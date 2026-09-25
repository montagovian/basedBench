"""Content routes must preserve uncertainty, evidence isolation and spending limits."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from PIL import Image
import pytest

from basedbench.pipeline import content_policy as policy
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json


def assessment(findings=None, **updates):
    return {"findings": findings or [], "context_sufficient": True, "context_gap": None,
            "rationale": "Brief description of the candidate's content.", **updates}


def finding(application="exclude", location="image", **updates):
    return {"category": "sexual_content", "location": location, "observation": "A specific content concern.",
            "image_anchor": "A relevant visual detail.", "evidence_comment_ids": [],
            "application": application, **updates}


def call(payload, **updates):
    return {"status": "completed", "response": {"model": policy.checks.MODEL},
            "output_text": json.dumps(payload), "error": None, **updates}


def response(payload):
    text = json.dumps(payload)
    usage = {"input_tokens": 100, "output_tokens": 100}
    return SimpleNamespace(status="completed", output_text=text,
        usage=SimpleNamespace(model_dump=lambda **_: usage),
        model_dump=lambda **_: {"model": policy.checks.MODEL, "status": "completed", "usage": usage})


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    assets = tmp_path / "source"
    assets.mkdir()
    image = tmp_path / "image.png"
    Image.new("RGB", (32, 32), "white").save(image)
    sha = file_hash(image)
    (assets / sha).write_bytes(image.read_bytes())
    evidence = {"explanation": "An ordinary joke.", "comment_evidence": "ID: c1 | Score: 5\nContext", "image_sha256": sha}
    cases = {"p1": {"post_id": "p1", "input": evidence, "input_sha256": digest(evidence),
                    "group_id": "g1", "stratum": "development", "previous_feedback": []}}
    event = {"event_id": "SECRET_EVENT", "notes": "SECRET_REVIEW_NOTE", "fields": {"content": "pass", "admission": "reject"}}
    store = SimpleNamespace(cases=cases, manifest={"packet_id": "packet"}, events=lambda: [event],
                            state=lambda *_: {"latest": event})
    monkeypatch.setattr(policy, "ReviewStore", lambda _: store)
    output = tmp_path / "run"
    settings = policy.prepare(tmp_path / "packet", assets, output, budget_usd=.75)
    return cases["p1"], output, settings, store, assets


def test_comments_alone_cannot_exclude_candidate():
    result = policy.decision(policy.ContentAssessment.model_validate(assessment([
        finding(location="context_only", image_anchor=None)])))
    assert result["decision"] == "pass" and not result["excluding_findings"]


@pytest.mark.parametrize("application,expected", [("allow", "pass"), ("exclude", "fail"),
                                                 ("policy_boundary", "defer"), ("needs_context", "defer")])
def test_findings_produce_distinct_routes(application, expected):
    result = policy.decision(policy.ContentAssessment.model_validate(assessment([finding(application)])))
    assert result["decision"] == expected
    if expected == "defer":
        assert result["reason_codes"] == [application]


def test_clear_exclusion_does_not_disappear_due_to_another_uncertain_finding():
    result = policy.decision(policy.ContentAssessment.model_validate(assessment([
        finding(), finding("policy_boundary"), finding("needs_context")])))
    assert result["decision"] == "fail"
    assert result["reason_codes"] == ["established_exclusion", "policy_boundary", "needs_context"]


def test_unknown_context_without_findings_cannot_pass():
    result = policy.decision(policy.ContentAssessment.model_validate(assessment(
        context_sufficient=False, context_gap="The obscured reference determines the meaning.")))
    assert result["decision"] == "defer" and result["reason_codes"] == ["needs_context"]


def test_missing_anchor_and_inconsistent_context_are_invalid():
    with pytest.raises(ValueError, match="anchor"):
        policy.Finding.model_validate(finding(image_anchor=None))
    with pytest.raises(ValueError, match="gap"):
        policy.ContentAssessment.model_validate(assessment(context_sufficient=False))


def test_known_unresolved_feedback_stays_separate_from_blind_verdict():
    route = policy.decision(policy.ContentAssessment.model_validate(assessment()))
    effective = policy.preserve_unresolved(route, "boundary")
    assert effective["decision"] == "defer" and effective["model_decision"] == "pass"
    assert route["decision"] == "pass"


def test_prompts_never_receive_human_labels_notes_or_overall_admission(frozen):
    case, output, settings, *_ = frozen
    stored_case = json.loads((output / "cases.json").read_text())[0]
    assert stored_case["gold"] == "pass"  # Overall reject is irrelevant.
    for arm in policy.ARMS:
        req = policy.make_request(stored_case, arm, output)
        assert "SECRET_" not in json.dumps(req)
        assert set(json.loads(req["input"][0]["content"][0]["text"])) == {"stored_explanation_context", "source_comments_context"}
        assert req["input"][0]["content"][1]["type"] == "input_image"
        assert req["store"] is False
    assert settings["max_calls"] == 2


def test_tentative_and_blank_labels_are_never_made_binary(frozen, tmp_path, monkeypatch):
    _, _, _, store, assets = frozen
    store.state = lambda *_: {"latest": {"event_id": "event", "notes": "", "fields": {"content": "boundary"}}}
    settings = policy.prepare(tmp_path / "packet", assets, tmp_path / "boundary", budget_usd=.75)
    assert settings["label_counts"] == {"unresolved": 1}
    store.state = lambda *_: {"latest": {"event_id": "event", "notes": "", "fields": {"admission": "reject"}}}
    with pytest.raises(ValueError, match="No explicit content"):
        policy.prepare(tmp_path / "packet", assets, tmp_path / "blank", budget_usd=.75)


@pytest.mark.parametrize("payload", [assessment([finding(evidence_comment_ids=["invented"])]),
                                    assessment([finding(image_anchor=None)])])
def test_invalid_evidence_is_error_not_content_rejection(frozen, payload):
    case, *_ = frozen
    result = policy.parse(case, call(payload))
    assert result["decision"] == "defer" and result["technical_status"] == "error"


def test_refusal_wrong_model_and_malformed_output_are_errors(frozen):
    case, *_ = frozen
    for bad in [call(assessment(), status="incomplete"), call(assessment(), response={"model": "gpt-5.5"}),
                call(assessment(), output_text="refusal")]:
        result = policy.parse(case, bad)
        assert result["decision"] == "defer" and result["technical_status"] == "error"


@pytest.mark.asyncio
async def test_resume_has_no_paid_repeats_and_tampering_is_detected(frozen):
    _, output, settings, *_ = frozen
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=response(assessment()))))
    first = await policy.run(output, budget_usd=.75, client=client)
    assert client.responses.create.call_count == 2
    second = await policy.run(output, budget_usd=.75, client=client)
    assert client.responses.create.call_count == 2 and first == second
    assert first["metrics"]["clarified"]["by_gold"]["pass"]["pass"] == 1
    request_path = next((output / "requests").glob("*.json"))
    request_path.write_text("{}")
    with pytest.raises(ValueError, match="evidence/request changed"):
        await policy.run(output, budget_usd=.75, client=client)


@pytest.mark.asyncio
async def test_missing_image_defers_without_a_provider_call(frozen, tmp_path):
    _, _, _, store, assets = frozen
    next(assets.iterdir()).unlink()
    output = tmp_path / "missing"
    settings = policy.prepare(tmp_path / "packet", assets, output, budget_usd=.75)
    assert settings["max_calls"] == 0
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock()))
    await policy.run(output, budget_usd=.75, client=client)
    client.responses.create.assert_not_called()
    rows = json.loads((output / "results.json").read_text())
    assert all(r["model_route"]["reason_codes"] == ["missing_image"] for r in rows)


@pytest.mark.asyncio
async def test_budget_and_interrupted_request_never_silently_retry(frozen):
    _, output, settings, *_ = frozen
    key = "p1.old_wording"
    (output / "calls" / f"{key}.pending").write_text(settings["experiment_id"])
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=response(assessment()))))
    report = await policy.run(output, budget_usd=.75, client=client)
    assert client.responses.create.call_count == 1
    assert report["metrics"]["old_wording"]["by_gold"]["pass"]["error"] == 1
    assert report["accounted_usd"] >= settings["request_bounds_usd"][key]
    with pytest.raises(ValueError, match="cap must match"):
        await policy.run(output, budget_usd=.1, client=client)


@pytest.mark.asyncio
async def test_fatal_provider_error_persists_across_resume(frozen):
    _, output, settings, *_ = frozen
    class Fatal(Exception):
        status_code = 401
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=Fatal("Denied"))))
    await policy.run(output, budget_usd=.75, client=client)
    before = client.responses.create.call_count
    await policy.run(output, budget_usd=.75, client=client)
    assert client.responses.create.call_count == before


@pytest.mark.asyncio
async def test_insufficient_budget_prevents_dispatch(frozen, tmp_path):
    _, _, _, _, assets = frozen
    output = tmp_path / "tiny-budget"
    policy.prepare(tmp_path / "packet", assets, output, budget_usd=.000001)
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock()))
    report = await policy.run(output, budget_usd=.000001, client=client)
    client.responses.create.assert_not_called()
    assert report["accounted_usd"] == 0
    assert report["metrics"]["clarified"]["by_gold"]["pass"]["error"] == 1


@pytest.mark.asyncio
async def test_focused_revision_runs_only_requested_variant(frozen, tmp_path):
    _, _, _, _, assets = frozen
    output = tmp_path / "revision"
    settings = policy.prepare(tmp_path / "packet", assets, output, budget_usd=.65, arms=("clarified",))
    assert settings["max_calls"] == 1 and settings["arms"] == ["clarified"]
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=response(assessment()))))
    report = await policy.run(output, budget_usd=.65, client=client)
    assert client.responses.create.call_count == 1
    assert set(report["metrics"]) == {"clarified"}
    assert len(json.loads((output / "results.json").read_text())) == 1
