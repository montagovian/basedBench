"""Leakage boundaries, provider validation, and paid-request recovery."""

import asyncio
import copy
import json
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from basedbench.pipeline import curation_history, curation_llm as llm
from basedbench.pipeline.curation_corpus import digest, file_hash


@pytest.fixture
def examples(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    Image.new("RGB", (8, 8), "red").save(assets / "pixels", format="PNG")
    return [{"post_id": f"p{i}", "input_sha256": f"hash{i}", "group_id": f"g{i}",
             "split": "development" if i < 24 else "calibration" if i < 30 else "test",
             "label": "accept" if i % 2 else "reject", "review_notes": "SECRET_REVIEW",
             "input": {"explanation": f"Explanation {i}", "comment_evidence": "ID: c1 | Score: 10\nA joke.\n---",
                       "image_sha256": "pixels", "forbidden": "SECRET_INPUT"}}
            for i in range(34)]


def assessment(**changes):
    return {"decision": "accept", "score": .8, "reason_codes": ["eligible"],
            "evidence_comment_ids": ["c1"], "reason": "Explained by the comment.", **changes}


class OpenAIStub:
    def __init__(self):
        self.requests = []
        self.responses = self

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        text = json.dumps(assessment())
        return SimpleNamespace(status="completed", output_text=text,
                               usage=SimpleNamespace(model_dump=lambda **kw: {"input_tokens": 100, "output_tokens": 10}),
                               model_dump=lambda **kw: {"status": "completed", "output_text": text})


def jev_body():
    return {"model": llm.JEV_MODEL, "answers": {"admission": {
        "type": "choice", "choice": "accept", "probabilities": {"accept": .8, "reject": .1, "defer": .1},
        "confidence": .5}}, "usage": {"input_tokens": 100, "output_tokens": 0}}


class JevStub:
    def __init__(self, status=200):
        self.requests = []
        self.status = status

    async def post(self, path, *, json):
        self.requests.append(json)
        return httpx.Response(self.status, json=jev_body(), request=httpx.Request("POST", "https://api.typesafe.ai" + path))


def plan_for(examples):
    references, _ = llm.select_examples(examples, "calibration", 2, "fixed")
    return {"experiment_id": "experiment", "arms": ["text", "image", "jev"],
            "instructions": llm.instructions(references), "reference_evidence": llm.reference_evidence(references),
            "policy_sha256": "policy", "response_schema": llm.Assessment.model_json_schema()}


def test_selection_is_label_blind_for_targets_and_keeps_groups(examples):
    examples[25]["group_id"] = examples[24]["group_id"]
    refs, selected = llm.select_examples(examples, "calibration", 3, "fixed")
    shuffled = copy.deepcopy(examples)
    for row in shuffled:
        if row["split"] != "development":
            row["label"] = "reject" if row["label"] == "accept" else "accept"
    again_refs, again = llm.select_examples(shuffled, "calibration", 3, "fixed")
    assert [r["post_id"] for r in selected] == [r["post_id"] for r in again]
    assert refs == again_refs and len(refs) == 8
    assert all(r["split"] == "development" for r in refs)
    groups = {r["group_id"] for r in selected}
    assert {r["post_id"] for r in selected} == {r["post_id"] for r in examples if r["group_id"] in groups}
    _, dev = llm.select_examples(examples, "development", 4, "fixed")
    assert not {r["group_id"] for r in refs} & {r["group_id"] for r in dev}
    with pytest.raises(ValueError):
        llm.select_examples(examples, "test", 2, "fixed")


def test_payloads_exclude_target_decisions_and_use_actual_image_format(tmp_path, examples):
    row, plan = examples[24], plan_for(examples)
    text = llm.request_content(row, "text", tmp_path)
    image = llm.request_content(row, "image", tmp_path)
    jev = llm.jev_request(row, plan)
    assert text == image[:1]
    assert image[1]["image_url"].startswith("data:image/png;base64,")
    assert jev["state"]["candidate"] == {k: row["input"][k] for k in ("explanation", "comment_evidence")}
    for payload in (text, image, jev, plan["instructions"]):
        assert "SECRET" not in json.dumps(payload)
    changed = {**row, "label": "opposite", "review_notes": "new secret"}
    assert llm.jev_request(changed, plan) == jev
    assert llm.request_content(changed, "text", tmp_path) == text


@pytest.mark.parametrize("problem", ["citation", "incomplete", "invalid_json"])
def test_invalid_openai_answers_defer_with_known_usage(examples, problem):
    call = {"status": "completed", "output_text": json.dumps(assessment()),
            "usage": {"input_tokens": 100, "output_tokens": 10}}
    if problem == "citation":
        call["output_text"] = json.dumps(assessment(evidence_comment_ids=["outside"]))
    elif problem == "incomplete":
        call["status"] = "incomplete"
    else:
        call["output_text"] = "not JSON"
    result = llm.normalize_call(examples[24], "text", call)
    assert result.decision == "defer" and result.score is None and result.error
    assert result.cost_usd == pytest.approx(.0008)
    assert llm.estimate_cost(None) is None


def test_jev_checks_version_distribution_and_winning_choice(examples):
    body = jev_body()
    call = {"response": body, "usage": body["usage"]}
    good = llm.normalize_call(examples[24], "jev", call)
    assert good.decision == "accept" and good.score == .8
    assert good.cost_usd == pytest.approx(.0000042)
    for mutate in (lambda b: b.update(model="other-version"),
                   lambda b: b["answers"]["admission"]["probabilities"].update(accept=.9),
                   lambda b: b["answers"]["admission"].update(choice="reject")):
        bad = copy.deepcopy(body)
        mutate(bad)
        result = llm.normalize_call(examples[24], "jev", {"response": bad, "usage": body["usage"]})
        assert result.decision == "defer" and result.error and result.score is None


def test_checkpoint_recovery_never_repeats_finished_or_uncertain_calls(tmp_path, examples):
    plan, rows = plan_for(examples), examples[24:26]
    output = tmp_path / "run"
    (output / "calls").mkdir(parents=True)
    (output / "calls" / "p24.text.pending").write_text("experiment")
    openai, jev = OpenAIStub(), JevStub()
    asyncio.run(llm.collect_calls(openai, rows, tmp_path, output, plan, concurrency=1, jev_client=jev))
    assert len(openai.requests) == 3 and len(jev.requests) == 2
    interrupted = json.loads((output / "calls" / "p24.text.json").read_text())
    assert interrupted["status"] == "unknown" and interrupted["usage"] is None
    assert llm.normalize_call(rows[0], "text", interrupted).cost_usd is None
    asyncio.run(llm.collect_calls(openai, rows, tmp_path, output, plan, concurrency=1, jev_client=jev))
    assert len(openai.requests) == 3 and len(jev.requests) == 2
    assert all(r["store"] is False for r in openai.requests)
    # Another arm's answer must not be fed into the next request.
    assert "Explained by the comment." not in json.dumps(openai.requests)


def test_fatal_jev_error_stops_only_jev(tmp_path, examples):
    output = tmp_path / "run"
    (output / "calls").mkdir(parents=True)
    openai, jev = OpenAIStub(), JevStub(status=401)
    asyncio.run(llm.collect_calls(openai, examples[24:26], tmp_path, output, plan_for(examples), concurrency=1, jev_client=jev))
    assert len(jev.requests) == 1 and len(openai.requests) == 4
    skipped = json.loads((output / "calls" / "p25.jev.json").read_text())
    assert "Not attempted" in skipped["error"] and skipped["usage"]["input_tokens"] == 0


def test_run_and_history_preserve_subset_and_reference_exposure(tmp_path, examples, monkeypatch):
    manifest = {"corpus_id": "corpus"}
    monkeypatch.setattr(llm, "load_corpus", lambda path: (manifest, examples))
    monkeypatch.setattr(llm, "history_status", lambda *args: {"status": "exploratory_only"})
    openai, jev = OpenAIStub(), JevStub()
    output = tmp_path / "run"
    kwargs = dict(history_audit=tmp_path / "unused-audit", api_key="fake", split="development", limit=3,
                  client=openai, jev_client=jev)
    report = asyncio.run(llm.run_llm(tmp_path, output, **kwargs))
    assert report["metrics"]["text"]["n"] == 3
    assert report["metrics"]["jev"]["errors"] == 0
    assert len(report["reference_ids"]) == 8 and report["training_ids"] == []
    assert not set(report["reference_ids"]) & set(report["evaluation_ids"])
    assert report["cost"]["calls_without_usage"] == 0
    asyncio.run(llm.run_llm(tmp_path, output, **kwargs))
    assert len(openai.requests) == 6 and len(jev.requests) == 3
    with pytest.raises(ValueError, match="frozen settings"):
        asyncio.run(llm.run_llm(tmp_path, output, **{**kwargs, "limit": 4}))
    # Simulate a later corpus that reserved a previously used reference.
    current = copy.deepcopy(examples)
    reference_id = report["reference_ids"][0]
    next(r for r in current if r["post_id"] == reference_id)["split"] = "test"
    monkeypatch.setattr(curation_history, "load_corpus", lambda path: (manifest, current if path.name == "current" else examples))
    history = tmp_path / "history.json"
    history.write_text(json.dumps([{"corpus": "old", "run": "run"}]))
    audit = curation_history.audit_history(tmp_path / "current", history, tmp_path / "audit.json")
    assert audit["counts"]["previously_used_as_reference"] == 1
    assert audit["verified_runs"][0]["evaluation_ids"] == report["evaluation_ids"]
    assert file_hash(output / "decisions.jsonl") == report["decisions_sha256"]
    # An explicit membership list cannot hide overlap with its references.
    report["reference_ids"].append(report["evaluation_ids"][0])
    report["reference_ids_sha256"] = digest(report["reference_ids"])
    (output / "report.json").write_text(json.dumps(report))
    with pytest.raises(ValueError, match="overlap"):
        curation_history.audit_history(tmp_path / "current", history, tmp_path / "invalid-audit.json")
