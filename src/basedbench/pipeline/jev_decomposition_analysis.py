"""Reproducible, group-separated analysis and local visual review for issue 38.

This module reads saved experiment files only. It never makes model requests.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import html
import json
import math
from pathlib import Path
import shutil
import tempfile
from typing import Any
import warnings

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from basedbench.pipeline.curation_corpus import digest
from basedbench.pipeline import jev_decomposition_questions as questions


VERSION = "jev-decomposition-analysis-v1"
ARM_ORDER = ("broad_text", "broad_observation", "atomic", "matrix", "focused")
LEARNED = ("learned_atomic", "learned_combined")
ROUTE_THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9)
SEED = 3801

# Editorial reading order only. These notes never enter fitting or case records.
REVIEW_EXAMPLES = {
    "1jley2r-5021e767b2de5d4b": (
        "Freddie Mercury: a useful correction",
        "Your earlier note says the answer misses the specific event implied by the photo. "
        "The new method flags it for work; the single check accepted it. "
        "Does that flag capture the omission you meant?",
    ),
    "1u9z5ho-4237a9eb2faa29be": (
        "Resident Evil 4: a missed reference",
        "Your earlier note calls out the missing Resident Evil 4 connection. "
        "The answer explains square packing, but the new method accepts it anyway. "
        "Is the game reference necessary to get this joke?",
    ),
    "1u8acxi-89c345571e8428b9": (
        "Wedding question: a false alarm",
        "You previously marked this revised answer ready. The single check agrees, "
        "but the new method flags it for work. Do you still consider this answer complete?",
    ),
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _check_manifest(root: Path, manifest_name: str) -> dict:
    manifest = _json(root / manifest_name)
    identity_key = "dataset_id" if manifest_name == "manifest.json" else "manifest_id"
    if identity_key in manifest and manifest[identity_key] != digest({k: v for k, v in manifest.items() if k != identity_key}):
        raise ValueError(f"Invalid {manifest_name} identity")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError(f"Invalid {manifest_name}: no file hashes")
    for name, expected in files.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or _sha(path) != expected:
            raise ValueError(f"Hash mismatch or missing file: {name}")
    return manifest


def _label(human: Any) -> str:
    if not isinstance(human, dict):
        raise ValueError("Human judgment must be an object")
    for key in ("quality", "answer_quality", "original_quality", "label"):
        if human.get(key) in ("ready", "repair", "unclear"):
            return human[key]
    raise ValueError("Missing ready/repair/unclear human answer judgment")


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Feature or score is not a finite number")
    return float(value)


def _features(arm: dict) -> dict[str, float] | None:
    if arm.get("state") != "completed":
        return None
    raw = arm.get("features")
    if not isinstance(raw, dict):
        return None
    # A flat numeric map is the normalized runner contract. Nested maps are
    # accepted only so the saved report remains readable across runner versions.
    if any(isinstance(v, dict) for v in raw.values()):
        raw = {f"{k}.{sub}": val for k, v in raw.items() if isinstance(v, dict) for sub, val in v.items()}
    if not raw:
        return None
    return {str(k): _number(v) for k, v in raw.items()}


def _prediction(arm: dict) -> str | None:
    if arm.get("state") != "completed":
        return None
    answer = arm.get("answer_quality")
    if answer in ("pass", "ready"):
        return "pass"
    if answer in ("fail", "repair"):
        return "fail"
    if answer in ("uncertain", "unclear"):
        return "uncertain"
    return None


def _score(arm: dict) -> float | None:
    if arm.get("state") != "completed" or arm.get("score") is None:
        return None
    score = _number(arm["score"])
    if not 0 <= score <= 1:
        raise ValueError("Probability score outside [0,1]")
    return score


def _route(score: float, threshold: float = 0.8) -> str:
    if score >= threshold:
        return "pass"
    if score <= 1 - threshold:
        return "fail"
    return "uncertain"


def _metric(rows: list[dict], method: str) -> dict:
    """Use exact class and technical denominators, including unscored examples."""
    labeled = [r for r in rows if r["gold"] != "unclear"]
    unclear = [r for r in rows if r["gold"] == "unclear"]
    states = Counter(r["methods"].get(method, {}).get("state", "missing") for r in rows)
    scored = [(r, r["methods"][method]) for r in labeled
              if r["methods"].get(method, {}).get("state") == "completed"
              and r["methods"][method].get("prediction") in ("pass", "fail", "uncertain")]
    raw = [(r, m) for r, m in scored if m["prediction"] in ("pass", "fail")]
    matrix = {gold: {pred: sum(r["gold"] == gold and m["prediction"] == pred for r, m in scored)
                     for pred in ("pass", "fail", "uncertain")}
              for gold in ("ready", "repair")}
    result = {
        "all_cases": len(rows), "known": len(labeled), "unclear": len(unclear),
        "gold_counts": dict(Counter(r["gold"] for r in rows)),
        "state_counts": dict(states), "completed_known": len(scored),
        "excluded_known": len(labeled) - len(scored),
        "confusion_with_uncertain": matrix,
        "raw_binary_n": len(raw),
        "raw_binary_accuracy": (sum((r["gold"] == "ready") == (m["prediction"] == "pass") for r, m in raw) / len(raw)) if raw else None,
        "raw_binary_balanced_accuracy": None,
        "per_class_error_counts": {
            gold: {"n": sum(r["gold"] == gold for r, _ in scored),
                   "wrong": sum(r["gold"] == gold and m["prediction"] == opposite for r, m in scored),
                   "uncertain": matrix[gold]["uncertain"]}
            for gold, opposite in (("ready", "fail"), ("repair", "pass"))},
    }
    if raw and len({r["gold"] for r, _ in raw}) == 2:
        result["raw_binary_balanced_accuracy"] = float(balanced_accuracy_score(
            [r["gold"] == "ready" for r, _ in raw], [m["prediction"] == "pass" for _, m in raw]))
    probabilities = [(r, m["score"]) for r, m in scored if m.get("score") is not None]
    result["auroc_n"] = len(probabilities)
    result["auroc"] = (float(roc_auc_score([r["gold"] == "ready" for r, _ in probabilities],
                                       [s for _, s in probabilities]))
                       if len({r["gold"] for r, _ in probabilities}) == 2 else None)
    routed = [(r, m.get("route_08") or _route(score)) for r, score in probabilities for m in [r["methods"][method]]]
    result["route_08"] = {
        "n": len(routed),
        "confusion": {gold: {pred: sum(r["gold"] == gold and route == pred for r, route in routed)
                             for pred in ("pass", "fail", "uncertain")}
                      for gold in ("ready", "repair")},
    }
    risk = {}
    for threshold in ROUTE_THRESHOLDS:
        accepted = [(r, score) for r, score in probabilities if score >= threshold or score <= 1 - threshold]
        errors = sum((r["gold"] == "ready") != (score >= threshold) for r, score in accepted)
        class_counts = {gold: {"eligible": sum(r["gold"] == gold for r, _ in probabilities),
                               "accepted": sum(r["gold"] == gold for r, _ in accepted),
                               "errors": sum(r["gold"] == gold and (r["gold"] == "ready") != (score >= threshold)
                                             for r, score in accepted)}
                        for gold in ("ready", "repair")}
        risk[str(threshold)] = {"n": len(accepted), "errors": errors,
                                "coverage_known": len(accepted) / len(labeled) if labeled else None,
                                "risk": errors / len(accepted) if accepted else None,
                                "by_class": class_counts}
    result["risk_coverage"] = risk
    return result


def _fit_oof(rows: list[dict], method: str, parts: tuple[str, ...]) -> list[dict]:
    """Return fold records while adding predictions only for held-out cases."""
    eligible = []
    for row in rows:
        if row["gold"] == "unclear":
            row["methods"][method] = {"state": "excluded_unclear"}
            continue
        feature_maps = [_features(row["arms"].get(part, {})) for part in parts]
        if any(f is None for f in feature_maps):
            row["methods"][method] = {"state": "excluded_incomplete", "missing_parts": [part for part, f in zip(parts, feature_maps) if f is None]}
            continue
        flat = {f"{part}.{key}": value for part, feature in zip(parts, feature_maps) for key, value in feature.items()}
        eligible.append((row, flat))
    if not eligible:
        return []
    keys = sorted({key for _, feature in eligible for key in feature})
    if any(set(feature) != set(keys) for _, feature in eligible):
        raise ValueError(f"Inconsistent feature schema for {method}")
    if len({row["group_id"] for row, _ in eligible}) < 5:
        for row, _ in eligible:
            row["methods"][method] = {"state": "excluded_insufficient_groups"}
        return []
    x = np.array([[feature[key] for key in keys] for _, feature in eligible], dtype=float)
    y = np.array([row["gold"] == "ready" for row, _ in eligible], dtype=int)
    groups = np.array([row["group_id"] for row, _ in eligible])
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="The least populated class in y has only")
            splits = list(splitter.split(x, y, groups))
    except ValueError:
        splits = []
    if len(splits) != 5 or any(len(set(y[train])) < 2 for train, _ in splits):
        for row, _ in eligible:
            row["methods"][method] = {"state": "excluded_insufficient_classes"}
        return []
    folds = []
    for fold_id, (train, test) in enumerate(splits):
        train_groups, test_groups = set(groups[train]), set(groups[test])
        if train_groups & test_groups:
            raise AssertionError("Family leakage between train and test")
        family_counts = Counter(groups[train])
        sample_weight = np.array([1 / family_counts[groups[i]] for i in train], dtype=float)
        estimator = make_pipeline(StandardScaler(), LogisticRegression(
            C=0.1, class_weight="balanced", max_iter=2000, random_state=SEED))
        estimator.fit(x[train], y[train], logisticregression__sample_weight=sample_weight)
        scores = estimator.predict_proba(x[test])[:, 1]
        for position, score in zip(test, scores):
            row = eligible[position][0]
            row["methods"][method] = {"state": "completed", "score": float(score),
                                       "prediction": "pass" if score >= 0.5 else "fail",
                                       "route_08": _route(float(score)), "fold": fold_id}
        folds.append({"method": method, "fold": fold_id, "train_case_ids": [eligible[i][0]["case_id"] for i in train],
                      "test_case_ids": [eligible[i][0]["case_id"] for i in test],
                      "train_group_ids": sorted(str(v) for v in train_groups),
                      "test_group_ids": sorted(str(v) for v in test_groups),
                      "train_class_counts": dict(Counter("ready" if y[i] else "repair" for i in train)),
                      "test_class_counts": dict(Counter("ready" if y[i] else "repair" for i in test)),
                      "feature_ids": keys, "scaler_mean": estimator.named_steps["standardscaler"].mean_.tolist()})
    return folds


def _prepare_rows(cases: list[dict], records: list[dict]) -> list[dict]:
    if not isinstance(cases, list) or not isinstance(records, list):
        raise ValueError("Cases and records must be lists")
    by_id = {r["case_id"]: r for r in records}
    if len(by_id) != len(records) or len({c["case_id"] for c in cases}) != len(cases) or set(by_id) != {c["case_id"] for c in cases}:
        raise ValueError("Records must contain exactly one row for each dataset case")
    rows = []
    for case in cases:
        rec = by_id[case["case_id"]]
        if any(rec.get(key) != case.get(key) for key in ("post_id", "group_id", "human")):
            raise ValueError(f"Identity or human judgment drift: {case['case_id']}")
        arms = rec.get("arms")
        if not isinstance(arms, dict):
            raise ValueError("Record missing arms")
        methods = {}
        for arm in ARM_ORDER:
            payload = arms.get(arm, {"state": "missing"})
            state = payload.get("state", "missing")
            if state not in ("completed", "held", "technical_error", "missing"):
                raise ValueError(f"Unknown arm state: {state}")
            prediction = _prediction(payload)
            methods[arm] = {"state": state, "prediction": prediction, "score": _score(payload)}
            if state == "completed" and arm != "matrix" and prediction is None:
                raise ValueError(f"Completed {arm} has no answer verdict")
            if state == "completed" and arm in ("atomic", "focused"):
                actual = _features(payload)
                if actual is None or set(actual) != set(questions.FEATURE_IDS):
                    raise ValueError(f"Invalid fixed 48-feature identity: {case['case_id']} {arm}")
            if state == "completed" and arm == "matrix":
                actual = _features(payload)
                if actual is None or set(actual) != set(questions.MATRIX_SUMMARY_IDS):
                    raise ValueError(f"Invalid fixed matrix summary identity: {case['case_id']}")
            if arm == "atomic":
                # Atomic answer_quality is the frozen rule. Its stored score is
                # the separate broad Choice from the same request, never a
                # probability for the rule's verdict.
                methods[arm]["broad_choice_score"] = methods[arm]["score"]
                methods[arm]["score"] = None
        rows.append({"case_id": case["case_id"], "post_id": case["post_id"],
                     "group_id": case["group_id"], "human": case["human"],
                     "gold": _label(case["human"]), "input": case["input"],
                     "image_path": case.get("image_path"), "image_error": case.get("image_error"),
                     "comments": case.get("comments", []), "observation": rec.get("observation"),
                     "selected_comment_ids": rec.get("selected_comment_ids", []),
                     "selection_metadata": rec.get("selection_metadata"),
                     "arms": arms, "methods": methods})
    return rows


def _priority(row: dict) -> tuple:
    if row["gold"] == "unclear":
        rank = 4
    else:
        expected = "pass" if row["gold"] == "ready" else "fail"
        broad = row["methods"]["broad_observation"]["prediction"]
        best = row["methods"].get("learned_combined", {}).get("prediction")
        if broad != expected and best == expected:
            rank = 0  # candidate architecture win
        elif best not in (None, expected):
            rank = 1  # held-out learned error
        elif any(row["methods"][name]["prediction"] not in (None, expected) for name in ("broad_text", "atomic", "focused")):
            rank = 2
        else:
            rank = 3
    return rank, hashlib.sha256(f"review-v1:{row['case_id']}".encode()).hexdigest()


def _display(value: Any) -> str:
    if isinstance(value, str):
        return html.escape(value, quote=True)
    return html.escape(json.dumps(value, ensure_ascii=False, sort_keys=True), quote=True)


def _human_markup(human: dict, gold: str) -> str:
    events = human.get("events") if isinstance(human.get("events"), list) else []
    notes = [(event.get("quality"), event["notes"]) for event in events
             if isinstance(event, dict) and isinstance(event.get("notes"), str) and event["notes"]]
    if notes:
        note_markup = "".join(f'<li><small>{_display(quality or "judgment")}</small><p>{_display(note)}</p></li>'
                              for quality, note in notes)
        note_markup = f'<ol class="human-notes">{note_markup}</ol>'
    else:
        note_markup = '<p class="quiet">No written note was recorded for this judgment.</p>'
    return (f'<h3>Human answer judgment</h3><p class="judgment">{_display(gold)}</p>'
            f'<h3>Exact human notes</h3>{note_markup}'
            f'<details><summary>Full human judgment and provenance ({len(events)} event{"s" if len(events) != 1 else ""})</summary>'
            f'<pre>{_display(human)}</pre></details>')


def _observation_markup(observation: Any) -> str:
    heading = '<h3>Machine image observation <small>fallible; not human ground truth</small></h3>'
    if not isinstance(observation, dict):
        return heading + '<p class="quiet">No image observation was available.</p>'
    uncertainties = observation.get("uncertainties", [])
    if not isinstance(uncertainties, list):
        uncertainties = []
    uncertainty_markup = ("".join(f'<li>{_display(item)}</li>' for item in uncertainties)
                          if uncertainties else '<li>None recorded.</li>')
    return (heading + f'<dl class="observation"><dt>Visible text</dt><dd>{_display(observation.get("visible_text", ""))}</dd>'
            f'<dt>Visible scene</dt><dd>{_display(observation.get("visible_scene", ""))}</dd>'
            f'<dt>Uncertainties</dt><dd><ul>{uncertainty_markup}</ul></dd></dl>'
            f'<details><summary>Full machine observation JSON</summary><pre>{_display(observation)}</pre></details>')


def _comparison_markup(rows: list[dict]) -> str:
    """Compare both methods on the same available, human-labeled cases."""
    names = ("broad_observation", "learned_combined")
    matched = [r for r in rows if r["gold"] in ("ready", "repair") and all(
        r["methods"].get(name, {}).get("state") == "completed"
        and r["methods"][name].get("prediction") in ("pass", "fail", "uncertain") for name in names)]
    if not matched:
        return '<p>No completed matched comparison is available.</p>'
    counts = {name: {gold: sum(r["gold"] == gold and r["methods"][name]["prediction"] == "fail"
                              for r in matched) for gold in ("ready", "repair")} for name in names}
    totals = Counter(r["gold"] for r in matched)
    caught_delta = counts[names[1]]["repair"] - counts[names[0]]["repair"]
    false_delta = counts[names[1]]["ready"] - counts[names[0]]["ready"]
    def change(value: int) -> str:
        return f'{abs(value)} {"more" if value >= 0 else "fewer"}'
    comparison = (f'The combined method caught <strong>{change(caught_delta)} answers needing work</strong> '
                  f'and wrongly flagged <strong>{change(false_delta)} previously accepted answers</strong>.')
    uncertain = sum(r["methods"][name]["prediction"] == "uncertain" for r in matched for name in names)
    exclusions = len(rows) - len(matched)
    return (f'<p class="takeaway">{comparison}</p>'
            '<table class="comparison"><thead><tr><th scope="col">Compared with your earlier judgments</th>'
            '<th scope="col">One overall check</th><th scope="col">Many checks combined</th></tr></thead><tbody>'
            f'<tr><th scope="row">Answers needing work caught<br><small>Higher is better</small></th>'
            f'<td>{counts[names[0]]["repair"]} of {totals["repair"]}</td>'
            f'<td>{counts[names[1]]["repair"]} of {totals["repair"]}</td></tr>'
            f'<tr><th scope="row">Accepted answers wrongly flagged<br><small>Lower is better</small></th>'
            f'<td>{counts[names[0]]["ready"]} of {totals["ready"]}</td>'
            f'<td>{counts[names[1]]["ready"]} of {totals["ready"]}</td></tr></tbody></table>'
            f'<p class="quiet">Same {len(matched)} answers in both columns. '
            f'{exclusions} other versions lack a clear human judgment or a completed comparison.'
            f'{" Uncertain decisions count as neither a catch nor a false alarm." if uncertain else ""}</p>')


def _verdict(value: str | None) -> str:
    # These are display labels for model verdicts, not authentication values.
    return {"ready": "Looks complete", "pass": "Looks complete", "repair": "Needs work",  # nosec B105
            "fail": "Needs work", "unclear": "Uncertain", "uncertain": "Uncertain"}.get(value, "Unavailable")


def _render(rows: list[dict], summary: dict, output: Path, dataset: Path) -> None:
    asset_dir = output / "assets"
    asset_dir.mkdir()
    cards = []
    ordered = sorted(rows, key=_priority)
    # The review shortlist must include failures as well as apparent wins.
    shortlist = [r for r in ordered if _priority(r)[0] == 0][:6]
    shortlist += [r for r in ordered if _priority(r)[0] == 1][:6]
    prioritized = {r["case_id"] for r in shortlist}
    for row in ordered:
        if len(prioritized) >= 12:
            break
        prioritized.add(row["case_id"])
    guided_ids = [case_id for case_id in REVIEW_EXAMPLES if any(r["case_id"] == case_id for r in rows)]
    if not guided_ids:
        guided_ids = [r["case_id"] for r in shortlist[:3] or ordered[:3]]
    guide_order = {case_id: i for i, case_id in enumerate(guided_ids)}
    for row in sorted(rows, key=lambda r: (guide_order.get(r["case_id"], len(guided_ids)), _priority(r))):
        tags = [row["gold"]]
        if row["case_id"] in guide_order:
            tags.append("guided")
        if row["case_id"] in prioritized:
            tags.append("priority")
        if any(v["state"] in ("technical_error", "held", "missing", "excluded_incomplete")
               for v in row["methods"].values()):
            tags.append("technical")
        image_markup = ""
        image = row.get("image_path")
        if image:
            source = Path(image)
            if not source.resolve().is_relative_to(dataset.resolve()):
                raise ValueError("Image path escapes dataset")
            if not source.is_file():
                raise ValueError("Missing review image")
            name = source.name
            target = asset_dir / name
            if target.exists() and _sha(target) != _sha(source):
                raise ValueError("Conflicting image asset names")
            if not target.exists():
                shutil.copyfile(source, target)
            image_markup = f'<img src="assets/{html.escape(name, quote=True)}" alt="Meme image for case {html.escape(str(row["case_id"]), quote=True)}">'
        method_rows = []
        for name in (*ARM_ORDER, *LEARNED):
            value = row["methods"].get(name, {"state": "missing"})
            raw = row["arms"].get(name, {})
            signal = raw.get("features", {})
            if raw.get("error"):
                signal = {"error": raw["error"], "features": signal}
            score = value.get("score") if name != "atomic" else value.get("broad_choice_score")
            method_rows.append(f'<tr><th>{_display(name)}</th><td>{_display(value.get("state"))}</td>'
                               f'<td>{_display(value.get("prediction"))}</td><td>{"—" if score is None else f"{score:.3f}"}{" (broad)" if name == "atomic" and score is not None else ""}</td>'
                               f'<td><details><summary>Signals</summary><pre>{_display(signal)}</pre></details></td></tr>')
        selected_ids = set(row.get("selected_comment_ids") or [])
        repeats = [v for v in summary.get("runtime", {}).get("repeat_deltas", []) if v.get("case_id") == row["case_id"]]
        singles = [v for v in summary.get("runtime", {}).get("batch_single_deltas", []) if v.get("case_id") == row["case_id"]]
        comments = "".join(f'<li class="{"selected" if c.get("id") in selected_ids else ""}"><b>{_display(c.get("id"))}</b> '
                           f'{"<em>selected</em> " if c.get("id") in selected_ids else ""}{_display(c.get("text"))}</li>'
                           for c in row["comments"])
        example = REVIEW_EXAMPLES.get(row["case_id"])
        title = example[0] if example else f'Post {row["post_id"]}'
        if row["case_id"] in guide_order:
            title = f'{guide_order[row["case_id"]] + 1}. {title}'
        note = f'<p class="review-note">{_display(example[1])}</p>' if example else ""
        decisions = [("Your earlier judgment", _verdict(row["gold"]))]
        decisions += [(label, _verdict(row["methods"].get(name, {}).get("prediction"))) for name, label in
                      (("broad_observation", "One overall check"), ("learned_combined", "Many checks combined"))]
        decisions_markup = "".join(f'<tr><th scope="row">{label}</th><td>{verdict}</td></tr>'
                                   for label, verdict in decisions)
        cards.append(f'<article class="case" id="{html.escape(str(row["case_id"]), quote=True)}" data-tags="{html.escape(" ".join(tags), quote=True)}"'
                     f'{"" if "guided" in tags else " hidden"}>'
                     f'<header><h2>{_display(title)}</h2></header>'
                     f'<div class="body"><div class="visual">{image_markup}<p>{_display(row.get("image_error") or "")}</p></div>'
                     f'<div class="narrative"><h3>Answer being checked</h3><p>{_display(row["input"].get("explanation", ""))}</p>'
                     f'<table class="decisions" aria-label="Answer judgments"><tbody>{decisions_markup}</tbody></table>{note}'
                     f'<details><summary>Your earlier notes</summary>{_human_markup(row["human"], row["gold"])}</details>'
                     f'<details><summary>Supporting comments ({len(row["comments"])})</summary><ol>{comments}</ol></details>'
                     f'<details class="technical"><summary>Model details and exact record</summary>'
                     f'<p>Post {_display(row["post_id"])} · answer version {_display(row["case_id"])} · group {_display(row["group_id"])}</p>'
                     f'{_observation_markup(row.get("observation"))}'
                     f'<h3>Method decisions</h3><table><thead><tr><th>Method</th><th>State</th><th>Decision</th><th>P(pass)</th><th>Detail</th></tr></thead>'
                     f'<tbody>{"".join(method_rows)}</tbody></table>'
                     '<p class="quiet">Combined verdicts use the fixed 0.5 threshold. These scores are not calibrated probabilities of correctness. '
                     'The atomic score belongs to its separate broad check, not its rule verdict.</p>'
                     f'<h3>Selected evidence IDs</h3><p>{_display(row.get("selected_comment_ids"))}</p>'
                     f'<details><summary>Selection scores and repeat measurements</summary><pre>{_display({"selection": row.get("selection_metadata"), "repeats": repeats, "batch_vs_single": singles})}</pre></details>'
                     '</details></div></div></article>')
    css = """
