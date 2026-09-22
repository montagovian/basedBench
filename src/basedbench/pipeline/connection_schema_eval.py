"""Schema-only continuation of issue #16's technical-error cases under its total cap.

The first experiment stays replayable. Prompts and semantic validators are reused
unchanged; keyed response objects prevent omitted/repeated/renamed identifiers.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import fcntl
import json
from collections import Counter
from pathlib import Path
import shutil

from basedbench.pipeline import connection_eval as base
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json

VERSION = 'connection-schema-v2'


def keyed_schema(definition, keys, identity_field):
    properties = {k: v for k, v in definition['properties'].items() if k != identity_field}
    item = {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}
    return {'type': 'object', 'properties': {key: copy.deepcopy(item) for key in keys},
            'required': list(keys), 'additionalProperties': False}


def make_request(case, stage, directory, **kwargs):
    body = base.make_request(case, stage, directory, **kwargs)
    schema = body['text']['format']['schema']
    if stage == 'map':
        schema['properties']['comment_roles'] = keyed_schema(schema['$defs']['CommentRole'], base.answers.citation_ids(case), 'comment_id')
    elif stage in {'check', 'verify'}:
        keys = [c['key'] for c in (kwargs.get('mapping') or {}).get('connections', [])]
        schema['properties']['coverage'] = keyed_schema(schema['$defs']['Coverage'], keys, 'key')
    return body


def parse(case, stage, call, mapping=None):
    if call.get('error'):
        return {'error': call['error']}
    try:
        value = json.loads(call['output_text'])
        field, identity = ('comment_roles', 'comment_id') if stage == 'map' else ('coverage', 'key')
        if stage != 'repair':
            if not isinstance(value[field], dict):
                raise ValueError('Expected keyed response object')
            value[field] = [{identity: key, **item} for key, item in value[field].items()]
        return base.parse(case, stage, {**call, 'output_text': json.dumps(value)}, mapping)
    except (ValueError, TypeError, KeyError) as exc:
        return {'error': str(exc)}


def code_hashes():
    return base.code_hashes() | {'connection_schema_eval': file_hash(Path(__file__))}


def prepare(prior: Path, output: Path):
    if output.exists():
        raise FileExistsError('Use a new directory')
    old_plan = json.loads((prior / 'plan.json').read_text())
    base.verify_files(prior, old_plan['files'])
    base.verify_files(prior, json.loads((prior / 'results-manifest.json').read_text()))
    old_report = json.loads((prior / 'report.json').read_text())
    old_results = json.loads((prior / 'results.json').read_text())
    old_cases = json.loads((prior / 'cases.json').read_text())
    if len(old_results) != len(old_cases) or list((prior / 'calls').glob('*.pending')):
        raise ValueError('First comparison must finish before this continuation')
    error_ids = {r['case_id'] for r in old_results if r['status'] == 'error'}
    cases = [c for c in old_cases if c['case_id'] in error_ids]
    if not cases:
        raise ValueError('No technical-error cases to rerun')
    remaining = .25 - old_report['accounted_usd']
    if remaining <= 0 or old_report['allowance_violation']:
        raise ValueError('No budget remaining under the original total cap')
    (output / 'assets').mkdir(parents=True)
    (output / 'calls').mkdir()
    (output / 'requests').mkdir()
    for case in cases:
        sha = case['input']['image_sha256']
        shutil.copyfile(prior / 'assets' / sha, output / 'assets' / sha)
    write_json(output / 'cases.json', cases)
    bounds = {}
    for case in cases:
        for stage in base.STAGES:
            body = make_request(case, stage, output, explanation=case['input']['explanation'])
            if stage != 'map':
                body['input'][0]['content'][0]['text'] += 'x' * 48000
            bounds[case['case_id'] + '.' + stage] = base.checks.request_bound(body, stage)
    plan = {'version': VERSION, 'budget_usd': remaining, 'total_budget_usd': .25,
            'prior_accounted_usd': old_report['accounted_usd'],
            'prior_files': {str((prior / n).resolve()): file_hash(prior / n) for n in ('plan.json', 'report.json', 'results.json', 'results-manifest.json')},
            'code_hashes': code_hashes(), 'model': base.checks.MODEL, 'prices': base.checks.PRICES,
            'request_bounds_usd': bounds, 'max_calls': len(bounds), 'max_concurrency': 3,
            'input_hashes': {c['case_id']: digest(c['input']) for c in cases},
            'prompts': old_plan['prompts'], 'semantic_prompts_changed': False, 'automatic_retries': 0,
            'selection': 'Exactly the first experiment outcomes with technical status error; no successful or semantic-unresolved cases repeated.',
            'files': {str(p.relative_to(output)): file_hash(p) for p in output.rglob('*') if p.is_file()}}
    if plan['prompts'] != {'map': base.MAP, 'check': base.CHECK, 'repair': base.REPAIR}:
        raise ValueError('Semantic prompts changed')
    plan['experiment_id'] = digest(plan)
    write_json(output / 'plan.json', plan)
    return plan


async def run(output: Path, *, api_key='', client=None):
    import openai
    plan = json.loads((output / 'plan.json').read_text())
    if plan['version'] != VERSION or plan['code_hashes'] != code_hashes() or digest({k: v for k, v in plan.items() if k != 'experiment_id'}) != plan['experiment_id']:
        raise ValueError('Frozen continuation configuration changed')
    base.verify_files(output, plan['files'])
    for path, sha in plan['prior_files'].items():
        if file_hash(Path(path)) != sha:
            raise ValueError('Prior comparison changed')
    if plan['budget_usd'] + plan['prior_accounted_usd'] > .25 + 1e-12:
        raise ValueError('Total cap exceeded')
    owned = client is None
    if owned:
        client = openai.AsyncOpenAI(api_key=api_key, max_retries=0, timeout=180)
    try:
        with (output / 'run.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if (output / 'results-manifest.json').exists():
                base.verify_files(output, json.loads((output / 'results-manifest.json').read_text()))
            budget = base.checks.Budget(plan, output)
            halted = any(json.loads(p.read_text()).get('fatal_provider_error') for p in (output / 'calls').glob('*.json'))
            results = []
            cases = json.loads((output / 'cases.json').read_text())
            semaphore = asyncio.Semaphore(plan['max_concurrency'])
            async def one_case(case):
                async with semaphore:
                    async def invoke(stage, **kwargs):
                        nonlocal halted
                        key = case['case_id'] + '.' + stage
                        body = make_request(case, stage, output, **kwargs)
                        if base.checks.request_bound(body, stage) > plan['request_bounds_usd'][key] + 1e-12:
                            raise ValueError('Request exceeds frozen allowance')
                        request_path = output / 'requests' / (key + '.json')
                        if request_path.exists() and json.loads(request_path.read_text()) != body:
                            raise ValueError('Request changed on replay')
                        if not request_path.exists():
                            write_json(request_path, body)
                        path = output / 'calls' / (key + '.json')
                        if halted and not path.exists():
                            return {'error': 'fatal_provider_stop'}
                        row = {'post_id': case['case_id'], 'input_sha256': plan['input_hashes'][case['case_id']]}
                        await base.transport.collect_calls(client, [row], output, output, {**plan, 'arms': [stage]},
                            concurrency=1, request_factory=lambda *_: body, budget=budget)
                        call = json.loads(path.read_text())
                        if call['post_id'] != case['case_id'] or call['arm'] != stage or call.get('request_content_sha256') not in {None, digest(body)}:
                            raise ValueError('Saved call identity mismatch')
                        if call.get('request_content_sha256') is None and call['status'] not in {'unknown', 'not_started'}:
                            raise ValueError('Response missing request provenance')
                        halted |= bool(call.get('fatal_provider_error'))
                        if budget.violated:
                            return {'error': 'budget_allowance_violation'}
                        return parse(case, stage, call, kwargs.get('mapping'))
                    result = await base.evaluate(case, invoke)
                    results.append(result)
                    results.sort(key=lambda r: r['case_id'])
                    write_json(output / 'results.json', results)
                    print(f"Recorded {len(results)}/{len(cases)} cases; combined accounted ${plan['prior_accounted_usd'] + sum(budget.charges.values()):.5f}/$0.25", flush=True)
            await asyncio.gather(*(one_case(case) for case in cases))
            calls = [json.loads(p.read_text()) for p in sorted((output / 'calls').glob('*.json'))]
            report = {'experiment_id': plan['experiment_id'], 'cases': len(results),
                'statuses': dict(Counter(r['status'] for r in results)), 'calls': len(calls),
                'completed_calls': sum(c['status'] == 'completed' for c in calls),
                'parse_errors': sum(bool(v.get('error')) for r in results for v in r['stages'].values()),
                'repairs_verified': sum(r['repaired'] for r in results),
                'cost_estimate_usd': sum(base.answers.exact_cost(c) or 0 for c in calls),
                'accounted_usd': sum(budget.charges.values()), 'allowance_violation': budget.violated,
                'unknown_usage_calls': sum(c.get('usage') is None for c in calls),
                'combined_accounted_usd': plan['prior_accounted_usd'] + sum(budget.charges.values()),
                'budget_usd': budget.limit, 'total_budget_usd': .25, 'independent_validation': False}
            write_json(output / 'report.json', report)
            write_json(output / 'results-manifest.json', {str(p.relative_to(output)): file_hash(p) for p in output.rglob('*')
                if p.is_file() and (p.parent.name in {'calls', 'requests'} or p.name in {'results.json', 'report.json'})})
            return report
    finally:
        if owned:
            await client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('prior', type=Path)
    prep.add_argument('output', type=Path)
    paid = sub.add_parser('run')
    paid.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        plan = prepare(args.prior, args.output)
        print(json.dumps({k: plan[k] for k in ('experiment_id', 'budget_usd', 'prior_accounted_usd', 'max_calls')}))
    else:
        import os
        from dotenv import dotenv_values
        key = os.getenv('OPENAI_API_KEY') or dotenv_values('.env').get('OPENAI_API_KEY')
        print(json.dumps(asyncio.run(run(args.output, api_key=key))))


if __name__ == '__main__':
    main()
