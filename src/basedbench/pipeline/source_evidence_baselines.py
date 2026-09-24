"""Replay exact-input findings from immutable historical evaluator runs."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any


EXPERIMENTS = (
    "calibrated-luna-dev-v1",
    "focused-connection-v1",
    "capacity-comparison-v1",
    "materiality-comparison-v1",
    "claim-eval-v1",
    "connection-eval-v1",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_experiment(path: Path) -> list[str]:
    """Check all frozen inputs, requests, and completed-call artifacts."""
    errors: list[str] = []
    try:
        plan = _read_json(path / "plan.json")
        manifest = _read_json(path / "results-manifest.json")
    except (OSError, ValueError) as exc:
        return [f"missing_or_invalid_plan_or_results_manifest: {exc}"]
    plan_files = plan.get("files")
    if not isinstance(plan_files, dict) or not isinstance(manifest, dict):
        return ["invalid_plan_or_results_manifest_shape"]
    experiment_id = plan.get("experiment_id")
    if experiment_id and _digest({key: value for key, value in plan.items() if key != "experiment_id"}) != experiment_id:
        errors.append("plan_identity_mismatch")
    for rel, expected in {**plan_files, **manifest}.items():
        file_path = path / rel
        if not file_path.is_file():
            errors.append(f"missing_source_file:{rel}")
        elif _file_hash(file_path) != expected:
            errors.append(f"source_hash_mismatch:{rel}")
    jobs = _planned_jobs(path, plan)
    if not isinstance(jobs, list):
        errors.append("invalid_plan_jobs")
        return errors
    for job in jobs:
        key = job.get("key")
        if not isinstance(key, str):
            errors.append("invalid_job_key")
            continue
        request_path = path / "requests" / f"{key}.json"
        try:
            request = _read_json(request_path)
        except (OSError, ValueError) as exc:
            errors.append(f"missing_or_invalid_request:{key}:{exc}")
            continue
        if _digest(request) != job.get("request_sha256"):
            errors.append(f"request_hash_mismatch:{key}")
    return errors


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _request_content(request: dict[str, Any]) -> tuple[list[str], list[bytes]]:
    texts: list[str] = []
    images: list[bytes] = []
    for item in _walk(request.get("input", [])):
        if item.get("type") == "input_text" and isinstance(item.get("text"), str):
            texts.append(item["text"])
        if item.get("type") == "input_image":
            image_url = item.get("image_url")
            if isinstance(image_url, str) and image_url.startswith("data:") and ";base64," in image_url:
                try:
                    images.append(base64.b64decode(image_url.split(",", 1)[1], validate=True))
                except (ValueError, TypeError):
                    continue
    return texts, images


def _text_objects(texts: list[str]) -> list[Any]:
    objects = []
    for text in texts:
        try:
            objects.append(json.loads(text))
        except (ValueError, TypeError):
            continue
    return objects


def _candidate_and_comments(texts: list[str]) -> tuple[str | None, str | None]:
    for obj in _text_objects(texts):
        for value in _walk(obj):
            if not isinstance(value, dict):
                continue
            answer = value.get("candidate_answer", value.get("explanation"))
            comments = value.get("comment_evidence")
            if isinstance(answer, str) and isinstance(comments, str):
                return answer, comments
    return None, None


def _input_sha(case: dict[str, Any]) -> str:
    existing = case.get("input_sha256")
    return existing if isinstance(existing, str) else _digest(case["input"])


def _match_request(case: dict[str, Any], request: dict[str, Any]) -> tuple[bool, str]:
    data = case.get("input") or {}
    image_hash = data.get("image_sha256")
    if not isinstance(image_hash, str):
        return False, "dataset_image_sha256_missing"
    texts, images = _request_content(request)
    if not images:
        return False, "cached_request_has_no_verifiable_image_bytes"
    if not any(hashlib.sha256(image).hexdigest() == image_hash for image in images):
        return False, "image_bytes_differ"
    answer, comments = _candidate_and_comments(texts)
    if answer is None or comments is None:
        return False, "cached_request_candidate_or_comment_packet_unparseable"
    if answer != data.get("explanation"):
        return False, "explanation_differs"
    if comments != data.get("comment_evidence"):
        return False, "comment_packet_differs"
    image_path = case.get("image_path")
    if image_path:
        local = Path(image_path)
        if not local.is_file() or _file_hash(local) != image_hash:
            return False, "dataset_image_path_missing_or_hash_mismatch"
    return True, "exact_input_match"


def _prompt_hash(request: dict[str, Any]) -> str:
    return _digest(request.get("instructions"))


def _schema_hash(request: dict[str, Any]) -> str | None:
    schema = ((request.get("text") or {}).get("format") or {}).get("schema")
    return _digest(schema) if schema is not None else None


def _parse_result(experiment: str, case: dict[str, Any], legacy_case: dict[str, Any],
                  arm: str, call: dict[str, Any], mapping: dict[str, Any] | None = None) -> dict[str, Any]:
    """Use the original parser for a matching model/prompt family only."""
    from basedbench.pipeline import calibrated_eval, capacity_eval, claim_eval, connection_eval, focused_connection_eval

    if experiment == "calibrated-luna-dev-v1":
        parsed = calibrated_eval.parse(legacy_case, arm, call)
    elif experiment == "focused-connection-v1":
        parsed = focused_connection_eval.parse(legacy_case, arm, call)
    elif experiment == "capacity-comparison-v1":
        parsed = capacity_eval.parse(legacy_case, arm, call)
    elif experiment == "materiality-comparison-v1":
        parsed = capacity_eval.parse(legacy_case, "luna", call)
    elif experiment == "claim-eval-v1":
        parsed = claim_eval.parse(legacy_case, arm, call, case["input"]["explanation"])
    elif experiment == "connection-eval-v1":
        parsed = connection_eval.parse(legacy_case, arm, call, mapping=mapping)
    else:
        parsed = {"error": "no_version_matched_parser"}
    if parsed.get("error"):
        return {"parsed": parsed, "answer_quality": None, "evidence_status": None,
                "joint_verdict": None, "verdict_kind": "unavailable"}
    answer_quality = parsed.get("answer_quality")
    evidence_status = parsed.get("evidence_status")
    verdict = parsed.get("verdict")
    if answer_quality is not None and evidence_status is not None:
        kind = "joint_answer_and_evidence_gate"
    else:
        kind = "joint_or_unseparated_historical_verdict" if verdict else "findings_without_verdict"
    return {"parsed": parsed, "answer_quality": answer_quality,
            "evidence_status": evidence_status, "joint_verdict": verdict,
            "verdict_kind": kind}


def _planned_jobs(path: Path, plan: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = plan.get("jobs")
    if jobs:
        return jobs
    if path.name not in {"claim-eval-v1", "connection-eval-v1"}:
        return []
    allowed_stages = {"baseline", "check"}
    inferred = []
    for request_path in sorted((path / "requests").glob("*.json")):
        case_id, sep, stage = request_path.stem.rpartition(".")
        if not sep or stage not in allowed_stages:
            continue
        key = request_path.stem
        try:
            request = _read_json(request_path)
        except (OSError, ValueError):
            continue
        inferred.append({"key": key, "case_id": case_id, "arm": stage, "repeat": 0,
                         "model": request.get("model") or plan.get("model"),
                         "request_sha256": _digest(request)})
    return inferred


def _experiment_rows(cache_root: Path, experiment: str, cases: dict[str, dict[str, Any]],
                     unmatched: dict[str, list[str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = cache_root / experiment
    if not path.is_dir():
        return [], {"verified": False, "errors": ["experiment_directory_missing"]}
    errors = _verify_experiment(path)
    status: dict[str, Any] = {"verified": not errors, "errors": errors,
                              "plan_sha256": _file_hash(path / "plan.json") if (path / "plan.json").is_file() else None,
                              "results_manifest_sha256": _file_hash(path / "results-manifest.json") if (path / "results-manifest.json").is_file() else None,
                              "matched_trials": 0}
    if errors:
        for case_id in cases:
            unmatched.setdefault(case_id, []).append(f"{experiment}:source_integrity_failed")
        return [], status
    plan = _read_json(path / "plan.json")
    cache_cases = _read_json(path / "cases.json")
    legacy_by_id = {item.get("case_id"): item for item in cache_cases if isinstance(item, dict)}
    results: list[dict[str, Any]] = []
    for job in _planned_jobs(path, plan):
        key, source_case_id, arm = job["key"], job["case_id"], job["arm"]
        legacy_case = legacy_by_id.get(source_case_id)
        if not legacy_case:
            continue
        request_path = path / "requests" / f"{key}.json"
        call_path = path / "calls" / f"{key}.json"
        request, call = _read_json(request_path), _read_json(call_path)
        for case_id, case in cases.items():
            if str(case.get("post_id")) != str(legacy_case.get("post_id", source_case_id)):
                continue
            exact, why = _match_request(case, request)
            if not exact:
                reason = f"{experiment}:{why}"
                if reason not in unmatched.setdefault(case_id, []):
                    unmatched[case_id].append(reason)
                continue
            expected_model = job.get("model")
            actual_model = (call.get("response") or {}).get("model")
            if actual_model != expected_model:
                unmatched.setdefault(case_id, []).append(f"{experiment}:{key}:actual_model_mismatch")
                continue
            mapping = None
            if experiment == "connection-eval-v1":
                map_call_path = path / "calls" / f"{source_case_id}.map.json"
                if not map_call_path.is_file():
                    unmatched.setdefault(case_id, []).append(f"{experiment}:{key}:matching_map_missing")
                    continue
                map_call = _read_json(map_call_path)
                mapping = connection_map = _parse_result(
                    experiment, case, legacy_case, "map", map_call)["parsed"]
                if connection_map.get("error"):
                    unmatched.setdefault(case_id, []).append(f"{experiment}:{key}:matching_map_invalid")
                    continue
            parsed = _parse_result(experiment, case, legacy_case, arm, call, mapping=mapping)
            record = {
                "case_id": case_id,
                "post_id": case.get("post_id"),
                "source_case_id": source_case_id,
                "experiment": experiment,
                "source": {
                    "request_path": str(request_path),
                    "request_sha256": _file_hash(request_path),
                    "call_path": str(call_path),
                    "call_sha256": _file_hash(call_path),
                    "plan_sha256": status["plan_sha256"],
                    "results_manifest_sha256": status["results_manifest_sha256"],
                    "legacy_input_sha256": call.get("input_sha256"),
                    "output_sha256": hashlib.sha256((call.get("output_text") or "").encode()).hexdigest(),
                },
                "stage": "answer_check",
                "condition": arm,
                "repeat": job.get("repeat"),
                "model": {"planned": expected_model, "actual_returned": actual_model},
                "prompt_hash": _prompt_hash(request),
                "schema_hash": _schema_hash(request),
                "input_identity": {"dataset_input_sha256": _input_sha(case),
                                   "image_sha256": case["input"]["image_sha256"],
                                   "match": why},
                "call": {"status": call.get("status"), "response_id": (call.get("response") or {}).get("id"),
                         "usage": call.get("usage"), "error": call.get("error")},
                **parsed,
            }
            results.append(record)
    status["matched_trials"] = len(results)
    return results, status


def prepare(data_root: str | Path, dataset: str | Path, output: str | Path) -> dict[str, Any]:
    """Write exact-input cached baselines, preserving each condition and repeat."""
    data_root, dataset, output = Path(data_root), Path(dataset), Path(output)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite baseline replay: {output}")
    if (data_root / "backfill").is_dir():
        cache_root = data_root / "backfill"
    elif (data_root / "data" / "backfill").is_dir():
        cache_root = data_root / "data" / "backfill"
    else:
        cache_root = data_root
    cases_path = dataset / "cases.json" if dataset.is_dir() else dataset
    cases_value = _read_json(cases_path)
    case_rows = cases_value.get("cases", cases_value) if isinstance(cases_value, dict) else cases_value
    cases = {str(case["case_id"]): case for case in case_rows}
    unmatched = {case_id: [] for case_id in cases}
    matches: list[dict[str, Any]] = []
    experiments: dict[str, Any] = {}
    for experiment in EXPERIMENTS:
        rows, status = _experiment_rows(cache_root, experiment, cases, unmatched)
        matches.extend(rows)
        experiments[experiment] = status
    matched_ids = {row["case_id"] for row in matches}
    for case_id in cases:
        if case_id not in matched_ids and not unmatched[case_id]:
            unmatched[case_id].append("no_exact_verified_cached_request")
    report = {
        "version": "source-evidence-baselines-v1",
        "case_count": len(cases),
        "matched_case_count": len(matched_ids),
        "matched_trial_count": len(matches),
        "unmatched_case_count": sum(case_id not in matched_ids for case_id in cases),
        "experiments": experiments,
        "unmatched": [{"case_id": case_id, "reasons": reasons} for case_id, reasons in unmatched.items()
                      if case_id not in matched_ids],
        "limits": ["Only exact explanation, comment-packet, and image-byte matches are reused.",
                   "Answer quality and evidence status stay separate; a joint gate is explicitly labeled.",
                   "Historical models and repeated calls remain separate observations."],
    }
    output.mkdir(parents=True)
    (output / "matches.json").write_text(json.dumps(matches, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {name: _file_hash(output / name) for name in ("matches.json", "report.json")}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return report