*{box-sizing:border-box}body{margin:0;background:#f4f1eb;color:#211f1a;font:16px/1.55 system-ui,sans-serif}
main{max-width:1160px;margin:auto;padding:2rem}h1{font-size:2.3rem;line-height:1.2;margin:.2rem 0 1rem}
h2{margin:.2rem 0;color:#204c42;font-size:1.3rem}h3{margin:1.1rem 0 .3rem;font-size:1rem}
h3 small,th small{font-weight:400;color:#625f57}.intro{max-width:75ch;font-size:1.1rem}
.takeaway{max-width:75ch}.conclusion{padding:1.1rem 1.4rem;border-left:4px solid #204c42;background:#e8eeea;margin:1.5rem 0}
.conclusion p{margin:.3rem 0}.review-intro{margin:2rem 0 1rem;max-width:78ch}
.toolbar{display:flex;gap:.6rem;flex-wrap:wrap;align-items:center;margin:1rem 0}
button,input{font:inherit;border:1px solid #adab9f;border-radius:7px;background:white;padding:.5rem .8rem}
button{cursor:pointer}button.active{background:#204c42;color:white}input{max-width:100%}
:focus-visible{outline:3px solid #a66b23;outline-offset:3px}[hidden]{display:none!important}
.case{background:white;border:1px solid #d8d2c6;border-radius:12px;margin:1.3rem 0;overflow:hidden;scroll-margin-top:1rem}
.case header{background:#e9e5db;padding:.9rem 1.2rem}.body{display:grid;grid-template-columns:minmax(240px,36%) 1fr;gap:1.5rem;padding:1.2rem}
.visual img{width:100%;height:auto;object-fit:contain;max-height:560px;background:#eee}
.narrative>h3:first-child{margin-top:0}.narrative p,.narrative pre{overflow-wrap:anywhere;white-space:pre-wrap}
.review-note{padding:.85rem 1rem;background:#f8f3e7;border-left:3px solid #bd9761}
pre{background:#f7f6f2;padding:.7rem;border-radius:6px;font:12px/1.5 ui-monospace,monospace;overflow-wrap:anywhere;white-space:pre-wrap}
.judgment{display:inline-block;margin:.2rem 0;padding:.2rem .7rem;background:#e4f2eb;color:#204c42;border-radius:2rem;font-weight:700}
.human-notes{margin:.3rem 0 1rem;padding-left:1.3rem}.human-notes li{margin:.5rem 0;padding:.6rem;background:#f9f6ef}
.human-notes p{margin:.2rem 0;white-space:pre-wrap}.human-notes small,.quiet{color:#67635c}.quiet{font-size:.9rem}
.observation{display:grid;grid-template-columns:7.5rem 1fr;gap:.4rem .8rem;margin:.4rem 0 1rem;padding:.8rem;background:#f2f5f4;border-radius:6px}
.observation dt{font-weight:700;color:#29534b}.observation dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}.observation ul{margin:0;padding-left:1.2rem}
table{width:100%;border-collapse:collapse;font-size:.9rem}th,td{text-align:left;border-bottom:1px solid #ddd8cc;padding:.55rem;vertical-align:top}
.comparison{max-width:850px}.comparison td{font-size:1.2rem;font-weight:650}.comparison th:first-child{width:48%}
.decisions{margin:1.2rem 0}.decisions td{font-weight:650}.decisions tr:last-child{background:#e8eeea}
td pre{max-height:180px;overflow:auto}details{margin:.7rem 0}summary{cursor:pointer;color:#205b51}
.selected{background:#e4f2eb}.selected em{color:#1c694c;font-weight:700;font-style:normal}.technical{font-size:.9rem}
@media(max-width:760px){main{padding:1rem}h1{font-size:1.9rem}.body{grid-template-columns:1fr}.observation{grid-template-columns:1fr}table{font-size:.8rem}.technical table{display:block;overflow-x:auto}.comparison th:first-child{width:44%}.comparison td{font-size:1rem}}
"""
    script = """
const buttons=[...document.querySelectorAll('[data-filter]')];
const cards=[...document.querySelectorAll('.case')];
const query=document.querySelector('#search');let filter='guided';
function refresh(){
  const q=query.value.toLowerCase();let count=0;
  for(const c of cards){const ok=(filter==='all'||c.dataset.tags.split(' ').includes(filter))&&c.textContent.toLowerCase().includes(q);c.hidden=!ok;if(ok)count++}
  for(const b of buttons)b.classList.toggle('active',b.dataset.filter===filter);
  document.querySelector('#search-controls').hidden=filter!=='all';
  document.querySelector('#shown').textContent=`${count} example${count===1?'':'s'} shown`;
}
for(const b of buttons)b.addEventListener('click',()=>{filter=b.dataset.filter;query.value='';refresh()});
query.addEventListener('input',refresh);
function revealLink(){
  let id;try{id=decodeURIComponent(location.hash.slice(1))}catch{return}
  const target=cards.find(c=>c.id===id);if(!target)return;
  if(!target.dataset.tags.split(' ').includes(filter)){filter='all'}
  query.value='';refresh();target.scrollIntoView({block:'start'});
}
window.addEventListener('hashchange',revealLink);refresh();revealLink();
"""
    runtime = summary.get("runtime", {})
    cost = runtime.get("accounted_usd")
    cost_text = f"about ${cost:.2f}" if isinstance(cost, (int, float)) else "cost unavailable"
    question_count = runtime.get("questions")
    question_text = f"{question_count:,}" if isinstance(question_count, int) else "many"
    guide_count = len(guided_ids)
    markup = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>What did we learn from Jev?</title><style>{css}</style><main>
<h1>What did we learn from Jev?</h1>
<p class="intro">Lots of small checks are cheap. Combining them into a reliable answer judge still needs work.</p>
<p>We asked Jev to <strong>check existing meme explanations</strong>: does each answer get the joke?
We compared one overall check with a method that combines many smaller checks.</p>
{_comparison_markup(rows)}
<div class="conclusion"><p><strong>My recommendation: keep experimenting with Jev; keep human review for answer quality.</strong></p>
<p>The whole experiment ran {question_text} Jev judgments for {cost_text}, including image descriptions.
The current combined method still makes too many mistakes to use automatically.</p></div>
<details><summary>What these results do and don’t establish</summary>
<p>This used existing development labels. It tells us how the methods behaved on these cases; it does not establish accuracy on new memes.
Both columns used the same machine image descriptions. Those descriptions can miss details.
The combined method used checks of the answer, its supporting comments, and a second pass with selected comments.</p>
<p>Related meme versions were kept together when training and checking the combined method.
Its displayed decisions use the predeclared 0.5 threshold. Your labels and exact notes are unchanged.</p>
<details><summary>Call counts, latency and accounting</summary><pre>{_display(runtime)}</pre></details></details>
<section class="review-intro"><h2>Start with these {guide_count} examples</h2>
<p>Look at each meme and the answer being checked. <strong>Tell me in chat whether the new decision makes sense</strong>
and what the answer misses, if anything. You can reply with the example number and a sentence.</p>
<p class="quiet">The short prompts below are my interpretation of your earlier feedback, for you to check.
You don’t need to review all {len(rows)} versions. Issue #38 remains open for your review.</p></section>
<div class="toolbar" aria-label="Review examples">
<button data-filter="guided" class="active">Start here ({guide_count})</button>
<button data-filter="all">Browse all {len(rows)}</button><span id="shown" class="quiet" aria-live="polite"></span></div>
<div id="search-controls" hidden><input id="search" type="search" placeholder="Find text or a post ID" aria-label="Search all cases"></div>
{''.join(cards)}
</main><script>{script}</script></html>"""
    (output / "index.html").write_text(markup, encoding="utf-8")



def prepare(root: Path | str, output: Path | str) -> dict:
    """Verify a completed saved run, then make immutable analysis and review files."""
    root, output = Path(root), Path(output)
    if output.exists():
        raise FileExistsError("Use a new analysis output directory")
    dataset = root / "dataset"
    _check_manifest(dataset, "manifest.json")
    records_manifest = _check_manifest(root, "records-manifest.json")
    if records_manifest["files"].get("dataset/manifest.json") != _sha(dataset / "manifest.json"):
        raise ValueError("Dataset manifest was not bound to records")
    cases, records, plan, runtime = (_json(dataset / "cases.json"), _json(root / "records.json"),
                                    _json(root / "plan.json"), _json(root / "runtime_report.json"))
    if plan.get("dataset_manifest_sha256") != _sha(dataset / "manifest.json"):
        raise ValueError("Plan dataset hash mismatch")
    if plan.get("experiment_id") != digest({k: v for k, v in plan.items() if k != "experiment_id"}):
        raise ValueError("Plan identity mismatch")
    if runtime.get("experiment_id") != plan.get("experiment_id"):
        raise ValueError("Runtime report does not belong to this plan")
    if not runtime.get("complete") and runtime.get("stop_reason") not in ("budget_cap", "call_ceiling"):
        raise ValueError("Run is incomplete without a declared budget or call cap stop")
    rows = _prepare_rows(cases, records)
    folds = []
    folds.extend(_fit_oof(rows, "learned_atomic", ("atomic",)))
    folds.extend(_fit_oof(rows, "learned_combined", ("atomic", "matrix", "focused")))
    methods = {name: _metric(rows, name) for name in (*ARM_ORDER, *LEARNED) if name != "matrix"}
    summary = {"version": VERSION, "experiment_id": plan.get("experiment_id"),
               "case_count": len(rows), "known_group_count": len({r["group_id"] for r in rows}),
               "methods": methods, "runtime": runtime, "partial_due_to_cap": not runtime.get("complete"),
               "limitations": ["Exposed development cases; group separation prevents direct overlap, not design exposure.",
                               "Human unclear labels are excluded from fitting and accuracy denominators.",
                               "Image observations are fallible machine evidence; held image arms remain in denominators."]}
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".jev-analysis-", dir=output.parent))
    try:
        _write(staging / "cases.json", rows)
        _write(staging / "folds.json", folds)
        _write(staging / "summary.json", summary)
        _render(rows, summary, staging, dataset)
        manifest = {"version": VERSION, "source_manifest_sha256": _sha(root / "records-manifest.json"),
                    "code_sha256": _sha(Path(__file__)),
                    "files": {str(p.relative_to(staging)): _sha(p) for p in sorted(staging.rglob("*")) if p.is_file()}}
        manifest["analysis_id"] = digest(manifest)
        _write(staging / "manifest.json", manifest)
        staging.rename(output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.root, args.output), indent=2))
