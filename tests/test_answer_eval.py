"""Meaning-sensitive routing, label isolation, budget enforcement and safe resume."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from basedbench.pipeline import answer_eval as answers
from basedbench.pipeline.curation_corpus import file_hash, write_json


def check(verdict="pass", reason="The explanation matches the shared joke."):
    return {"image_setup": "The image provides a concrete setup.", "joke_connection": "The payoff inverts the setup.",
            "claim_support": [{"claim": "The intended reading", "support": "shared_comments", "evidence_comment_ids": ["c1", "c2", "c3"]}],
            "missing_core_details": [], "verdict": verdict, "reason": reason,
            "defects": [] if verdict == "pass" else ["missing_core_connection"],
            "evidence_comment_ids": ["c1", "c2", "c3"]}


def draft(text="The corrected explanation connects the setup to its payoff."):
    return {"status": "proposed", "explanation": text, "reason": "Supported by image and comments.",
            "evidence_comment_ids": ["c1", "c2", "c3"]}


@pytest.fixture
def frozen(tmp_path):
    assets = tmp_path / "source-assets"
    assets.mkdir()
    image = tmp_path / "image.png"
    Image.new("RGB", (24, 24), "white").save(image)
    sha = file_hash(image)
    (assets / sha).write_bytes(image.read_bytes())
    case = {"case_id": "p1-bad", "post_id": "p1", "gold": "fail", "gold_source": "SECRET_GOLD_SOURCE",
            "notes": "SECRET_EXPECTED_MEANING", "provenance": {"reviewer": "SECRET_REVIEWER"},
            "input": {"explanation": "The bad answer names a reference but misses its connection.",
                      "comment_evidence": "ID: c1 | Score: 8\nFirst account\nID: c2 | Score: 7\nSecond account\nID: c3 | Score: 6\nThird account",
                      "image_sha256": sha}}
    source, output = tmp_path / "cases.json", tmp_path / "run"
    write_json(source, [case])
    plan = answers.prepare(source, assets, output, budget_usd=1)
    return case, output, plan


def response(payload, model=answers.checks.MODEL):
    text = json.dumps(payload)
    usage = {"input_tokens": 100, "output_tokens": 50}
    return SimpleNamespace(status="completed", output_text=text,
        usage=SimpleNamespace(model_dump=lambda **_: usage),
        model_dump=lambda **_: {"model": model, "status": "completed", "usage": usage, "output_text": text})


def test_generation_and_verification_are_blind_to_labels_and_previous_judgments(frozen):
    case, output, _ = frozen
    for stage in (*answers.STAGES, "jev"):
        body = answers.make_request(case, stage, output, explanation="CANDIDATE", critique={"reason": "PRIVATE_CRITIQUE"})
        serialized = json.dumps(body)
        assert "SECRET_" not in serialized
        assert case["input"]["explanation"] not in serialized
        if stage == "generate":
            assert "CANDIDATE" not in serialized
        if not stage.endswith("repair"):
            assert "PRIVATE_CRITIQUE" not in serialized
        if stage.endswith("verify"):
            assert body["instructions"] == answers.CHECK
            evidence = json.loads(body["input"][0]["content"][0]["text"])
            assert set(evidence) == {"comment_evidence", "candidate_answer"}


@pytest.mark.asyncio
async def test_wrong_meaning_triggers_repair_despite_consensus_and_verified_answer_is_separate(frozen):
    case, _, _ = frozen
    calls = []
    async def invoke(stage, **kwargs):
        calls.append((stage, kwargs))
        if stage == "original_check":
            return check("fail", "Comments agree, but the stored answer omits their intended connection.")
        if stage.endswith("repair") or stage == "generate":
            return draft()
        return check()
    result = await answers.evaluate_case(case, invoke)
    assert result["original"]["repaired"]
    assert result["original"]["explanation"] != case["input"]["explanation"]
    assert case["input"]["explanation"].startswith("The bad answer")
    verifier = dict(calls)["original_verify"]
    assert set(verifier) == {"explanation"}
    assert "original_repair" in dict(calls)


@pytest.mark.asyncio
async def test_failed_repair_stays_unresolved_and_does_not_loop(frozen):
    case, _, _ = frozen
    calls = []
    async def invoke(stage, **kwargs):
        calls.append(stage)
        return draft() if stage.endswith("repair") or stage == "generate" else check("fail")
    result = await answers.evaluate_case(case, invoke)
    assert result["original"]["status"] == result["fresh"]["status"] == "unresolved"
    assert result["original"]["explanation"] is None
    assert calls.count("original_repair") == calls.count("generated_repair") == 1
    assert len(calls) == 7


@pytest.mark.asyncio
async def test_competing_readings_and_missing_evidence_do_not_force_repairs(frozen):
    case, _, _ = frozen
    calls = []
    async def invoke(stage, **kwargs):
        calls.append(stage)
        if stage == "generate":
            return {"status": "insufficient_evidence", "explanation": None, "reason": "Competing readings", "evidence_comment_ids": []}
        return {**check("fail"), "defects": ["competing_readings"]}
    result = await answers.evaluate_case(case, invoke)
    assert calls == ["original_check", "generate"]
    assert result["original"]["status"] == result["fresh"]["status"] == "unresolved"


@pytest.mark.parametrize("payload", [
    {**check(), "evidence_comment_ids": ["c1", "c2", "invented"]},
    {**check(), "evidence_comment_ids": ["c1", "c1", "c1"]},
    {**check(), "defects": ["unsupported_addition"]},
    {**check("fail"), "defects": []},
])
def test_invalid_or_inconsistent_verifier_output_is_an_error(frozen, payload):
    case, _, _ = frozen
    call = {"status": "completed", "response": {"model": answers.checks.MODEL}, "output_text": json.dumps(payload)}
    assert "error" in answers.parse(case, "original_verify", call)


def test_model_substitution_and_incomplete_calls_never_verify(frozen):
    case, _, _ = frozen
    call = {"status": "completed", "response": {"model": "another-model"}, "output_text": json.dumps(check())}
    assert "error" in answers.parse(case, "original_check", call)
    call.update(status="incomplete", response={"model": answers.checks.MODEL})
    assert "error" in answers.parse(case, "original_check", call)


@pytest.mark.parametrize("change", [
    {"missing_core_details": ["The image's visual punchline"]},
    {"claim_support": [{"claim": "Optional embellishment", "support": "minority_comment", "evidence_comment_ids": ["c1"]}]},
    {"claim_support": [{"claim": "Unsupported assertion", "support": "unsupported", "evidence_comment_ids": []}]},
    {"claim_support": [{"claim": "Made-up evidence", "support": "image_and_shared_comments", "evidence_comment_ids": ["invented"]}]},
])
def test_global_pass_cannot_override_claim_evidence_or_missing_payoff(frozen, change):
    case, _, _ = frozen
    call = {"status": "completed", "response": {"model": answers.checks.MODEL}, "output_text": json.dumps(check() | change)}
    assert "error" in answers.parse(case, "original_check", call)


def test_individual_fact_does_not_need_three_citations_when_shared_reading_has_them(frozen):
    case, _, _ = frozen
    payload = check()
    payload["claim_support"].append({"claim": "A background identifying fact", "support": "shared_comments", "evidence_comment_ids": ["c1"]})
    call = {"status": "completed", "response": {"model": answers.checks.MODEL}, "output_text": json.dumps(payload)}
    assert answers.parse(case, "original_check", call)["verdict"] == "pass"


@pytest.mark.asyncio
async def test_parser_replay_reuses_only_identical_requests_with_preserved_usage_and_zero_new_cost(frozen, tmp_path):
    _, source, _ = frozen
    async def create(**body):
        return response(draft() if "status" in body["text"]["format"]["schema"]["properties"] else check())
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=create)))
    original = await answers.run(source, budget_usd=1, client=client)
    target = tmp_path / "replay"
    answers.prepare(source / "cases.json", source / "assets", target, budget_usd=1, reuse_from=source)
    client.responses.create.reset_mock(side_effect=True)
    client.responses.create.side_effect = AssertionError("Should reuse")
    replay = await answers.run(target, budget_usd=1, client=client)
    client.responses.create.assert_not_called()
    assert replay["results"] == original["results"]
    assert replay["reused_calls"] == replay["calls"] == 3
    assert replay["cost_estimate_usd"] == replay["accounted_usd"] == 0
    saved = json.loads(next((target / "calls").glob("*.json")).read_text())
    assert saved["usage"]["input_tokens"] == 100
    assert saved["reused_from"]["experiment_id"] == original["experiment_id"]
    await answers.run(target, budget_usd=1, client=client)
    client.responses.create.assert_not_called()
    source_call = Path(saved["reused_from"]["path"])
    source_call.write_text("{}")
    with pytest.raises(ValueError, match="Frozen replay response"):
        answers.load_plan(target)


@pytest.mark.asyncio
async def test_finished_calls_are_not_repeated_and_request_tampering_is_detected(frozen):
    case, output, _ = frozen
    async def create(**body):
        schema = body["text"]["format"]["schema"]
        return response(draft() if "status" in schema["properties"] else check())
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=create)))
    first = await answers.run(output, budget_usd=1, client=client)
    assert first["metrics"]["original_check"]["defects_missed"] == 1
    assert client.responses.create.await_count == 3
    second = await answers.run(output, budget_usd=1, client=client)
    assert client.responses.create.await_count == 3
    assert first == second
    (output / "requests" / f"{case['case_id']}.original_check.json").write_text("{}")
    with pytest.raises(ValueError, match="Saved request"):
        await answers.run(output, budget_usd=1, client=client)


@pytest.mark.asyncio
async def test_interrupted_request_is_not_repeated_and_retains_cost_reservation(frozen):
    case, output, plan = frozen
    pending = output / "calls" / f"{case['case_id']}.original_check.pending"
    pending.write_text(plan["experiment_id"])
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=response(draft()))))
    # Generated verification is deliberately invalid as a Check: must stay error.
    report = await answers.run(output, budget_usd=1, client=client)
    assert client.responses.create.await_count == 2
    assert report["calls_without_usage"] == 1
    assert report["accounted_usd"] >= plan["request_bounds_usd"][f"{case['case_id']}.original_check"]
    assert report["results"][0]["original"]["status"] == "error"
    assert not pending.exists()


@pytest.mark.asyncio
async def test_fatal_provider_failure_stops_all_later_stages_and_resume(frozen):
    _, output, _ = frozen
    class AuthError(Exception):
        status_code = 401
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=AuthError("Unauthorized"))))
    await answers.run(output, budget_usd=1, client=client)
    await answers.run(output, budget_usd=1, client=client)
    assert client.responses.create.await_count == 1


@pytest.mark.asyncio
async def test_too_small_budget_prevents_dispatch(frozen, tmp_path):
    _, output, _ = frozen
    tiny = tmp_path / "tiny"
    answers.prepare(output / "cases.json", output / "assets", tiny, budget_usd=.000001)
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock()))
    report = await answers.run(tiny, budget_usd=.000001, client=client)
    client.responses.create.assert_not_called()
    assert report["accounted_usd"] == 0
    assert report["results"][0]["original"]["status"] == "error"


def test_frozen_assets_and_cases_cannot_change(frozen):
    _, output, _ = frozen
    (output / "cases.json").write_text("[]")
    with pytest.raises(ValueError, match="Frozen evidence"):
        answers.load_plan(output)


def test_cache_writes_are_included_in_cost():
    call = {"arm": "original_check", "usage": {"input_tokens": 1000, "output_tokens": 100,
        "input_tokens_details": {"cached_tokens": 100, "cache_write_tokens": 200}}}
    assert answers.exact_cost(call) == pytest.approx((700 * .2 + 100 * .02 + 200 * .25 + 100 * 1.2) / 1e6)
