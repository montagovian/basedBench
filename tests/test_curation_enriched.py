"""Partial gold, family separation, component denominators and shared spending."""

import json

import pytest
from PIL import Image

from basedbench.pipeline import curation_enriched as enriched
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json


def test_partial_gold_and_tentative_feedback_are_not_invented():
    case = {"previous_feedback": [{"item": {"current_decision": "reject", "decision_status": "tentative",
            "reason": "Maybe", "dimensions": {"content_policy": {"verdict": "fail", "certainty": "tentative"},
            "ground_truth": {"verdict": "fail", "certainty": "stated"}}}}]}
    gold = enriched.labels(case, None)
    assert gold["components"] == {"ground_truth": "fail"}
    assert gold["admission"] is None
    latest = {"fields": {"admission": "accept", "content": "boundary", "value": "unsure"}, "notes": "", "event_id": "e"}
    gold = enriched.labels(case, latest)
    assert gold["components"] == {}
    assert gold["unresolved"] == {"content_policy": "boundary", "benchmark_value": "unsure"}


@pytest.fixture
def sources(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    (corpus / "assets").mkdir(parents=True)
    cases, events = {}, []
    for i in range(8):
        image = tmp_path / f"{i}.png"
        Image.new("RGB", (24, 24), (i * 30, 30, 70)).save(image)
        sha = file_hash(image)
        (corpus / "assets" / sha).write_bytes(image.read_bytes())
        content = {"image_sha256": sha, "explanation": f"Explanation {i}",
                   "comment_evidence": f"ID: c{i} | Score: 42\nComment {i}"}
        pid = f"p{i}"
        cases[pid] = {"post_id": pid, "input": content, "input_sha256": digest(content), "group_id": pid,
                      "split": "calibration", "stratum": "random_control" if i < 6 else "previous_discussion", "previous_feedback": []}
        if i < 6:
            events.append({"post_id": pid, "kind": "feedback", "event_id": f"event{i}", "notes": "",
                           "fields": {"content": "pass", "ground_truth": "ready", "value": "yes" if i % 2 else "no",
                                      "admission": "accept" if i % 2 else "reject"}})
    class Store:
        def __init__(self, path):
            self.cases = cases
            self.manifest = {"packet_id": "packet", "corpus_id": "corpus"}
        def events(self):
            return events
    monkeypatch.setattr(enriched, "ReviewStore", Store)
    return corpus, cases, events


def test_folds_exclude_held_out_families_including_older_copies(sources):
    _, cases, events = sources
    gold = {p: enriched.labels(c, next((e for e in events if e["post_id"] == p), None)) for p, c in cases.items()}
    # The older p6 copy has a valid component label but belongs to target p0's family.
    gold["p6"]["components"] = {"benchmark_value": "pass"}
    family = enriched.families(cases, [["p0", "p6"]])
    targets = [e["post_id"] for e in events]
    folds = enriched.assign_folds(targets, family, gold, "fixed")
    family_folds = {family[p]: fold for p, fold in folds.items()}
    assert family["p0"] == family["p6"]
    for target in targets:
        refs = enriched.references(target, cases, gold, family, folds, "fixed")
        for name, examples in refs.items():
            for example in examples:
                pid = example["post_id"]
                assert family_folds.get(family[pid]) != folds[target]
                assert example["verdict"] == gold[pid]["components"][name]


def test_frozen_preparation_contains_no_candidate_labels_and_detects_tampering(tmp_path, sources):
    corpus, cases, _ = sources
    out = tmp_path / "experiment"
    plan = enriched.prepare(tmp_path / "packet", corpus, out, [], budget_usd=1)
    assert len(plan["request_bounds_usd"]) == 30
    assert enriched.load_plan(out) == plan
    request_path = out / "jev_examples" / "requests" / "p0.json"
    body = json.loads(request_path.read_text())
    assert body["state"]["candidate"] == {k: cases["p0"]["input"][k] for k in ("explanation", "comment_evidence")}
    assert "admission" not in body["state"]["candidate"]
    assert "historical_label" not in body["state"]["candidate"]
    for examples in body["state"]["component_examples"].values():
        assert all("post_id" not in e for e in examples)
    request_path.write_text("{}")
    with pytest.raises(ValueError, match="Frozen"):
        enriched.load_plan(out)


def test_component_denominators_include_abstention_and_leave_single_class_balanced_undefined():
    metrics = enriched.component_metrics({"a": "pass", "b": "fail", "c": "fail"}, {"a": "pass", "b": "uncertain", "c": "pass"})
    assert metrics["accuracy"] == pytest.approx(1 / 3)
    assert metrics["balanced_accuracy"] == .5
    assert metrics["fail_recall"] == 0
    assert enriched.component_metrics({"a": "pass"}, {"a": "pass"})["balanced_accuracy"] is None
    assert enriched.component_metrics({}, {})["accuracy"] is None


@pytest.mark.asyncio
async def test_budget_is_shared_across_variants_and_restores_unknown_requests(tmp_path, sources):
    corpus, _, _ = sources
    out = tmp_path / "experiment"
    plan = enriched.prepare(tmp_path / "packet", corpus, out, [], budget_usd=1)
    first, second = "jev_old_rules", "jev_clear_rules"
    pid = plan["evaluation_ids"][0]
    child = plan["variants"][first]
    pending = out / first / "calls" / f"{pid}.jev.pending"
    pending.write_text(child["experiment_id"])
    budget = enriched.restore_budget(plan, out)
    bound = plan["request_bounds_usd"][f"{first}:{pid}.jev"]
    assert sum(budget.charges.values()) == bound
    budget.limit = bound
    assert await enriched.ScopedBudget(budget, second).acquire(pid, "jev") is None
    call = {"experiment_id": child["experiment_id"], "input_sha256": child["input_hashes"][pid],
            "usage": {"input_tokens": 10, "output_tokens": 0}}
    write_json(pending.with_suffix(".json"), call)
    restored = enriched.restore_budget(plan, out)
    assert sum(restored.charges.values()) < bound
    assert await enriched.ScopedBudget(restored, second).acquire(pid, "jev") is not None
