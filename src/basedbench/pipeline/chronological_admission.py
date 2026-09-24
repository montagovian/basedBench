"""Frozen chronological admission, with one persistent GPT-6 Luna allowance."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import copy
import fcntl
import json
import math
from pathlib import Path
import re
import shutil

from PIL import Image

from basedbench.errors import FATAL_LLM_ERROR_CODES, FATAL_LLM_STATUS_CODES
from basedbench.pipeline import admission_pilot as pilot
from basedbench.pipeline import answer_eval as answers, content_policy as content
from basedbench.pipeline import calibrated_eval, curation_llm as transport
from basedbench.pipeline import chronological_duplicates, chronological_inventory
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json

VERSION = 'chronological-admission-v1'
MODEL = 'gpt-6-luna'
MAX_BUDGET = 10.0
PRICES = {**calibrated_eval.PRICES[MODEL], 'source': 'https://developers.openai.com/api/docs/models/gpt-6-luna',
          'checked_on': '2026-09-23', 'long_context_threshold': 272000, 'context_tokens': 1050000}


def code_hashes() -> dict:
    return {**pilot.code_hashes(), 'chronological_admission': file_hash(Path(__file__)),
            'calibrated_eval': file_hash(Path(calibrated_eval.__file__)),
            'chronological_duplicates': file_hash(Path(chronological_duplicates.__file__)),
            'chronological_inventory': file_hash(Path(chronological_inventory.__file__))}


def request(case: dict, stage: str, output: Path, **kwargs) -> dict:
    body = pilot.make_request(case, stage, output, **kwargs)
    body['model'] = MODEL
    return body


def price(usage: dict | None, *, conservative: bool = False) -> float | None:
    """Reject malformed counters before allowing an unknown call to release spend."""
    if not isinstance(usage, dict):
        return None
    details = usage.get('input_tokens_details') or {}
    if not isinstance(details, dict):
        return None
    fields = [usage.get('input_tokens'), usage.get('output_tokens'),
              details.get('cached_tokens', 0), details.get('cache_write_tokens', 0)]
    if any(type(value) is not int or value < 0 for value in fields):
        return None
    if fields[2] + fields[3] > fields[0]:
        return None
    return calibrated_eval.price(usage, MODEL, conservative=conservative)


def fatal_response(call: dict) -> bool:
    response = call.get('response') or {}
    failure = response.get('error') or {}
    if not isinstance(failure, dict):
        return False
    inner = failure.get('error') if isinstance(failure.get('error'), dict) else failure
    return inner.get('code') in FATAL_LLM_ERROR_CODES or inner.get('status') in FATAL_LLM_STATUS_CODES


def parse(case: dict, stage: str, call: dict) -> dict:
    """Validate Luna 6 explicitly; reuse schemas and citation rules, not old model checks."""
    if call.get('error') or call.get('status') != 'completed':
        detail = call.get('error') or 'Incomplete provider response'
        return pilot.error('invalid_response', detail) if stage in {'content', 'suitability'} else {'error': detail}
    if call.get('response', {}).get('model') != MODEL:
        detail = 'Unexpected returned model identity'
        return pilot.error('invalid_response', detail) if stage in {'content', 'suitability'} else {'error': detail}
    try:
        if stage == 'content':
            value = content.ContentAssessment.model_validate_json(call['output_text'])
            if not {cid for finding in value.findings for cid in finding.evidence_comment_ids} <= content.citation_ids(case):
                raise ValueError('Citation outside supplied comments')
            return {**content.decision(value), 'assessment': value.model_dump()}
        if stage == 'suitability':
            value = pilot.Suitability.model_validate_json(call['output_text']).model_dump()
            return pilot.result({'pass': 'pass', 'fail': 'fail', 'uncertain': 'defer'}[value['verdict']],
                                value['failure_code'] or ('recoverable_task' if value['verdict'] == 'pass' else 'unclear_task'),
                                assessment=value)
        schema = answers.Draft if stage == 'generate' or stage.endswith('repair') else answers.AnswerCheck
        value = schema.model_validate_json(call['output_text'])
        cited = set(value.evidence_comment_ids)
        if isinstance(value, answers.AnswerCheck):
            cited.update(cid for claim in value.claim_support for cid in claim.evidence_comment_ids)
        if not cited <= set(answers.citation_ids(case)):
            raise ValueError('Citation outside supplied evidence')
        return value.model_dump()
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        return pilot.error('invalid_response', str(exc)) if stage in {'content', 'suitability'} else {'error': str(exc)}


def verify_files(directory: Path, files: dict) -> None:
    if not isinstance(files, dict):
        raise ValueError('Invalid frozen file manifest')
    root = directory.resolve()
    for relative, expected in files.items():
        if not isinstance(relative, str) or not isinstance(expected, str) or not re.fullmatch('[a-f0-9]{64}', expected):
            raise ValueError('Invalid frozen file entry')
        name = Path(relative)
        if name.is_absolute() or '..' in name.parts or not name.parts:
            raise ValueError(f'Unsafe frozen path: {relative}')
        path = root / name
        if (not path.resolve().is_relative_to(root) or
                any(part.is_symlink() for part in (path, *path.parents) if part != root) or
                not path.is_file() or file_hash(path) != expected):
            raise ValueError(f'Frozen input changed: {relative}')


def _source_plan(directory: Path, *, id_key: str, expected_inventory: str | None = None) -> dict:
    plan = json.loads((directory / 'plan.json').read_text())
    if expected_inventory is not None and plan['inventory_id'] != expected_inventory:
        raise ValueError('Duplicate audit belongs to a different inventory')
    if id_key not in plan or digest({k: v for k, v in plan.items() if k != id_key}) != plan[id_key]:
        raise ValueError('Source plan identity changed')
    verify_files(directory, plan['files'])
    for path, expected in plan.get('source_files', {}).items():
        if file_hash(Path(path)) != expected:
            raise ValueError('Source input changed')
    if plan.get('code') != chronological_duplicates._code_hashes():
        raise ValueError('Source code changed')
    return plan


def _preflight(case: dict, output: Path) -> None:
    case['input_sha256'] = digest(case['input'])
    case['preflight'] = pilot.result('pass', 'available_evidence')
    source = Path(case.pop('image_path')) if case.get('image_path') else None
    sha = case['input']['image_sha256']
    if source is None or not source.is_file():
        case['preflight'] = pilot.error('missing_image')
    elif not re.fullmatch('[a-f0-9]{64}', sha or '') or file_hash(source) != sha:
        raise ValueError('Image identity changed')
    else:
        shutil.copyfile(source, output / 'assets' / sha)
        try:
            with Image.open(source) as image:
                if getattr(image, 'n_frames', 1) != 1:
                    raise ValueError('Animated image is unsupported')
                image.verify()
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            case['preflight'] = pilot.error('unsupported_image', str(exc))
    if len(answers.citation_ids(case)) < 3:
        if case['preflight']['decision'] == 'pass':
            case['preflight'] = pilot.result('defer', 'fewer_than_three_comments')
        else:
            case['preflight']['reason_codes'].append('fewer_than_three_comments')
    if case.get('source_mismatches'):
        earlier = [] if case['preflight']['decision'] == 'pass' else case['preflight']['reason_codes']
        case['preflight'] = pilot.error('source_mismatch', json.dumps(case['source_mismatches']))
        case['preflight']['reason_codes'] = [*earlier, 'source_mismatch']


def prepare_inventory(inventory: Path, duplicates: Path, output: Path, *, budget_usd: float = 10) -> dict:
    inventory, duplicates, output = Path(inventory).resolve(), Path(duplicates).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError('Prepare a new frozen directory')
    if not math.isfinite(budget_usd) or not 0 < budget_usd <= MAX_BUDGET:
        raise ValueError('Budget must be positive and at most $10')
    manifest = json.loads((inventory / 'manifest.json').read_text())
    verify_files(inventory, manifest['files'])
    iplan = json.loads((inventory / 'plan.json').read_text())
    if iplan['inventory_id'] != manifest['inventory_id']:
        raise ValueError('Inventory identity changed')
    if digest({k: v for k, v in iplan.items() if k != 'inventory_id'}) != iplan['inventory_id']:
        raise ValueError('Inventory plan identity changed')
    if iplan.get('code_sha256') is not None and iplan['code_sha256'] != chronological_inventory.code_hashes():
        raise ValueError('Inventory code changed')
    if iplan.get('baseline_sha256') is not None and iplan['baseline_sha256'] != digest(
            json.loads((inventory / 'baseline.json').read_text())):
        raise ValueError('Inventory baseline changed')
    dplan = _source_plan(duplicates, id_key='audit_id', expected_inventory=manifest['inventory_id'])
    results_manifest = duplicates / 'results-manifest.json'
    verify_files(duplicates, json.loads(results_manifest.read_text()))
    report = json.loads((duplicates / 'report.json').read_text())
    if report['audit_id'] != dplan['audit_id']:
        raise ValueError('Duplicate report identity changed')
    input_rows = json.loads((duplicates / 'inputs.json').read_text())
    inputs = {row['post_id']: row for row in input_rows}
    if len(inputs) != len(input_rows):
        raise ValueError('Duplicate audit input IDs are not unique')
    candidates = json.loads((inventory / 'candidates.json').read_text())
    if len(candidates) > 1000:
        raise ValueError('More than 1,000 selected candidates')
    ids = [item['post_id'] for item in candidates]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r'[A-Za-z0-9_-]+', pid) for pid in ids):
        raise ValueError('Invalid or duplicate post IDs')
    disposition_ids = [row['post_id'] for row in report['dispositions']]
    if len(disposition_ids) != len(ids) or set(ids) != set(disposition_ids):
        raise ValueError('Duplicate report does not cover every candidate')
    cases = []
    for item in candidates:
        pid = item['post_id']
        if pid not in inputs or inputs[pid]['pool'] != 'fresh':
            raise ValueError('Missing duplicate input')
        image = item['image']
        if image.get('sha256') != inputs[pid]['image'].get('sha256'):
            raise ValueError('Duplicate audit used different image evidence')
        comment_text, selected = pilot.comment_evidence(item)
        edges = [{**edge, 'fresh_pair': edge['left'] in ids and edge['right'] in ids}
                 for edge in report['edges'] if pid in (edge['left'], edge['right'])]
        path = None
        if image['status'] == 'available':
            relative = Path(image['path'])
            path = inventory / relative
            if (relative.is_absolute() or '..' in relative.parts or not path.resolve().is_relative_to(inventory)
                    or path.is_symlink() or manifest['files'].get(str(relative)) != image.get('sha256')):
                raise ValueError('Candidate image path is not frozen inventory evidence')
        cases.append({'post_id': pid, 'image_path': str(path) if path else None,
                      'input': {'explanation': '', 'comment_evidence': comment_text, 'image_sha256': image.get('sha256')},
                      'source_mismatches': item.get('source_mismatches', []), 'duplicate': pilot.duplicate_route(edges),
                      'human': {}, 'provenance': {'inventory_id': manifest['inventory_id'],
                          'duplicate_audit_id': dplan['audit_id'], 'subreddit': item['subreddit'],
                          'source_date': item.get('source_date'), 'comment_selection': selected,
                          'image_retrieval': image}})
    for folder in ('assets', 'calls', 'requests'):
        (output / folder).mkdir(parents=True, exist_ok=True)
    bounds = {}
    worst = '\U00010000' * 2400
    critique = {'reason': '\U00010000' * 1200, 'missing_core_details': ['\U00010000' * 300] * 3,
                'defects': ['missing_core_connection', 'unsupported_addition', 'visual_contradiction',
                            'competing_readings', 'insufficient_evidence']}
    for case in cases:
        _preflight(case, output)
        if case['preflight']['decision'] != 'pass':
            continue
        try:
            for stage in pilot.STAGES:
                body = request(case, stage, output, explanation=worst, critique=critique)
                bounds[f"{case['post_id']}.{stage}"] = calibrated_eval.bound(body)
        except ValueError as exc:
            case['preflight'] = pilot.error('request_not_supported', str(exc))
            for stage in pilot.STAGES:
                bounds.pop(f"{case['post_id']}.{stage}", None)
    write_json(output / 'cases.json', cases)
    source_paths = [inventory / 'manifest.json', inventory / 'plan.json', inventory / 'candidates.json',
                    duplicates / 'plan.json', duplicates / 'inputs.json', duplicates / 'report.json']
    source_paths.append(results_manifest)
    plan = {'schema_version': VERSION, 'scope': {'kind': 'chronological_inventory',
             'inventory_id': manifest['inventory_id'], 'duplicate_audit_id': dplan['audit_id']},
            'source_directories': {'inventory': str(inventory), 'duplicates': str(duplicates)},
            'budget_usd': budget_usd, 'model': MODEL, 'prices': PRICES,
            'component_versions': {'answer': answers.VERSION, 'content': content.VERSION,
                'duplicates': dplan.get('version', 'chronological-duplicates'),
                'suitability': pilot.SUITABILITY_VERSION},
            'source_files': {str(path): file_hash(path) for path in source_paths},
            'code_hashes': code_hashes(), 'input_hashes': {c['post_id']: c['input_sha256'] for c in cases},
            'request_bounds_usd': bounds, 'all_stage_bounds_usd': sum(bounds.values()),
            'max_calls_per_candidate': 6, 'max_repairs_per_answer': 1, 'automatic_retries': 0,
            'concurrency': 1, 'human_validation': False, 'publication': False,
            'files': {str(p.relative_to(output)): file_hash(p) for p in sorted(output.rglob('*')) if p.is_file()},
            'limitations': ['Automatic accepts are development candidates, not human validation or publication.',
                            'Sampled comments and model checks do not establish independent human consensus.',
                            'Unresolved duplicate links defer; no match does not prove novelty.']}
    plan['experiment_id'] = digest(plan)
    write_json(output / 'plan.json', plan)
    return plan


def load_plan(output: Path) -> dict:
    plan = json.loads((output / 'plan.json').read_text())
    if (plan['schema_version'] != VERSION or plan['code_hashes'] != code_hashes()
            or plan['experiment_id'] != digest({k: v for k, v in plan.items() if k != 'experiment_id'})):
        raise ValueError('Frozen plan/code changed; use a new run')
    verify_files(output, plan['files'])
    for path, expected in plan['source_files'].items():
        if file_hash(Path(path)) != expected:
            raise ValueError('Frozen source input changed')
    sources = plan['source_directories']
    verify_files(Path(sources['inventory']), json.loads((Path(sources['inventory']) / 'manifest.json').read_text())['files'])
    verify_files(Path(sources['duplicates']), json.loads((Path(sources['duplicates']) / 'results-manifest.json').read_text()))
    for marker in (output / 'calls').glob('*.pending'):
        if marker.stem not in plan['request_bounds_usd'] or marker.read_text() != plan['experiment_id']:
            raise ValueError('Pending request belongs to a different run')
    return plan


class Budget:
    """One run-wide persistent ledger; malformed/unknown usage retains reservation."""
    def __init__(self, plan: dict, output: Path):
        self.limit = plan['budget_usd']
        self.bounds = plan['request_bounds_usd']
        self.charges: dict[str, float] = {}
        self.violated = False
        for path in (output / 'calls').glob('*.json'):
            call = json.loads(path.read_text())
            if call['experiment_id'] != plan['experiment_id']:
                raise ValueError('Budget history belongs to another run')
            self.settle(call['post_id'], call['arm'], call)
        for path in (output / 'calls').glob('*.pending'):
            if path.stem not in self.charges:
                self.charges[path.stem] = self.bounds[path.stem]

    def reserve(self, pid: str, stage: str) -> float | None:
        key = f'{pid}.{stage}'
        if key in self.charges:
            raise ValueError('Request already accounted')
        amount = self.bounds[key]
        if self.violated or sum(self.charges.values()) + amount > self.limit + 1e-12:
            return None
        self.charges[key] = amount
        return amount

    async def acquire(self, pid: str, stage: str) -> float | None:
        return self.reserve(pid, stage)

    def settle(self, pid: str, stage: str, call: dict) -> None:
        key = f'{pid}.{stage}'
        if key not in self.bounds:
            raise ValueError('Unplanned call')
        value = price(call.get('usage'), conservative=True)
        if (call.get('response') is not None and isinstance(call.get('usage'), dict) and
                call['usage'].get('input_tokens') == 0 and call['usage'].get('output_tokens') == 0):
            value = None
        self.charges[key] = self.bounds[key] if value is None else value
        self.violated |= self.charges[key] > self.bounds[key] + 1e-12
        response = call.get('response') or {}
        # A nonstandard service tier may carry a different price schedule.
        self.violated |= response.get('service_tier', 'default') not in {'default', None}


def _report(output: Path, plan: dict, cases: list[dict], results: list[dict], budget: Budget, *, complete: bool) -> dict:
    recorded = {row['post_id']: row for row in results}
    outcomes = [recorded.get(case['post_id'], {'post_id': case['post_id'], 'decision': 'defer',
        'reason_codes': ['checkpoint_not_completed'], 'technical_status': 'not_run',
        'components': {name: pilot.skipped('checkpoint_not_completed') for name in
                       ('preflight', 'duplicates', 'content', 'answer', 'suitability')},
        'human': {}, 'human_validated': False}) for case in cases]
    calls = [json.loads(path.read_text()) for path in sorted((output / 'calls').glob('*.json'))]
    prices = [price(call.get('usage')) for call in calls]
    report = {'experiment_id': plan['experiment_id'], 'version': VERSION, 'scope': plan['scope'],
        'component_versions': plan['component_versions'], 'complete': complete, 'outcomes': outcomes,
        'counts': dict(Counter(row['decision'] for row in outcomes)),
        'technical_errors': sum(row['technical_status'] == 'error' for row in outcomes),
        'reason_counts': dict(Counter(reason for row in outcomes for reason in row['reason_codes'])),
        'cost': {'budget_usd': budget.limit, 'accounted_usd': sum(budget.charges.values()),
                 'estimated_usd': sum(value for value in prices if value is not None),
                 'unknown_usage_calls': sum(value is None for value in prices),
                 'completed_provider_calls': sum(call.get('response') is not None for call in calls),
                 'call_records': len(calls), 'pending': len(list((output / 'calls').glob('*.pending'))),
                 'allowance_violation': budget.violated}, 'limitations': plan['limitations']}
    transport._atomic_json(output / 'report.json', report)
    transport._atomic_json(output / 'results-manifest.json', {'report.json': file_hash(output / 'report.json'),
        **{str(path.relative_to(output)): file_hash(path) for folder in ('calls', 'requests')
           for path in sorted((output / folder).glob('*.json'))}})
    return report


async def run(output: Path, *, budget_usd: float, api_key: str = '', client=None,
              stop_after_new_calls: int | None = None) -> dict:
    output = Path(output).resolve()
    plan = load_plan(output)
    if budget_usd != plan['budget_usd']:
        raise ValueError('Execution cap must equal the frozen cap')
    if stop_after_new_calls is not None and stop_after_new_calls < 0:
        raise ValueError('Checkpoint call count cannot be negative')
    cases = json.loads((output / 'cases.json').read_text())
    with (output / 'run.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (output / 'report.json').exists() and not (output / 'results-manifest.json').exists():
            raise ValueError('Saved report is missing its results manifest')
        if (output / 'results-manifest.json').exists():
            verify_files(output, json.loads((output / 'results-manifest.json').read_text()))
        budget = Budget(plan, output)
        # Fully completed replays must not construct credentials or clients.
        if (output / 'report.json').exists():
            report = json.loads((output / 'report.json').read_text())
            if report['complete'] and not list((output / 'calls').glob('*.pending')):
                return report
        halted = budget.violated or any(
            saved.get('fatal_provider_error') or fatal_response(saved) or
            (saved.get('response') and saved['response'].get('model') != MODEL)
            for saved in (json.loads(p.read_text()) for p in (output / 'calls').glob('*.json')))
        remaining = budget.limit - sum(budget.charges.values())
        reservable = any(amount <= remaining + 1e-12 and key not in budget.charges
                         for key, amount in plan['request_bounds_usd'].items())
        owned = client is None and not halted and stop_after_new_calls != 0 and any(
            c['preflight']['decision'] == 'pass' and c['duplicate']['decision'] == 'pass' for c in cases) and reservable
        if owned:
            if not api_key:
                raise ValueError('API key required for new model calls')
            import openai
            client = openai.AsyncOpenAI(api_key=api_key, max_retries=0, timeout=120)
        try:
            new_calls, results = 0, []
            for case in cases:
                async def invoke(stage, **kwargs):
                    nonlocal halted, new_calls
                    key = case['post_id'] + '.' + stage
                    body = request(case, stage, output, **kwargs)
                    if calibrated_eval.bound(body) > plan['request_bounds_usd'][key] + 1e-12:
                        raise ValueError('Adaptive request exceeds frozen reservation')
                    request_path = output / 'requests' / (key + '.json')
                    if request_path.exists() and json.loads(request_path.read_text()) != body:
                        raise ValueError('Adaptive request changed on replay')
                    if not request_path.exists():
                        transport._atomic_json(request_path, body)
                    path = output / 'calls' / (key + '.json')
                    pending = path.with_suffix('.pending').exists()
                    if not path.exists() and not pending:
                        if halted:
                            return pilot.error('fatal_provider_stop') if stage in {'content', 'suitability'} else {'error': 'fatal_provider_stop'}
                        if stop_after_new_calls is not None and new_calls >= stop_after_new_calls:
                            raise pilot.CheckpointStop()
                    was_saved = path.exists()
                    row = {'post_id': case['post_id'], 'input_sha256': case['input_sha256']}
                    await transport.collect_calls(client, [row], output, output, {**plan, 'arms': [stage]},
                                                  concurrency=1, request_factory=lambda *_: body, budget=budget)
                    call = json.loads(path.read_text())
                    if (call['post_id'] != case['post_id'] or call['arm'] != stage or
                            call.get('request_content_sha256') not in {digest(body), None}):
                        raise ValueError('Response identity/request mismatch')
                    if call.get('request_content_sha256') is None and call['status'] not in {'unknown', 'not_started'}:
                        raise ValueError('Completed response missing request provenance')
                    path.with_suffix('.pending').unlink(missing_ok=True)
                    halted |= bool(call.get('fatal_provider_error')) or fatal_response(call) or budget.violated
                    halted |= bool(call.get('response') and call['response'].get('model') != MODEL)
                    if not was_saved and not pending and call.get('cost_reservation_usd') is not None:
                        new_calls += 1
                    if budget.violated:
                        return pilot.error('budget_allowance_violation') if stage in {'content', 'suitability'} else {'error': 'budget_allowance_violation'}
                    if call.get('error') and 'experiment cost limit reached' in call['error']:
                        return pilot.error('budget_exhausted') if stage in {'content', 'suitability'} else {'error': 'budget_exhausted'}
                    return parse(case, stage, call)
                try:
                    results.append(await pilot.evaluate(case, invoke))
                except pilot.CheckpointStop:
                    return _report(output, plan, cases, results, budget, complete=False)
                _report(output, plan, cases, results, budget, complete=len(results) == len(cases))
                if len(results) % 10 == 0 or len(results) == len(cases):
                    print(f"Recorded {len(results)}/{len(cases)} candidates; "
                          f"accounted ${sum(budget.charges.values()):.4f}/${budget.limit:.2f}", flush=True)
            return _report(output, plan, cases, results, budget, complete=True)
        finally:
            if owned:
                await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--inventory', type=Path, required=True)
    prep.add_argument('--duplicates', type=Path, required=True)
    prep.add_argument('--output', type=Path, required=True)
    prep.add_argument('--budget-usd', type=float, default=10)
    execute = sub.add_parser('run')
    execute.add_argument('--output', type=Path, required=True)
    execute.add_argument('--budget-usd', type=float, required=True)
    execute.add_argument('--stop-after-new-calls', type=int)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare_inventory(args.inventory, args.duplicates, args.output, budget_usd=args.budget_usd)
    else:
        import os
        from dotenv import dotenv_values
        key = os.getenv('OPENAI_API_KEY') or dotenv_values('.env').get('OPENAI_API_KEY', '')
        result = asyncio.run(run(args.output, budget_usd=args.budget_usd, api_key=key,
                                 stop_after_new_calls=args.stop_after_new_calls))
    print(json.dumps({k: v for k, v in result.items() if k in {'experiment_id', 'complete', 'counts', 'cost', 'budget_usd'}}, indent=2))


if __name__ == '__main__':
    main()
