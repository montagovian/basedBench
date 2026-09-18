"""Historical input provenance, leakage boundaries, and baseline evaluation."""

import json
import random
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from basedbench.cli import app
from basedbench.pipeline.curation_corpus import build_corpus, file_hash, load_corpus
from basedbench.pipeline.curation_eval import Decision, decide, feature_text, metrics, run_baseline

GENERATED = "2026-05-01T00:00:00.000Z"
REVIEWED = "2026-05-02T00:00:00Z"


@pytest.fixture
def source(tmp_path, db):
    def add(pid, *, positive=True, reason=None, image_copy=None):
        image_path = tmp_path / f"{pid}.png"
        if image_copy:
            image_path.write_bytes((tmp_path / f"{image_copy}.png").read_bytes())
        else:
            pixels = random.Random(pid).randbytes(32 * 32 * 3)
            Image.frombytes("RGB", (32, 32), pixels).save(image_path)
        db.conn.execute("""INSERT INTO memes
            (post_id, subreddit, title, local_image_path, retrieved_at, created_utc)
            VALUES (?, 'ExplainTheJoke', 'Current title', ?, ?, ?)""", (pid, str(image_path), GENERATED, GENERATED))
        db.conn.execute("INSERT INTO ground_truths (post_id, explanation, created_at) VALUES (?, ?, ?)",
                        (pid, "Later corrected explanation", GENERATED))
        db.conn.execute("INSERT INTO reviews (post_id, status, reason, reviewed_at) VALUES (?, ?, ?, ?)",
                        (pid, "validated" if positive else "excluded", reason if reason else None if positive else "other", REVIEWED))
        response = json.dumps({"has_consensus": True, "selected_explanation": f"Original explanation for {pid}", "confidence": 0.9})
        prompt = f"Subreddit: r/ExplainTheJoke\nComments (1 total):\nID: {pid}_c1 | Score: 100 | Author: private_author\nEvidence for {pid}\n---"
        db.conn.execute("""INSERT INTO llm_calls
            (post_id, session_id, role, model, system_prompt, user_prompt, prompt_version, created_at, response, verdict)
            VALUES (?, 'session', 'consensus', 'test-model', 'Original system', ?, 'prompt-v1', ?, ?, 'consensus')""",
                        (pid, prompt, GENERATED, response))

    def save():
        path = tmp_path / "source.db"
        with sqlite3.connect(path) as disk:
            db.conn.backup(disk)
        return path

    return add, save, db.conn


def test_build_uses_original_call_not_corrected_gloss_or_future_rerun(tmp_path, source):
    add, save, conn = source
    add("original")
    conn.execute("""INSERT INTO llm_calls
        (post_id, session_id, role, model, system_prompt, user_prompt, prompt_version, created_at, response, verdict)
        SELECT post_id, session_id, role, model, system_prompt, user_prompt, prompt_version,
               '2026-05-03T00:00:00Z', '{"has_consensus":true,"selected_explanation":"Future gloss"}', verdict
        FROM llm_calls WHERE post_id='original'""")
    db_path = save()
    original_db_hash = file_hash(db_path)
    output = tmp_path / "corpus"
    built = build_corpus(db_path, output, project_root=tmp_path)
    manifest, rows = load_corpus(output)
    assert file_hash(db_path) == original_db_hash
    assert len(rows) == 1
    row = rows[0]
    assert row["input"]["explanation"] == "Original explanation for original"
    assert row["provenance"]["current_explanation_differs"] is True
    text = feature_text(row["input"])
    assert "Author:" not in text and "private_author" not in text
    assert "Future gloss" not in text and "Later corrected" not in text
    assert row["provenance"]["original_call"]["created_at"] == GENERATED
    assert manifest["corpus_id"] == built["corpus_id"]
    # Rebuilding the same evidence has the same content identity, despite time/path.
    again = build_corpus(db_path, tmp_path / "corpus-again", project_root=tmp_path)
    assert again["corpus_id"] == manifest["corpus_id"]
    with pytest.raises(FileExistsError):
        build_corpus(db_path, output, project_root=tmp_path)


def test_quarantine_is_not_a_negative_label_and_automation_is_excluded(tmp_path, source):
    add, save, conn = source
    add("good")
    add("missing-call", positive=False)
    add("future-only")
    add("broken-image")
    add("automatic", positive=False, reason="auto:trivial")
    conn.execute("DELETE FROM llm_calls WHERE post_id='missing-call'")
    conn.execute("UPDATE llm_calls SET created_at='2026-05-03T00:00:00Z' WHERE post_id='future-only'")
    (tmp_path / "broken-image.png").write_text("not an image")
    output = tmp_path / "corpus"
    result = build_corpus(save(), output, project_root=tmp_path)
    assert result["counts"]["candidates"] == 4
    assert result["counts"]["included"] == 1
    assert result["counts"]["quarantined"] == 3
    assert len(list((output / "assets").iterdir())) == 1
    _, rows = load_corpus(output)
    assert [r["post_id"] for r in rows] == ["good"]


