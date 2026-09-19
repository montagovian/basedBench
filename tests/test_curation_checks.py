"""Component aggregation, Luna selection, and paid-request budget boundaries."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from basedbench.pipeline import curation_checks as checks
from basedbench.pipeline import curation_history
from basedbench.pipeline.curation_corpus import digest


def component(verdict="pass"):
    return {"verdict": verdict, "pass_score": .8 if verdict == "pass" else .2,
            "reason": "Candidate explanation omits its central contrast." if verdict == "fail" else "Supported.",
            "evidence_comment_ids": ["c1"]}


def assessment(failed="ground_truth"):
    return {name: component("fail" if name == failed else "pass") for name in checks.CHECKS}


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    Image.new("RGB", (8, 8), "red").save(tmp_path / "assets/pixels", format="PNG")
    rows = [{"post_id": f"p{i}", "input_sha256": f"hash{i}", "group_id": f"g{i}",
             "split": "development" if i < 24 else "calibration" if i < 30 else "test",
             "label": "accept" if i % 2 else "reject", "review_notes": "SECRET_REVIEW",
             "input": {"explanation": f"Explanation {i}", "comment_evidence": "ID: c1 | Score: 10\nEvidence\n---",
                       "image_sha256": "pixels", "forbidden": "SECRET_INPUT"}}
            for i in range(34)]
    monkeypatch.setattr(checks, "load_corpus", lambda path: ({"corpus_id": "corpus"}, rows))
    monkeypatch.setattr(checks, "history_status", lambda *args: {"status": "exploratory_only"})
    return tmp_path, rows


class LunaStub:
    def __init__(self):
        self.responses = self
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        await asyncio.sleep(0)  # Exercise simultaneous reservations.
        direct = "decision" in kwargs["text"]["format"]["schema"]["properties"]
        value = ({"decision": "accept", "score": .8, "reason_codes": ["eligible"],
                  "reason": "Supported", "evidence_comment_ids": ["c1"]} if direct else assessment())
        text = json.dumps(value)
        return SimpleNamespace(status="completed", output_text=text,
                               usage=SimpleNamespace(model_dump=lambda **kw: {"input_tokens": 100, "output_tokens": 100}),
                               model_dump=lambda **kw: {"model": checks.MODEL, "status": "completed"})


class JevStub:
    def __init__(self):
        self.requests = []

    async def post(self, path, *, json):
        self.requests.append(json)
        await asyncio.sleep(0)
        body = {"model": checks.replay.JEV_MODEL,
                "answers": {name: {"type": "choice", "choice": "fail" if name == "ground_truth" else "pass",
                                   "probabilities": {"pass": .1 if name == "ground_truth" else .8,
                                                     "fail": .8 if name == "ground_truth" else .1, "uncertain": .1}}
                            for name in checks.CHECKS},
                "usage": {"input_tokens": 500, "output_tokens": 0}}
        return httpx.Response(200, json=body, request=httpx.Request("POST", "https://api.typesafe.ai" + path))


def test_failed_ground_truth_cannot_be_overruled_by_other_passes():
    value = assessment()
    assert checks.combine(value) == "reject"
    value["ground_truth"] = component("uncertain")
    assert checks.combine(value) == "defer"
    value["ground_truth"] = component()
    assert checks.combine(value) == "accept"
    del value["ground_truth"]
    with pytest.raises(ValueError):
        checks.combine(value)


def test_model_mismatch_and_missing_component_never_become_rejections(corpus):
    _, rows = corpus
    call = {"status": "completed", "response": {"model": "gpt-5.5-2026-04-23"},
            "output_text": json.dumps(assessment()), "usage": {"input_tokens": 100, "output_tokens": 100}}
    d, _ = checks.parse(rows[24], "luna_checks", call)
    assert d.decision == "defer" and d.error and d.score is None
    call["response"]["model"] = checks.MODEL
    value = assessment()
    del value["content_policy"]
    call["output_text"] = json.dumps(value)
    d, _ = checks.parse(rows[24], "luna_checks", call)
    assert d.decision == "defer" and d.error


def test_budget_reserves_concurrent_calls_and_keeps_unknown_cost(tmp_path):
    (tmp_path / "calls").mkdir()
    bounds = {f"p{i}.luna_checks": .1 for i in range(4)}
    plan = {"experiment_id": "e", "budget_usd": .21, "request_bounds_usd": bounds}
    budget = checks.Budget(plan, tmp_path)
    assert budget.reserve("p0", "luna_checks") == .1
    assert budget.reserve("p1", "luna_checks") == .1
    assert budget.reserve("p2", "luna_checks") is None
    budget.settle("p0", "luna_checks", {"usage": None})
    assert budget.reserve("p2", "luna_checks") is None
    budget.settle("p1", "luna_checks", {"usage": {"input_tokens": 0, "output_tokens": 0}})
    assert budget.reserve("p2", "luna_checks") == .1
    # A pending request consumes its allowance after a process restart as well.
    (tmp_path / "calls/p0.luna_checks.pending").write_text("e")
    restarted = checks.Budget(plan, tmp_path)
    assert restarted.charges["p0.luna_checks"] == .1
    assert restarted.reserve("p1", "luna_checks") == .1
    assert restarted.reserve("p2", "luna_checks") is None


def test_budget_accounts_cache_writes_and_stops_on_broken_allowance(tmp_path):
    (tmp_path / "calls").mkdir()
    plan = {"experiment_id": "e", "budget_usd": 1,
            "request_bounds_usd": {"p0.luna_checks": .001, "p1.luna_checks": .001}}
    budget = checks.Budget(plan, tmp_path)
    usage = {"input_tokens": 10_000, "output_tokens": 0}
    assert checks.cost(usage, "luna_checks", upper=True) > checks.cost(usage, "luna_checks")
    budget.settle("p0", "luna_checks", {"usage": usage})
    assert budget.violated and budget.reserve("p1", "luna_checks") is None


def test_budget_skips_all_requests_when_allowance_wont_fit(corpus):
    path, _ = corpus
    luna, jev = LunaStub(), JevStub()
    report = asyncio.run(checks.run_checks(path, path / "tiny-budget", history_audit=path / "audit",
                        api_key="fake", jev_api_key="fake", budget_usd=.0000001, limit=1,
                        client=luna, jev_client=jev))
    assert not luna.requests and not jev.requests
    assert all(m["errors"] == 1 and m["deferred"] == 1 for m in report["metrics"].values())
    assert report["cost"]["accounted_usd_including_unknown_allowances"] == 0


def test_end_to_end_same_inputs_luna_only_no_repeated_spend_and_history(corpus, monkeypatch):
    path, rows = corpus
    luna, jev = LunaStub(), JevStub()
    output = path / "run"
    args = dict(history_audit=path / "audit", api_key="fake", jev_api_key="fake", budget_usd=.5,
                split="calibration", limit=3, client=luna, jev_client=jev)
    report = asyncio.run(checks.run_checks(path, output, **args))
    assert all(r["model"] == "gpt-5.6-luna" for r in luna.requests)
    assert len(luna.requests) == 9 and len(jev.requests) == 3
    assert "SECRET" not in json.dumps([luna.requests, jev.requests])
    assert report["metrics"]["luna_direct"]["accepted"] == 3
    assert report["metrics"]["luna_checks"]["rejected"] == 3
    assert report["metrics"]["jev"]["rejected"] == 3
    assert report["component_counts"]["jev"]["ground_truth"] == {"fail": 3}
    for index in range(0, 9, 3):
        assert luna.requests[index]["input"] == luna.requests[index + 1]["input"]
        assert luna.requests[index + 1]["input"][0]["content"] == luna.requests[index + 2]["input"][0]["content"][:1]
        direct_schema = luna.requests[index]["text"]["format"]["schema"]
        check_schema = luna.requests[index + 1]["text"]["format"]["schema"]
        assert direct_schema["properties"]["evidence_comment_ids"]["items"]["enum"] == ["c1"]
        assert check_schema["$defs"]["Check"]["properties"]["evidence_comment_ids"]["items"]["enum"] == ["c1"]
    again = asyncio.run(checks.run_checks(path, output, **args))
    assert len(luna.requests) == 9 and len(jev.requests) == 3
    assert again["cost"] == report["cost"]
    with pytest.raises(ValueError, match="frozen"):
        asyncio.run(checks.run_checks(path, output, **{**args, "budget_usd": 2}))
    monkeypatch.setattr(curation_history, "load_corpus", lambda _: ({"corpus_id": "corpus"}, rows))
    (path / "history.json").write_text(json.dumps([{"corpus": "old", "run": "run"}]))
    audit = curation_history.audit_history(path, path / "history.json", path / "history-audit.json")
    assert audit["verified_runs"][0]["evaluation_ids"] == report["evaluation_ids"]
    assert audit["counts"]["unexposed_in_declared_history"] == 4


def test_jev_only_needs_no_openai_client_or_key(corpus, monkeypatch):
    import openai

    path, _ = corpus
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: pytest.fail("JEV-only opened OpenAI client"))
    jev = JevStub()
    report = asyncio.run(checks.run_checks(path, path / "jev-only", history_audit=path / "audit",
                        api_key=None, jev_api_key="fake", budget_usd=.01, limit=2,
                        jev_only=True, jev_client=jev))
    assert set(report["metrics"]) == {"jev"} and len(jev.requests) == 2
    assert report["cost"]["estimated_usd"] < .01


def test_image_allowance_covers_patches_not_base64_size():
    body = {"model": checks.MODEL, "input": [{"type": "input_image", "detail": "high", "image_url": "a" * 100000}],
            "max_output_tokens": 4096}
    first = checks.request_bound(body, "luna_image_checks")
    body["input"][0]["image_url"] *= 2
    assert checks.request_bound(body, "luna_image_checks") == first
    body["input"][0]["detail"] = "original"
    with pytest.raises(ValueError):
        checks.request_bound(body, "luna_image_checks")
