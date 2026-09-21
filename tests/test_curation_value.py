"""Evidence ablations, frozen requests, one-question parsing and paid-call resumption."""

import json

import pytest

from basedbench.pipeline import curation_enriched as enriched
from basedbench.pipeline import curation_value as value
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json


@pytest.fixture
def inputs(tmp_path):
    source = tmp_path / "source"
    (source / "jev_clear_rules" / "requests").mkdir(parents=True)
    rows, gold, observations = [], {}, {}
    for i, truth in enumerate(("pass", "fail", None)):
        pid = f"p{i}"
        content = {"explanation": f"Explanation {i}", "comment_evidence": f"Comments {i}", "image_sha256": f"image{i}"}
        row = {"post_id": pid, "input": content, "input_sha256": digest(content), "split": "calibration",
               "historical_label": "CANARY_LABEL", "previous_feedback": "CANARY_FEEDBACK"}
        rows.append(row)
        gold[pid] = {"components": {"benchmark_value": truth} if truth else {}, "admission": "reject",
                     "notes": "CANARY_NOTE", "unresolved": {} if truth else {"benchmark_value": "unsure"}}
        observations[pid] = {"image_sha256": f"image{i}", "visible_text": f"Caption {i}", "visible_scene": f"Scene {i}"}
        write_json(source / "jev_clear_rules" / "requests" / f"{pid}.json",
                   enriched.make_request(row, "jev_clear_rules", {}, tmp_path))
    write_json(source / "targets.json", rows)
    plan = {"evaluation_ids": [r["post_id"] for r in rows], "gold": gold, "corpus_id": "corpus",
            "files": {p.relative_to(source).as_posix(): file_hash(p) for p in source.rglob("*.json")}}
    plan["experiment_id"] = digest(plan)
    write_json(source / "plan.json", plan)
    obs = tmp_path / "observations.json"
    write_json(obs, {"author": "assistant", "items": observations})
    prompts = tmp_path / "prompts.json"
    spec = {"type": "choice", "instructions": "Some question", "criteria": {v: v for v in ("pass", "fail", "uncertain")}}
    write_json(prompts, {"common_instructions": "Common", "variants": {v: spec for v in ("interpretation_gap", "anchored_payoff", "combined")}})
    return source, prompts, obs, tmp_path / "out"


def test_frozen_factorial_requests_do_not_leak_feedback(inputs):
    source, prompts, obs, out = inputs
    plan = value.prepare(*inputs, budget_usd=.1)
    assert enriched.load_plan(out) == plan
    assert len(plan["request_bounds_usd"]) == 24
    assert plan["gold"]["p0"]["components"]["benchmark_value"] == "pass"
    for pid in plan["evaluation_ids"]:
        for name in ("control", "interpretation_gap", "anchored_payoff", "combined"):
            text = json.loads((out / f"{name}_text" / "requests" / f"{pid}.json").read_text())
            literal = json.loads((out / f"{name}_literal" / "requests" / f"{pid}.json").read_text())
            assert set(text["questions"]) == {"benchmark_value"}
            assert text["questions"] == literal["questions"]
            assert "CANARY" not in json.dumps(literal)
            assert set(text["state"]["candidate"]) == {"explanation", "comment_evidence"}
            addition = literal["state"]["candidate"].pop("literal_observation")
            assert set(addition) == {"visible_text", "visible_scene"}
            assert literal == text
    path = out / "control_text" / "requests" / "p0.json"
    path.write_text("{}")
    with pytest.raises(ValueError, match="Frozen"):
        enriched.load_plan(out)


def test_cap_and_mismatched_or_labeled_observations_fail_before_writes(inputs):
    _, _, obs, out = inputs
    with pytest.raises(ValueError, match="maximum allowances"):
        value.prepare(*inputs, budget_usd=.0000001)
    assert not out.exists()
    document = json.loads(obs.read_text())
    document["items"]["p0"]["image_sha256"] = "wrong"
    write_json(obs, document)
    with pytest.raises(ValueError, match="image mismatch"):
        value.prepare(*inputs, budget_usd=.1)
    document["items"]["p0"]["image_sha256"] = "image0"
    document["items"]["p0"]["value_label"] = "fail"
    write_json(obs, document)
    with pytest.raises(ValueError, match="only image identity"):
        value.prepare(*inputs, budget_usd=.1)
    assert not out.exists()


def response():
    return {"model": value.replay.JEV_MODEL, "answers": {"benchmark_value": {
        "type": "choice", "choice": "pass", "probabilities": {"pass": .6, "fail": .3, "uncertain": .1}}},
        "usage": {"input_tokens": 20, "output_tokens": 0}}


def test_choice_validation_preserves_abstention_and_rounded_scores():
    call = {"status": "completed", "response": response()}
    answer = call["response"]["answers"]["benchmark_value"]
    answer.update(choice="uncertain", probabilities={"pass": .33, "fail": .33, "uncertain": .33})
    assert value.parse(call)["verdict"] == "uncertain"
    answer["probabilities"]["pass"] = float("nan")
    assert value.parse(call)["verdict"] == "error"
    call["response"] = response()
    call["response"]["model"] = "unexpected-model"
    assert value.parse(call)["verdict"] == "error"
    call["response"] = response()
    call["response"]["answers"]["benchmark_value"]["choice"] = "fail"
    assert value.parse(call)["verdict"] == "error"


@pytest.mark.asyncio
async def test_resumption_never_repeats_completed_or_uncertain_requests(inputs, monkeypatch):
    import httpx
    *_, out = inputs
    plan = value.prepare(*inputs, budget_usd=.1)
    pending = out / "control_text" / "calls" / "p0.jev.pending"
    pending.write_text(plan["variants"]["control_text"]["experiment_id"])
    sent = []

    class Reply:
        def raise_for_status(self):
            pass
        def json(self):
            return response()

    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, *, json):
            sent.append(json)
            return Reply()

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    report = await value.run(out, budget_usd=.1, api_key="test-only")
    assert len(sent) == 23
    assert report["variants"]["control_text"]["errors"] == 1
    assert report["variants"]["control_text"]["metrics"]["confusion"] == {"fail->pass": 1, "pass->error": 1}
    assert report["variants"]["combined_literal"]["metrics"]["n"] == 2
    assert report["variants"]["combined_literal"]["unresolved"] == {"p2": "pass"}
    assert report["cost_usd"] < report["accounted_usd"] < .1
    await value.run(out, budget_usd=.1, api_key="test-only")
    assert len(sent) == 23