def test_duplicate_and_explicit_families_stay_together_known_cases_in_development(tmp_path, source):
    add, save, conn = source
    add("a")
    add("b", positive=False, image_copy="a")
    add("c")
    add("d", positive=False)
    conn.execute("""INSERT INTO consensus_regression
        (post_id, status, consensus_at_annotation, annotated_at) VALUES ('b', 'partial', '{}', ?)""", (REVIEWED,))
    families = tmp_path / "families.json"
    families.write_text(json.dumps({"b": "shared-joke", "c": "shared-joke"}))
    result = build_corpus(save(), tmp_path / "corpus", project_root=tmp_path, family_file=families)
    _, rows = load_corpus(tmp_path / "corpus")
    family = [r for r in rows if r["post_id"] in "abc"]
    assert len({r["group_id"] for r in family}) == 1
    assert {r["split"] for r in family} == {"development"}
    assert result["counts"]["conflicting_label_groups"] == 1
    assert result["counts"]["previously_examined_examples"] == 3
    assert next(r for r in rows if r["post_id"] == "b")["provenance"]["label_source"] == "inferred_manual"


@pytest.mark.parametrize("payload", ["examples.jsonl", "asset", "manifest.json"])
def test_integrity_checks_reject_modified_payloads(tmp_path, source, payload):
    add, save, _ = source
    add("a")
    output = tmp_path / "corpus"
    build_corpus(save(), output, project_root=tmp_path)
    if payload == "asset":
        next((output / "assets").iterdir()).write_bytes(b"altered")
    elif payload == "manifest.json":
        value = json.loads((output / payload).read_text())
        value["seed"] = "different"
        (output / payload).write_text(json.dumps(value))
    else:
        path = output / payload
        path.write_text(path.read_text().replace('"label":"accept"', '"label":"reject"'))
    with pytest.raises(ValueError, match="integrity|manifest"):
        load_corpus(output)


def test_abstention_and_metric_denominators():
    rows = [{"post_id": str(i), "input_sha256": str(i), "group_id": str(i), "label": label}
            for i, label in enumerate(["accept", "reject", "accept", "reject"])]
    results = [Decision(str(i), str(i), "test", score, decide(score, .8, .2, error=error), error=error)
               for i, (score, error) in enumerate([(.9, None), (.85, None), (.5, None), (None, "timeout")])]
    result = metrics(rows, results)
    assert result["accept_precision"] == .5
    assert result["positive_retention"] == .5
    assert result["negative_accept_rate"] == .5
    assert result["errors"] == 1 and result["deferred"] == 2
    deferred = metrics(rows, [replace(d, decision="defer", score=None) for d in results])
    assert deferred["accept_precision"] is None
    assert deferred["accept_precision_wilson95_independent_items"] is None
    with pytest.raises(ValueError):
        metrics(rows, results[:-1])
    with pytest.raises(ValueError):
        metrics(rows, [replace(results[0], input_sha256="wrong"), *results[1:]])
    with pytest.raises(ValueError):
        decide(.5, .2, .8)
    with pytest.raises(ValueError):
        decide(float("nan"), .8, .2)


def test_baseline_fits_development_only_and_never_scores_test(tmp_path, source, monkeypatch):
    pytest.importorskip("sklearn")
    import joblib
    from sklearn.pipeline import Pipeline

    add, save, _ = source
    for i in range(50):
        add(f"item{i}", positive=i % 2 == 0)
    corpus = tmp_path / "corpus"
    build_corpus(save(), corpus, project_root=tmp_path)
    _, rows = load_corpus(corpus)
    assert {r["split"] for r in rows} == {"development", "calibration", "test"}
    original_fit, original_predict = Pipeline.fit, Pipeline.predict_proba
    seen = {}

    def fit(self, x, y, **kwargs):
        seen["train"] = x
        return original_fit(self, x, y, **kwargs)

    def predict(self, x, **kwargs):
        seen["eval"] = x
        return original_predict(self, x, **kwargs)

    monkeypatch.setattr(Pipeline, "fit", fit)
    monkeypatch.setattr(Pipeline, "predict_proba", predict)
    report = run_baseline(corpus, tmp_path / "run")
    assert seen["train"] == [feature_text(r["input"]) for r in rows if r["split"] == "development"]
    assert seen["eval"] == [feature_text(r["input"]) for r in rows if r["split"] == "calibration"]
    assert report["final_test_evaluated"] is False
    # The stored estimator reproduces the exact recorded scores.
    model = joblib.load(tmp_path / "run" / "model.joblib")
    probabilities = model.predict_proba(seen["eval"])[:, list(model.classes_).index(1)]
    decisions = [json.loads(line) for line in (tmp_path / "run" / "decisions.jsonl").read_text().splitlines()]
    assert [d["score"] for d in decisions if d["model"] == "tfidf-logistic-v1"] == pytest.approx(probabilities)
    assert {d["post_id"] for d in decisions} == {r["post_id"] for r in rows if r["split"] == "calibration"}


def test_cli_build_does_not_load_credentials_or_migrate_database(tmp_path, source, monkeypatch):
    add, save, _ = source
    add("a")

    def forbidden():
        raise AssertionError("curation must not load Config or open a writable DB")

    monkeypatch.setattr("basedbench.cli._load", forbidden)
    result = CliRunner().invoke(app, ["curation", "build", "--db", str(save()), "--output", str(tmp_path / "corpus")])
    assert result.exit_code == 0, result.output
