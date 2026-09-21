"""Frozen JEV value-prompt comparison, with a paired literal-evidence ablation."""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import math
from collections import Counter
from pathlib import Path

from basedbench.pipeline import curation_checks as checks
from basedbench.pipeline import curation_enriched as enriched
from basedbench.pipeline import curation_llm as replay
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json, write_jsonl


def prepare(source: Path, prompts_path: Path, observations_path: Path, output: Path, *, budget_usd: float) -> dict:
    if output.exists():
        raise FileExistsError("Use a new output directory")
    if not math.isfinite(budget_usd) or budget_usd <= 0:
        raise ValueError("A finite positive spending cap is required")
    original = enriched.load_plan(source)
    targets = json.loads((source / "targets.json").read_text())
    ids = [r["post_id"] for r in targets]
    if len(ids) != len(set(ids)) or ids != original["evaluation_ids"] or any(r["split"] == "test" for r in targets):
        raise ValueError("Expected unique original development targets in frozen order")
    prompts = json.loads(prompts_path.read_text())
    observations = json.loads(observations_path.read_text())
    if set(observations["items"]) != set(ids):
        raise ValueError("Every target needs exactly one observation")
    for row in targets:
        observation = observations["items"][row["post_id"]]
        if set(observation) != {"image_sha256", "visible_text", "visible_scene"}:
            raise ValueError("Observations may contain only image identity and literal evidence")
        if observation["image_sha256"] != row["input"]["image_sha256"]:
            raise ValueError("Observation image mismatch")
        if not all(isinstance(observation[k], str) for k in ("visible_text", "visible_scene")) or not observation["visible_scene"].strip():
            raise ValueError("An observation must describe the visible scene")
    specs = {}
    for name, spec in prompts["variants"].items():
        if name not in {"interpretation_gap", "anchored_payoff", "combined"} or spec["type"] != "choice" or set(spec["criteria"]) != {"pass", "fail", "uncertain"}:
            raise ValueError("Unexpected prompt specification")
        specs[name] = {**spec, "instructions": prompts["common_instructions"] + "\n" + spec["instructions"]}
    if len(specs) != 3:
        raise ValueError("Expected three draft hypotheses")
    bodies, variants, bounds = {}, {}, {}
    for evidence in ("text", "literal"):
        for prompt in ("control", *specs):
            variant = f"{prompt}_{evidence}"
            for row in targets:
                pid = row["post_id"]
                old = json.loads((source / "jev_clear_rules" / "requests" / f"{pid}.json").read_text())
                if old["model"] != replay.JEV_MODEL:
                    raise ValueError("Source model mismatch")
                # Keep the exact previous candidate text; remove the other checks.
                candidate = {k: row["input"][k] for k in ("explanation", "comment_evidence")}
                if old["state"] != {"candidate": candidate}:
                    raise ValueError("Expected source text without reference examples")
                body = {"model": replay.JEV_MODEL, "state": copy.deepcopy(old["state"]),
                        "questions": {"benchmark_value": copy.deepcopy(old["questions"]["benchmark_value"] if prompt == "control" else specs[prompt])}}
                if evidence == "literal":
                    body["state"]["candidate"]["literal_observation"] = {
                        k: observations["items"][pid][k] for k in ("visible_text", "visible_scene")}
                bodies[variant, pid] = body
                bounds[f"{variant}:{pid}.jev"] = checks.request_bound(body, "jev")
            child = {"variant": variant, "arms": ["jev"], "evaluation_ids": ids,
                     "input_hashes": {r["post_id"]: r["input_sha256"] for r in targets},
                     "request_content_hashes": {p: digest(bodies[variant, p]) for p in ids}}
            child["experiment_id"] = digest(child)
            variants[variant] = child
    if sum(bounds.values()) > budget_usd:
        raise ValueError(f"All maximum allowances (${sum(bounds.values()):.6f}) must fit the cap before preparation")
    output.mkdir(parents=True)
    write_json(output / "targets.json", targets)
    write_json(output / "prompts.json", prompts)
    write_json(output / "observations.json", observations)
    for variant, child in variants.items():
        (output / variant / "requests").mkdir(parents=True)
        (output / variant / "calls").mkdir()
        for pid in ids:
            write_json(output / variant / "requests" / f"{pid}.json", bodies[variant, pid])
        write_json(output / variant / "plan.json", child)
    code_files = [Path(__file__), Path(enriched.__file__), Path(checks.__file__), Path(replay.__file__)]
    plan = {"schema_version": "curation-value-v1", "source_experiment_id": original["experiment_id"],
            "corpus_id": original["corpus_id"], "evaluation_ids": ids,
            "gold": {p: original["gold"][p] for p in ids}, "variants": variants,
            "budget_usd": budget_usd, "request_bounds_usd": bounds, "all_request_bounds_usd": sum(bounds.values()),
            "prices": replay.JEV_PRICES,
            "code_hashes": {p.name: file_hash(p) for p in code_files},
            "limitations": [
                "Development diagnostic: all cases informed the hypotheses; this is not independent validation.",
                "Assistant-authored observations were made with knowledge of earlier feedback and may be biased.",
                "Literal-evidence variants receive descriptions, not pixels; descriptions are not guaranteed complete or correct.",
                "Observation preparation cost is not included in provider cost; this is not an automated captioning pipeline.",
                "No examples or reference labels are supplied. Content and ground truth are not evaluated or changed.",
                "The control uses the previous clear-rules value question alone; one versus three questions may affect behavior.",
                "Only five settled value failures and seventeen passes; six unresolved value labels remain separate.",
                "Hypotheses differ as whole prompts, including shared instructions and answer descriptions.",
                "A single response per condition does not establish repeatability; scores are not calibrated probabilities.",
            ]}
    plan["files"] = {p.relative_to(output).as_posix(): file_hash(p) for p in sorted(output.rglob("*.json"))}
    plan["experiment_id"] = digest(plan)
    write_json(output / "plan.json", plan)
    return plan


