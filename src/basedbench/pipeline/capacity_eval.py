"""Frozen Luna/Sol capacity comparison with identical checker requests."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
import fcntl
import json
from pathlib import Path
import shutil

from basedbench.pipeline import focused_connection_eval as focused
from basedbench.pipeline import calibrated_eval as calibrated
from basedbench.pipeline.connection_eval import verify_files
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json

VERSION = 'capacity-comparison-v1'
MODELS = {'luna': 'gpt-6-luna', 'sol': 'gpt-6-sol'}
PRICES = {'gpt-6-luna': {'input': .10, 'cached': .01, 'write': .125, 'output': .50},
          'gpt-6-sol': {'input': 2., 'cached': .20, 'write': 2.50, 'output': 10.}}


def request(case, arm, directory):
    body = focused.request(case, 'baseline', directory)
    body['model'] = MODELS[arm]
    return body


def price(usage, model, *, conservative=False):
    if usage is None:
        return None
    n, out = usage.get('input_tokens'), usage.get('output_tokens')
    details = usage.get('input_tokens_details') or {}
    cached, written = details.get('cached_tokens', 0), details.get('cache_write_tokens', 0)
    if any(type(v) is not int or v < 0 for v in (n, out, cached, written)) or cached + written > n:
        return None
    rates = PRICES[model]
    input_cost = (n * rates['write'] if conservative else
                  (n-cached-written)*rates['input'] + cached*rates['cached'] + written*rates['write'])
    in_scale, out_scale = (2, 1.5) if n > 272000 else (1, 1)
    return (input_cost*in_scale + out*rates['output']*out_scale) / 1e6


def bound(body):
    rates = PRICES[body['model']]
    return (1050000*2*rates['write'] + body['max_output_tokens']*1.5*rates['output']) / 1e6


class Budget(calibrated.Budget):
    def settle(self, pid, arm, call):
        key = f'{pid}.{arm}'
        amount = price(call.get('usage'), self.job_models[key], conservative=True)
        self.unknown |= amount is None
        self.charges[key] = self.bounds[key] if amount is None else amount
        self.violated |= self.charges[key] > self.bounds[key] + 1e-12
        self.active.discard(key)
        self.changed.set()


def parse(case, arm, call):
    if call.get('error') or call.get('status') != 'completed':
        return {'error': call.get('error') or 'Incomplete response'}
    if call.get('response', {}).get('model') != MODELS[arm]:
        return {'error': 'Unexpected returned model identity'}
    try:
        v = calibrated.SimpleCheck.model_validate_json(call['output_text']).model_dump()
        if not set(v['supporting_comment_ids']) <= set(calibrated.answers.citation_ids(case)):
            raise ValueError('Unknown evidence ID')
        v['verdict'] = ('fail' if v['answer_quality'] == 'fail' else 'pass'
                        if v['answer_quality'] == 'pass' and v['evidence_status'] == 'supported' else 'uncertain')
        return v
    except (ValueError, KeyError, TypeError) as exc:
        return {'error': str(exc)}


def code_hashes():
    return focused.code_hashes() | {'capacity_eval': file_hash(Path(__file__))}


def prepare(source, output, access):
    if output.exists():
        raise FileExistsError('Use a new capacity experiment directory')
    old_plan = json.loads((source / 'plan.json').read_text())
    verify_files(source, old_plan['files'])
    verify_files(source, json.loads((source / 'results-manifest.json').read_text()))
    if old_plan['version'] != focused.VERSION or old_plan['code_hashes'] != focused.code_hashes():
        raise ValueError('Source focused experiment changed')
    metadata = json.loads(access.read_text())
    if {m['id'] for m in metadata['models']} != set(MODELS.values()):
        raise ValueError('Read-only account access must cover both exact model IDs')
    cases = json.loads((source / 'cases.json').read_text())
    expected = set(focused.REPAIR_IDS + focused.READY_IDS + focused.STRESS_IDS)
    if {c['case_id'] for c in cases} != expected or len(cases) != 20 or len({c['group_id'] for c in cases}) != 20:
        raise ValueError('Reuse the same twenty diagnostic cases and known families')
    for c in cases:
        quality = ('repair' if c['case_id'] in focused.REPAIR_IDS else 'ready'
                   if c['case_id'] in focused.READY_IDS else None)
        if c.get('original_quality') != quality:
            raise ValueError('Human provenance must match the frozen source')
        if calibrated.image_error(source / 'assets' / c['input']['image_sha256']):
            raise ValueError('Unsupported image; do not replace selected identities')
    output.mkdir(parents=True)
    for sub in ('assets', 'requests', 'calls'):
        (output / sub).mkdir()
    shutil.copyfile(source / 'cases.json', output / 'cases.json')
    shutil.copyfile(access, output / 'model-access.json')
    for c in cases:
        sha = c['input']['image_sha256']
        shutil.copyfile(source / 'assets' / sha, output / 'assets' / sha)
    jobs, bounds = [], {}
    for c in cases:
        for arm, model in MODELS.items():
            for repeat in range(2 if c['case_id'] in focused.REPEATS else 1):
                key = f"{c['case_id']}.{arm}_r{repeat}"
                body = request(c, arm, output)
                write_json(output / 'requests' / (key + '.json'), body)
                bounds[key] = bound(body)
                jobs.append({'key': key, 'case_id': c['case_id'], 'arm': arm, 'repeat': repeat,
                             'model': model, 'request_sha256': digest(body)})
    jobs.sort(key=lambda j: digest([VERSION, 'dispatch', j['key']]))
    if len(jobs) != 52:
        raise ValueError("Capacity plan must contain exactly 52 jobs")
    plan = {'version': VERSION, 'phase': 'exposed_capacity_development', 'arms': list(MODELS),
            'models': MODELS, 'jobs': jobs, 'max_calls': 52, 'budget_usd': 10.,
            'max_concurrency': 3, 'automatic_retries': 0, 'request_bounds_usd': bounds,
            'prices': PRICES, 'prices_checked_on': '2026-09-22',
            'pricing_sources': ['https://developers.openai.com/api/docs/models/' + m for m in MODELS.values()],
            'repeated_case_ids': list(focused.REPEATS), 'primary_case_ids': list(focused.PRIMARY_IDS),
            'human_labels_available': True, 'human_label_scope': list(focused.REPAIR_IDS + focused.READY_IDS),
            'unlabeled_stress_cases': list(focused.STRESS_IDS), 'independent_validation': False,
            'input_errors': {}, 'source_plan_sha256': file_hash(source / 'plan.json'),
            'source_results_manifest_sha256': file_hash(source / 'results-manifest.json'),
            'input_hashes': {c['case_id']: digest(c['input']) for c in cases},
            'code_hashes': code_hashes(), 'plan_document_sha256': file_hash(Path('docs/capacity-comparison-plan.md')),
            'criteria': old_plan['criteria'],
            'files': {str(p.relative_to(output)): file_hash(p) for p in sorted(output.rglob('*')) if p.is_file()}}
    plan['experiment_id'] = digest(plan)
    write_json(output / 'plan.json', plan)
    return plan


def report_for(plan, cases, results, calls, budget):
    lookup = {(r['case_id'], r['arm'], r['repeat']): r['result'] for r in results}
    metrics = defaultdict(lambda: defaultdict(Counter))
    adequacy = defaultdict(lambda: defaultdict(Counter))
    stability, counts = {}, {}
    for c in cases:
        for arm in MODELS:
            v = lookup.get((c['case_id'], arm, 0), {})
            gold = c.get('original_quality', 'unlabeled')
            metrics[c['stratum']][arm][gold + ':' + v.get('verdict', 'error')] += 1
            adequacy[c['stratum']][arm][gold + ':' + v.get('answer_quality', 'error')] += 1
    for arm in MODELS:
        q = lambda cid, repeat=0: lookup.get((cid, arm, repeat), {}).get('answer_quality')
        pairs = [(lookup.get((cid, arm, 0), {}), lookup.get((cid, arm, 1), {})) for cid in focused.REPEATS]
        valid = [(a, b) for a, b in pairs if 'verdict' in a and 'verdict' in b]
        stability[arm] = {'paired_valid': len(valid),
                          'different_gate_verdicts': sum(a['verdict'] != b['verdict'] for a, b in valid),
                          'different_answer_quality': sum(a['answer_quality'] != b['answer_quality'] for a, b in valid)}
        counts[arm] = {'primary_both_fail': sum(all(q(cid, r) == 'fail' for r in (0, 1)) for cid in focused.PRIMARY_IDS),
                       'ready_first_pass': sum(q(cid) == 'pass' for cid in focused.READY_IDS),
                       'ready_repeat_pass': sum(q(cid, 1) == 'pass' for cid in focused.REPEATS if cid in focused.READY_IDS),
                       'repair_first_fail': sum(q(cid) == 'fail' for cid in focused.REPAIR_IDS),
                       'adequacy_flips': stability[arm]['different_answer_quality']}
    sol, luna = counts['sol'], counts['luna']
    quality_pass = (sol['primary_both_fail'] == 3 and sol['ready_first_pass'] == 6 and sol['ready_repeat_pass'] == 3
                    and sol['repair_first_fail'] >= 8 and sol['adequacy_flips'] <= min(1, luna['adequacy_flips']))
    by_key = {j['key']: j for j in plan['jobs']}
    cost = lambda c: price(c.get('usage'), by_key[c['post_id'] + '.' + c['arm']]['model'])
    serial = lambda v: {s: {a: dict(n) for a, n in arms.items()} for s, arms in v.items()}
    report = {'experiment_id': plan['experiment_id'], 'phase': plan['phase'], 'cases': len(cases),
              'calls': len(calls), 'planned_calls': len(plan['jobs']), 'input_errors': {},
              'completed_calls': sum(c['status'] == 'completed' for c in calls),
              'technical_errors': sum(bool(r['result'].get('error')) for r in results),
              'unknown_usage_calls': sum(cost(c) is None for c in calls),
              'cost_estimate_usd': sum(cost(c) or 0 for c in calls),
              'accounted_usd': sum(budget.charges.values()), 'budget_usd': plan['budget_usd'],
              'allowance_violation': budget.violated, 'complete': len(results) == len(plan['jobs']),
              'metrics': serial(metrics), 'separate_answer_adequacy': serial(adequacy), 'stability': stability,
              'capacity_criteria': {'counts': counts, 'quantitative_quality_criteria_met': quality_pass,
                                    'rationale_and_stress_inspection': 'not_automatically_scored'},
              'cost_by_arm': {a: sum(cost(c) or 0 for c in calls if by_key[c['post_id'] + '.' + c['arm']]['arm'] == a) for a in MODELS},
              'limits': ['Twenty selected exposed cases; fifteen human labels and five unlabeled stress cases.',
                         'Answer adequacy and substantive comment support are separate judgments.',
                         'Quantitative outcomes still require inspection of rationales and stress cases.']}
    report['quantitative_screen_pass'] = (quality_pass and report['complete'] and not report['technical_errors']
        and not report['unknown_usage_calls'] and not report['allowance_violation'])
    return report


async def run(output, *, api_key='', client=None):
    plan = json.loads((output / 'plan.json').read_text())
    if (plan['version'] != VERSION or plan['code_hashes'] != code_hashes()
            or digest({k: v for k, v in plan.items() if k != 'experiment_id'}) != plan['experiment_id']):
        raise ValueError('Frozen capacity plan or implementation changed')
    verify_files(output, plan['files'])
    if not 0 < plan['budget_usd'] <= 10 or len(plan['jobs']) != 52 or plan['models'] != MODELS:
        raise ValueError('Outside frozen capacity comparison scope')
    owned = client is None
    if owned:
        import openai
        client = openai.AsyncOpenAI(api_key=api_key, max_retries=0, timeout=180)
    try:
        with (output / 'run.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if (output / 'results-manifest.json').exists():
                verify_files(output, json.loads((output / 'results-manifest.json').read_text()))
                return json.loads((output / 'report.json').read_text())
            cases = json.loads((output / 'cases.json').read_text())
            by_id = {c['case_id']: c for c in cases}
            budget = Budget(plan, output)
            halted = any(json.loads(p.read_text()).get('fatal_provider_error') for p in (output / 'calls').glob('*.json'))
            results = []
            semaphore = asyncio.Semaphore(plan['max_concurrency'])
            async def one(job):
                nonlocal halted
                async with semaphore:
                    key = job['key']; cid, tag = key.split('.')
                    body = json.loads((output / 'requests' / (key + '.json')).read_text())
                    if digest(body) != job['request_sha256'] or bound(body) > plan['request_bounds_usd'][key] + 1e-12:
                        raise ValueError('Frozen request changed')
                    path = output / 'calls' / (key + '.json')
                    if not path.exists() and (halted or budget.unknown or budget.violated):
                        return
                    row = {'post_id': cid, 'input_sha256': plan['input_hashes'][cid]}
                    await calibrated.transport.collect_calls(client, [row], output, output, {**plan, 'arms': [tag]},
                        concurrency=1, request_factory=lambda *_: body, budget=budget)
                    call = json.loads(path.read_text())
                    if call.get('request_content_sha256') not in {None, digest(body)}:
                        raise ValueError('Response/request mismatch')
                    halted |= bool(call.get('fatal_provider_error'))
                    results.append({'case_id': cid, 'arm': job['arm'], 'repeat': job['repeat'],
                                    'result': parse(by_id[cid], job['arm'], call)})
                    if len(results) % 10 == 0:
                        print(f'Recorded {len(results)}/52; accounted ${sum(budget.charges.values()):.4f}/$10', flush=True)
            await asyncio.gather(*(one(j) for j in plan['jobs']))
            results.sort(key=lambda r: (r['case_id'], r['arm'], r['repeat']))
            write_json(output / 'results.json', results)
            calls = [json.loads(p.read_text()) for p in sorted((output / 'calls').glob('*.json'))]
            report = report_for(plan, cases, results, calls, budget)
            write_json(output / 'report.json', report)
            write_json(output / 'results-manifest.json', {str(p.relative_to(output)): file_hash(p)
                for p in sorted(output.rglob('*')) if p.is_file()
                and (p.parent.name == 'calls' or p.name in {'results.json', 'report.json'})})
            return report
    finally:
        if owned:
            await client.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('prepare')
    a.add_argument('source', type=Path); a.add_argument('output', type=Path); a.add_argument('access', type=Path)
    a = sub.add_parser('run'); a.add_argument('output', type=Path)
    args = p.parse_args()
    if args.command == 'prepare':
        plan = prepare(args.source, args.output, args.access)
        print(json.dumps({k: plan[k] for k in ('experiment_id', 'max_calls', 'budget_usd')}))
    else:
        import os
        from dotenv import dotenv_values
        key = os.getenv('OPENAI_API_KEY') or dotenv_values('.env').get('OPENAI_API_KEY')
        print(json.dumps(asyncio.run(run(args.output, api_key=key)), indent=2))
