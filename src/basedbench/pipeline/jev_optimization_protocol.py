"""Frozen, local-only case and scoring protocol for the bounded Jev search."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile

from sklearn.model_selection import StratifiedGroupKFold


VERSION = 1
BUDGETS = {
    "budget_total_usd": 5,
    "budget_search_usd": 4,
    "max_provider_calls": 4000,
    "final_call_reserve": 800,
    "max_questions": 500000,
    "final_question_reserve": 80000,
    "max_case_evaluations": 1200,
    "final_evaluation_reserve": 188,
}
_SOURCES = (
    "dataset/manifest.json", "dataset/cases.json", "analysis/manifest.json",
    "analysis/cases.json", "analysis/folds.json",
)
_LABEL_TO_VERDICT = {"ready": "pass", "repair": "fail"}
_VERDICTS = {"pass", "fail", "uncertain"}


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _identity(value: dict) -> str:
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _source_hashes(source_root: Path) -> dict[str, str]:
    hashes = {}
    for name in _SOURCES:
        path = source_root / name
        if not path.is_file():
            raise ValueError(f"Missing frozen source: {name}")
        hashes[str(path.resolve())] = _hash(path)
    control = source_root.parent / "jev-optimization-groundwork" / "threshold-control.json"
    if not control.is_file():
        raise ValueError("Missing frozen threshold control")
    hashes[str(control.resolve())] = _hash(control)
    return hashes


def _verify_manifest(path: Path, identity: str) -> None:
    manifest = _read(path)
    if manifest.get(identity) != _identity({k: v for k, v in manifest.items() if k != identity}):
        raise ValueError(f"Source manifest identity changed: {path}")
    base = path.parent.resolve()
    for name, expected in manifest.get("files", {}).items():
        target = (base / name).resolve()
        if not target.is_relative_to(base) or not target.is_file() or _hash(target) != expected:
            raise ValueError(f"Frozen source changed: {name}")


def _baseline(control: dict, case_id: str) -> dict:
    row = control[case_id]
    return {"broad": row["broad_native"], "combined": row["frozen_combined"],
            "calibrated": row["calibrated"]}


def _assert_group_split(parts: tuple[list[str], ...], cases: dict[str, dict]) -> None:
    ids = [set(part) for part in parts]
    if any(len(part) != len(ids[i]) for i, part in enumerate(parts)):
        raise ValueError("Duplicate case in split")
    if any(ids[i] & ids[j] for i in range(len(ids)) for j in range(i + 1, len(ids))):
        raise ValueError("Case leakage between partitions")
    groups = [{cases[c]["group_id"] for c in part} for part in parts]
    if any(groups[i] & groups[j] for i in range(len(groups)) for j in range(i + 1, len(groups))):
        raise ValueError("Family leakage between partitions")


def _weights(ids: list[str], cases: dict[str, dict]) -> dict[str, float]:
    """Balance classes, then families inside each class; mean weight is one."""
    by_class = Counter(cases[c]["gold"] for c in ids)
    by_family = Counter((cases[c]["gold"], cases[c]["group_id"]) for c in ids)
    families_per_class = Counter({label: len({cases[c]["group_id"] for c in ids if cases[c]["gold"] == label})
                                  for label in by_class})
    if set(by_class) != {"ready", "repair"}:
        raise ValueError("Every partition needs both known classes")
    raw = {c: 1 / (len(by_class) * families_per_class[cases[c]["gold"]]
                    * by_family[(cases[c]["gold"], cases[c]["group_id"])]) for c in ids}
    scale = len(ids) / sum(raw.values())
    return {c: raw[c] * scale for c in ids}


def _examples(ids: list[str], partition: str, cases: dict[str, dict]) -> list[dict]:
    weights = _weights(ids, cases)
    return [{"case_id": c, "partition": partition, "weight": weights[c]} for c in ids]


def prepare(source_root: Path | str, root: Path | str) -> dict:
    """Freeze exact source versions and group-safe splits, publishing atomically."""
    source_root, root = Path(source_root).resolve(), Path(root).absolute()
    if root.exists():
        raise FileExistsError("Never overwrite a frozen optimization plan")
    if root.resolve().is_relative_to(source_root):
        raise ValueError("Output cannot be inside frozen source")
    _verify_manifest(source_root / "dataset/manifest.json", "dataset_id")
    _verify_manifest(source_root / "analysis/manifest.json", "analysis_id")
    hashes = _source_hashes(source_root)
    raw = _read(source_root / "analysis/cases.json")
    source_cases = _read(source_root / "dataset/cases.json")
    if len(raw) != 99 or {r["case_id"] for r in raw} != {r["case_id"] for r in source_cases}:
        raise ValueError("Expected exact 99 source versions")
    control_data = _read(source_root.parent / "jev-optimization-groundwork/threshold-control.json")
    control = {r["case_id"]: r for r in control_data["cases"]}
    folds_saved = sorted((f for f in _read(source_root / "analysis/folds.json")
                          if f.get("method") == "learned_combined"), key=lambda f: f["fold"])
    if len(folds_saved) != 5 or [f["fold"] for f in folds_saved] != list(range(5)):
        raise ValueError("Expected five saved learned_combined folds")
    cases, excluded = [], []
    for row in raw:
        cid = row["case_id"]
        reason = ("unknown_label" if row["gold"] not in _LABEL_TO_VERDICT else
                  "image_incomplete" if row.get("image_error") or row["arms"]["broad_observation"]["state"] != "completed" else None)
        if reason:
            excluded.append({"case_id": cid, "reason": reason,
                             "detail": row.get("image_error") or row["arms"]["broad_observation"]["state"]})
            continue
        if cid not in control:
            raise ValueError(f"Missing baseline control: {cid}")
        comments = [{"id": comment["id"], "text": comment["text"]} for comment in row["comments"]]
        observation = {key: row["observation"][key] for key in
                       ("visible_text", "visible_scene", "uncertainties") if key in row["observation"]}
        cases.append({"case_id": cid, "group_id": row["group_id"], "gold": row["gold"],
                      "input": {"explanation": row["input"]["explanation"]},
                      "comments": comments, "observation": observation,
                      "image_error": None, "baseline": _baseline(control, cid)})
    cases.sort(key=lambda r: r["case_id"])
    if len(cases) != 94 or len(excluded) != 5 or Counter(r["gold"] for r in cases) != {"ready": 77, "repair": 17}:
        raise ValueError("Frozen eligible/excluded composition changed")
    lookup = {r["case_id"]: r for r in cases}
    eligible = set(lookup)
    folds = []
    for saved in folds_saved:
        outer_train, test = saved["train_case_ids"], saved["test_case_ids"]
        if set(outer_train) | set(test) != eligible:
            raise ValueError("Saved fold does not cover eligible cases")
        _assert_group_split((outer_train, test), lookup)
        ordered = sorted(outer_train)
        y = [lookup[c]["gold"] for c in ordered]
        groups = [lookup[c]["group_id"] for c in ordered]
        inner_train_idx, val_idx = next(StratifiedGroupKFold(n_splits=3, shuffle=True,
                                                               random_state=4001).split(ordered, y, groups))
        train = [ordered[i] for i in inner_train_idx]
        val = [ordered[i] for i in val_idx]
        _assert_group_split((train, val, test), lookup)
        folds.append({"fold": saved["fold"], "train_ids": train, "val_ids": val,
                      "test_ids": list(test)})
    if Counter(cid for fold in folds for cid in fold["test_ids"]) != Counter({cid: 1 for cid in eligible}):
        raise ValueError("Each eligible case must be outer-test exactly once")
    root.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{root.name}.", dir=root.parent))
    try:
        _write(stage / "cases.json", cases)
        plan = {"version": VERSION, "cases_file": str((root / "cases.json").resolve()),
                "cases_sha256": _hash(stage / "cases.json"), "source_hashes": hashes,
                "case_ids": sorted(eligible), "folds": folds, "excluded": sorted(excluded, key=lambda r: r["case_id"]),
                "baseline_controls": control_data["totals"], **BUDGETS}
        plan["plan_id"] = _identity(plan)
        _write(stage / "plan.json", plan)
        os.replace(stage, root)
        return plan
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def load(root: Path | str) -> tuple[dict, dict[str, dict]]:
    root = Path(root).resolve()
    plan = _read(root / "plan.json")
    if plan.get("version") != VERSION or plan.get("plan_id") != _identity({k: v for k, v in plan.items() if k != "plan_id"}):
        raise ValueError("Optimization plan identity changed")
    if plan.get("cases_file") != str(root / "cases.json") or _hash(root / "cases.json") != plan.get("cases_sha256"):
        raise ValueError("Frozen cases file changed")
    if any(plan.get(k) != v for k, v in BUDGETS.items()):
        raise ValueError("Budget constants changed")
    for path, expected in plan["source_hashes"].items():
        source = Path(path)
        if not source.is_file() or _hash(source) != expected:
            raise ValueError(f"Frozen source changed: {path}")
    rows = _read(root / "cases.json")
    cases = {r["case_id"]: r for r in rows}
    if len(cases) != 94 or sorted(cases) != plan["case_ids"]:
        raise ValueError("Frozen case IDs changed")
    for fold in plan["folds"]:
        _assert_group_split((fold["train_ids"], fold["val_ids"], fold["test_ids"]), cases)
        if set(fold["train_ids"] + fold["val_ids"] + fold["test_ids"]) != set(cases):
            raise ValueError("Fold coverage changed")
    return plan, cases


def example_sets(plan: dict, cases_by_id: dict[str, dict], fold_id: int) -> tuple[list[dict], list[dict], list[dict]]:
    fold = next((f for f in plan["folds"] if f["fold"] == fold_id), None)
    if fold is None:
        raise ValueError(f"Unknown fold: {fold_id}")
    _assert_group_split((fold["train_ids"], fold["val_ids"], fold["test_ids"]), cases_by_id)
    return tuple(_examples(fold[key], partition, cases_by_id) for key, partition in
                 (("train_ids", "train"), ("val_ids", "val"), ("test_ids", "test")))


def score(example: dict, row: dict, pred: str | dict) -> float:
    if example["case_id"] != row["case_id"] or example["partition"] not in {"train", "val", "test"}:
        raise ValueError("Example and row mismatch")
    prediction = pred.get("prediction") if isinstance(pred, dict) else pred
    if prediction not in _VERDICTS:
        raise ValueError("Invalid prediction")
    weight = example["weight"]
    if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight <= 0:
        raise ValueError("Invalid example weight")
    return float(weight) if prediction == _LABEL_TO_VERDICT[row["gold"]] else 0.0


def feedback(example: dict, row: dict, result: dict) -> dict:
    if example["case_id"] != row["case_id"]:
        raise ValueError("Example and row mismatch")
    if example["partition"] != "train":
        return {}
    # Build from a strict allowlist. Local human notes and provenance are never copied.
    trace = result.get("trace") or {}
    columns = ("unit_id", "comment_id", "start", "end", "role", "need", "coverage",
               "p_essential", "p_covered", "p_missing", "p_contradicted", "essential")
    units = []
    for unit in trace.get("units", []):
        if isinstance(unit, dict):
            source = unit.get("unit", unit)
            role = unit.get("role") or {}
            need = unit.get("need") or {}
            coverage = unit.get("coverage") or {}
            units.append([source.get("id"), source.get("comment_id"), source.get("start"),
                          source.get("end"), role.get("choice"), need.get("choice"),
                          coverage.get("choice"), (need.get("probabilities") or {}).get("essential"),
                          (coverage.get("probabilities") or {}).get("covered"),
                          (coverage.get("probabilities") or {}).get("missing"),
                          (coverage.get("probabilities") or {}).get("contradicted"),
                          unit.get("essential")])
    compact_trace = {"columns": columns, "rows": units}
    for key in ("reason_codes", "reason", "verdict", "aggregation", "adequacy", "essential_count"):
        if key in trace:
            value = trace[key]
            compact_trace[key] = value.get("choice") if key == "adequacy" and isinstance(value, dict) else value
    return {"input": {"explanation": row["input"]["explanation"],
                      "comments": [{"id": comment["id"], "text": comment["text"]}
                                   for comment in row["comments"]],
                      "observation": {key: row["observation"][key] for key in
                                      ("visible_text", "visible_scene", "uncertainties")
                                      if key in row["observation"]}},
            "trace": compact_trace,
            "prediction": result.get("prediction"),
            "expected": _LABEL_TO_VERDICT[row["gold"]]}


def summarize(cases: dict[str, dict] | list[dict], records: list[dict]) -> dict:
    """Compare saved controls and seed/optimized outer decisions on matched cases."""
    lookup = cases if isinstance(cases, dict) else {r["case_id"]: r for r in cases}
    if len(lookup) != 94:
        raise ValueError("Summary requires all 94 eligible cases")
    by_method = {method: {} for method in ("broad", "combined", "calibrated", "seed", "optimized")}
    for cid, row in lookup.items():
        for method in ("broad", "combined", "calibrated"):
            by_method[method][cid] = row["baseline"][method]
    for item in records:
        method, cid, prediction = item["method"], item["case_id"], item["prediction"]
        if method not in ("seed", "optimized") or cid not in lookup or prediction not in _VERDICTS:
            raise ValueError("Invalid outer decision record")
        if cid in by_method[method]:
            raise ValueError("Duplicate outer decision")
        by_method[method][cid] = prediction
    metrics = {}
    for method, decisions in by_method.items():
        counts = {gold: dict(Counter(decisions[cid] for cid, row in lookup.items()
                                     if row["gold"] == gold and cid in decisions))
                  for gold in ("ready", "repair")}
        repair_groups = {lookup[cid]["group_id"] for cid, p in decisions.items()
                         if lookup[cid]["gold"] == "repair" and p == "fail"}
        metrics[method] = {"evaluated": len(decisions), "counts": counts,
                           "ready_passes": counts["ready"].get("pass", 0),
                           "ready_rejections": counts["ready"].get("fail", 0),
                           "repair_catches": counts["repair"].get("fail", 0),
                           "repair_families_caught": len(repair_groups),
                           "decided_coverage": sum(p != "uncertain" for p in decisions.values()) / 94}
    family_labels = defaultdict(set)
    for row in lookup.values():
        family_labels[row["group_id"]].add(row["gold"])
    paired = sorted(group for group, labels in family_labels.items() if labels == {"ready", "repair"})
    pair_metrics = {}
    for method, decisions in by_method.items():
        pair_metrics[method] = {"families": len(paired), "both_correct": sum(
            all(decisions.get(cid) == _LABEL_TO_VERDICT[row["gold"]] for cid, row in lookup.items()
                if row["group_id"] == group) for group in paired)}
    opt = metrics["optimized"]
    broad = metrics["broad"]
    new_catches = {cid for cid, p in by_method["optimized"].items()
                   if lookup[cid]["gold"] == "repair" and p == "fail" and by_method["broad"][cid] != "fail"}
    lost_catches = {cid for cid, p in by_method["optimized"].items()
                    if lookup[cid]["gold"] == "repair" and p != "fail" and by_method["broad"][cid] == "fail"}
    new_families = {lookup[cid]["group_id"] for cid in new_catches}
    net_catches = opt["repair_catches"] - broad["repair_catches"]
    screen = {"new_repair_catches": len(new_catches), "lost_repair_catches": len(lost_catches),
              "net_repair_catches": net_catches, "new_repair_families": len(new_families),
              "ready_passes": opt["ready_passes"], "ready_rejections": opt["ready_rejections"],
              "decided_coverage": opt["decided_coverage"],
              "met": len(by_method["optimized"]) == 94 and net_catches >= 3 and len(new_families) >= 2
                     and opt["ready_passes"] >= 67 and opt["ready_rejections"] <= 10
                     and opt["decided_coverage"] >= .9}
    return {"eligible": 94, "gold": {"ready": 77, "repair": 17}, "metrics": metrics,
            "paired_families": pair_metrics, "development_screen": screen,
            "changed_decisions": [{"case_id": cid, "gold": lookup[cid]["gold"],
                                   "group_id": lookup[cid]["group_id"],
                                   "broad": by_method["broad"][cid],
                                   "combined": by_method["combined"][cid],
                                   "calibrated": by_method["calibrated"][cid],
                                   "seed": by_method["seed"].get(cid),
                                   "optimized": by_method["optimized"].get(cid)}
                                  for cid in sorted(lookup) if cid in by_method["optimized"] and
                                  by_method["optimized"][cid] != by_method["broad"][cid]]}