def parse(call: dict) -> dict:
    """Validate one native Choice, preserving rounded scores and explicit errors."""
    try:
        if call.get("error") or call["status"] != "completed":
            raise ValueError(call.get("error") or "Incomplete provider call")
        response = call["response"]
        if response["model"] != replay.JEV_MODEL or set(response["answers"]) != {"benchmark_value"}:
            raise ValueError("Unexpected model or answer keys")
        answer = response["answers"]["benchmark_value"]
        probs = answer["probabilities"]
        if answer["type"] != "choice" or set(probs) != {"pass", "fail", "uncertain"}:
            raise ValueError("Invalid choices")
        if not all(type(v) in {int, float} and math.isfinite(v) and 0 <= v <= 1 for v in probs.values()):
            raise ValueError("Invalid probabilities")
        rounded = all(math.isclose(v * 100, round(v * 100), abs_tol=1e-8) for v in probs.values())
        if not math.isclose(sum(probs.values()), 1, abs_tol=.015000001 if rounded else 1e-4):
            raise ValueError("Invalid probability sum")
        if probs[answer["choice"]] < max(probs.values()):
            raise ValueError("Choice is inconsistent with scores")
        return {"verdict": answer["choice"], "pass_score": probs["pass"], "probabilities": probs, "error": None}
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        return {"verdict": "error", "pass_score": None, "error": str(exc)}


def summarize(output: Path) -> dict:
    plan = enriched.load_plan(output)
    gold = {p: g["components"]["benchmark_value"] for p, g in plan["gold"].items() if "benchmark_value" in g["components"]}
    predictions, report = [], {"experiment_id": plan["experiment_id"], "variants": {}, "limitations": plan["limitations"]}
    for variant, child in plan["variants"].items():
        results, spent, unknown = {}, 0.0, 0
        for pid in child["evaluation_ids"]:
            path = output / variant / "calls" / f"{pid}.jev.json"
            call = json.loads(path.read_text())
            if (call["experiment_id"] != child["experiment_id"] or call["input_sha256"] != child["input_hashes"][pid]
                    or call["post_id"] != pid or call["arm"] != "jev"):
                raise ValueError("Call identity mismatch")
            if call.get("request_content_sha256") is not None and call["request_content_sha256"] != child["request_content_hashes"][pid]:
                raise ValueError("Call request mismatch")
            result = parse(call)
            results[pid] = result["verdict"]
            price = checks.cost(call.get("usage"), "jev")
            unknown += price is None
            spent += price or 0
            predictions.append({"variant": variant, "post_id": pid, **result,
                                "latency_ms": call.get("latency_ms"), "cost_usd": price})
        report["variants"][variant] = {"metrics": enriched.component_metrics(gold, results),
            "all_outcomes": dict(Counter(results.values())),
            "unresolved": {p: results[p] for p in results if p not in gold},
            "positive_misses": {p: results[p] for p in gold if gold[p] == "pass" and results[p] != "pass"},
            "negative_outcomes": {p: results[p] for p in gold if gold[p] == "fail"},
            "cost_usd": spent, "calls_without_usage": unknown, "errors": sum(v == "error" for v in results.values())}
    budget = enriched.restore_budget(plan, output)
    report.update(cost_usd=sum(v["cost_usd"] for v in report["variants"].values()),
                  accounted_usd=sum(budget.charges.values()), budget_usd=plan["budget_usd"], allowance_violation=budget.violated)
    write_jsonl(output / "predictions.jsonl", predictions)
    write_json(output / "report.json", report)
    return report


async def run(output: Path, *, budget_usd: float, api_key: str) -> dict:
    import fcntl
    import httpx

    plan = enriched.load_plan(output)
    if budget_usd != plan["budget_usd"]:
        raise ValueError("Execution cap must equal prepared cap")
    for module in (__file__, enriched.__file__, checks.__file__, replay.__file__):
        path = Path(module)
        if file_hash(path) != plan["code_hashes"][path.name]:
            raise ValueError("Implementation changed since preparation")
    rows = json.loads((output / "targets.json").read_text())
    with (output / "run.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        budget = enriched.restore_budget(plan, output)
        async with httpx.AsyncClient(base_url="https://api.typesafe.ai", timeout=60, follow_redirects=False,
                                    headers={"Authorization": f"Bearer {api_key}"}) as client:
            # Explicit order: complete the text-only comparison before adding descriptions.
            for evidence in ("text", "literal"):
                for prompt in ("control", "interpretation_gap", "anchored_payoff", "combined"):
                    variant = f"{prompt}_{evidence}"
                    child = plan["variants"][variant]
                    def request_factory(row, arm, corpus, settings):
                        return json.loads((output / variant / "requests" / f"{row['post_id']}.json").read_text())
                    print(f"Running {variant}; accounted ${sum(budget.charges.values()):.5f}/${budget.limit:.2f}", flush=True)
                    await replay.collect_calls(None, rows, output, output / variant, child, concurrency=4,
                        jev_client=client, request_factory=request_factory, budget=enriched.ScopedBudget(budget, variant))
        return summarize(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    for name in ("source", "prompts", "observations", "output"):
        prep.add_argument(name, type=Path)
    prep.add_argument("--budget-usd", required=True, type=float)
    paid = sub.add_parser("run")
    paid.add_argument("output", type=Path)
    paid.add_argument("--budget-usd", required=True, type=float)
    args = parser.parse_args()
    if args.command == "prepare":
        plan = prepare(args.source, args.prompts, args.observations, args.output, budget_usd=args.budget_usd)
        print(json.dumps({"experiment_id": plan["experiment_id"], "calls": len(plan["request_bounds_usd"]),
                          "all_request_bounds_usd": plan["all_request_bounds_usd"], "budget_usd": plan["budget_usd"]}))
    else:
        import os
        from dotenv import dotenv_values
        env = dotenv_values(".env")
        key = os.getenv("JEV_API_KEY") or os.getenv("TYPESAFE_API_KEY") or env.get("JEV_API_KEY") or env.get("TYPESAFE_API_KEY")
        if not key:
            raise ValueError("JEV_API_KEY is required")
        report = asyncio.run(run(args.output, budget_usd=args.budget_usd, api_key=key))
        print(json.dumps({"cost_usd": report["cost_usd"], "accounted_usd": report["accounted_usd"],
                          "errors": {v: r["errors"] for v, r in report["variants"].items()}}))


if __name__ == "__main__":
    main()
