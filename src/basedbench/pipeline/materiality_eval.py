"""A frozen, prompt-only materiality comparison with separately attributed human labels."""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
from pathlib import Path
import shutil

from basedbench.pipeline import calibrated_eval as calibrated, capacity_eval as capacity
from basedbench.pipeline import focused_connection_eval as focused
from basedbench.pipeline.connection_eval import verify_files
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json

VERSION = 'materiality-comparison-v1'
MODEL = 'gpt-6-luna'
ARMS = ('baseline', 'materiality')
NEW_READY = ('1u8dptp', '1u2ywbz')
READY_IDS = focused.READY_IDS + NEW_READY
REPEATS = focused.REPEATS + NEW_READY
STRESS_IDS = tuple(cid for cid in focused.STRESS_IDS if cid not in NEW_READY)
PARAGRAPH = """Judge semantic sufficiency, not exhaustive description. An omission is material
when it leaves an essential decoding, relation, referent or contrast unresolved,
or substitutes a different core joke. Before failing, check whether the written
answer already conveys that meaning through a concise or broader faithful
paraphrase. In your existing reason field, identify the essential meaning that
is absent or wrong and why the written answer does not convey it. Identifying
an unmentioned detail is not by itself a reason to fail. Do not require every
visible cue, proper name, literal caption, secondary wording or background fact
when the answer already supplies enough meaning to grade the intended joke.
Your own inference of an absent essential decoding still does not repair the
answer. A richer alternative, optional detail, familiarity, easiness, aesthetic
taste or a theory of humor is not required. Do not claim a defect solely because
another interpretation is imaginable. Do not assert an author's motive,
minority embellishment, fictional accusation or joke as established fact.
Use uncertain when an essential connection or competing core readings cannot
be resolved."""
_paragraphs = calibrated.SIMPLE.split('\n\n')
assert _paragraphs[2].startswith('Pass concise paraphrases')
MATERIALITY = '\n\n'.join([*_paragraphs[:2], PARAGRAPH, *_paragraphs[3:]])


def request(case, arm, directory):
    if arm not in ARMS:
        raise ValueError('Unknown materiality condition')
    body = capacity.request(case, 'luna', directory)
    if arm == 'materiality':
        body['instructions'] = MATERIALITY
        body['prompt_cache_key'] = 'basedbench-materiality-' + digest(MATERIALITY)[:24]
    return body


def code_hashes():
    return capacity.code_hashes() | {'materiality_eval': file_hash(Path(__file__))}


def identified(directory, filename, key):
    manifest = json.loads((directory / filename).read_text())
    if digest({k: v for k, v in manifest.items() if k != key}) != manifest[key]:
        raise ValueError('Source identity changed')
    verify_files(directory, manifest['files'])
    return manifest


def prepare(source, human, access, output):
    if output.exists():
        raise FileExistsError('Use a new materiality experiment directory')
    old = identified(source, 'plan.json', 'experiment_id')
    verify_files(source, json.loads((source / 'results-manifest.json').read_text()))
    if old['version'] != capacity.VERSION or old['code_hashes'] != capacity.code_hashes():
        raise ValueError('Frozen capacity source changed')
    snapshot = identified(human, 'manifest.json', 'snapshot_id')
    metadata = json.loads(access.read_text())
    if [m['id'] for m in metadata['models']] != [MODEL] or metadata['inference_calls'] != 0:
        raise ValueError('Expected read-only access check for the exact Luna model')
    cases = json.loads((source / 'cases.json').read_text())
    expected = set(focused.REPAIR_IDS + READY_IDS + STRESS_IDS)
    if len(cases) != 20 or {c['case_id'] for c in cases} != expected or len({c['group_id'] for c in cases}) != 20:
        raise ValueError('Expected the same twenty family-distinct cases')
    new_cases = json.loads((human / 'cases.json').read_text())
    feedback = json.loads((human / 'human-feedback.json').read_text())
    if (len(new_cases) != 2 or len(feedback) != 2
            or {c['case_id'] for c in new_cases} != set(NEW_READY)
            or {r['post_id'] for r in feedback} != set(NEW_READY)):
        raise ValueError('Expected exactly the two newly reviewed cases')
    latest = {e['post_id']: e for e in (json.loads(line) for line in (human / 'events.jsonl').read_text().splitlines())
              if e['kind'] == 'feedback'}
    overlay = []
    for c in cases:
        cid = c['case_id']
        expected_quality = 'repair' if cid in focused.REPAIR_IDS else 'ready' if cid in focused.READY_IDS else None
        if c.get('original_quality') != expected_quality:
            raise ValueError('Original human provenance changed')
        if calibrated.image_error(source / 'assets' / c['input']['image_sha256']):
            raise ValueError('Unsupported image; do not replace identities')
        c['original_selection_stratum'] = c['stratum']
        if cid in NEW_READY:
            h = next(r for r in new_cases if r['case_id'] == cid)
            r = next(r for r in feedback if r['post_id'] == cid)
            if (h['input'] != c['input'] or h['original_quality'] != 'ready'
                    or r['event'] != latest.get(cid) or h['human_event_id'] != r['event']['event_id']
                    or r['event']['fields'].get('quality_a') != 'ready'
                    or r['answers'] != [{'source': 'original', 'quality': 'ready',
                                         'text_sha256': digest(c['input']['explanation'])}]):
                raise ValueError('Human overlay must match the exact answer and saved event')
            c.update(original_quality='ready', human_event_id=h['human_event_id'],
                     human_review_stratum=h['stratum'], human_snapshot_id=snapshot['snapshot_id'])
            overlay.append({'case_id': cid, 'previous_quality': None, 'human_snapshot_id': snapshot['snapshot_id'],
                            'source_input_sha256': digest(c['input']), 'feedback': r})
        elif cid in STRESS_IDS:
            c.pop('original_quality', None)
        c['evaluation_role'] = 'human_' + c['original_quality'] if 'original_quality' in c else 'assistant_stress_unlabeled'
    # The approved paragraph is part of the frozen recipe, not adjusted after outcomes.
    doc = Path('docs/materiality-comparison-plan.md').read_text()
    if '\n'.join(line[2:] for line in doc.splitlines() if line.startswith('> ')) != PARAGRAPH:
        raise ValueError('Candidate paragraph differs from the declared plan')
    output.mkdir(parents=True)
    for sub in ('assets', 'requests', 'calls'):
        (output / sub).mkdir()
    write_json(output / 'cases.json', cases)
    write_json(output / 'human-label-overlay.json', overlay)
    shutil.copyfile(access, output / 'model-access.json')
    for c in cases:
        sha = c['input']['image_sha256']
        shutil.copyfile(source / 'assets' / sha, output / 'assets' / sha)
    jobs, bounds = [], {}
    for c in cases:
        for arm in ARMS:
            for repeat in range(2 if c['case_id'] in REPEATS else 1):
                key = f"{c['case_id']}.{arm}_r{repeat}"
                body = request(c, arm, output)
                write_json(output / 'requests' / (key + '.json'), body)
                bounds[key] = capacity.bound(body)
                jobs.append({'key': key, 'case_id': c['case_id'], 'arm': arm, 'repeat': repeat,
                             'model': MODEL, 'request_sha256': digest(body)})
    jobs.sort(key=lambda j: digest([VERSION, 'dispatch', j['key']]))
    assert len(jobs) == 56
    plan = {'version': VERSION, 'phase': 'exposed_materiality_development', 'arms': list(ARMS), 'model': MODEL,
            'jobs': jobs, 'max_calls': 56, 'budget_usd': 1., 'max_concurrency': 3, 'automatic_retries': 0,
            'request_bounds_usd': bounds, 'prices': capacity.PRICES[MODEL], 'prices_checked_on': '2026-09-23',
            'pricing_source': 'https://developers.openai.com/api/docs/models/gpt-6-luna',
            'repeated_case_ids': list(REPEATS), 'primary_case_ids': list(focused.PRIMARY_IDS),
            'human_labels_available': True, 'human_label_scope': list(focused.REPAIR_IDS + READY_IDS),
            'unlabeled_stress_cases': list(STRESS_IDS), 'independent_validation': False, 'input_errors': {},
            'source_plan_sha256': file_hash(source / 'plan.json'),
            'source_results_manifest_sha256': file_hash(source / 'results-manifest.json'),
            'human_snapshot_manifest_sha256': file_hash(human / 'manifest.json'),
            'input_hashes': {c['case_id']: digest(c['input']) for c in cases}, 'code_hashes': code_hashes(),
            'plan_document_sha256': file_hash(Path('docs/materiality-comparison-plan.md')),
            'criteria': {'primary_both_checks': 3, 'ready_first_pass': 8, 'ready_repeat_pass': 5,
                         'repair_first_fail_min': 8, 'adequacy_flips_max': 1, 'no_more_flips_than_baseline': True,
                         'technical_errors_max': 0, 'matching_rationale_and_stress_inspection_required': True},
            'files': {str(p.relative_to(output)): file_hash(p) for p in sorted(output.rglob('*')) if p.is_file()}}
    plan['experiment_id'] = digest(plan)
    write_json(output / 'plan.json', plan)
    return plan


def report_for(plan, cases, results, calls, budget):
    report = calibrated.report_for(plan, cases, results, calls, budget)
    lookup = {(r['case_id'], r['arm'], r['repeat']): r['result'].get('answer_quality') for r in results}
    counts = {}
    for arm in ARMS:
        q = lambda cid, repeat=0: lookup.get((cid, arm, repeat))
        counts[arm] = {'primary_both_fail': sum(all(q(cid, r) == 'fail' for r in (0, 1)) for cid in focused.PRIMARY_IDS),
                       'ready_first_pass': sum(q(cid) == 'pass' for cid in READY_IDS),
                       'ready_repeat_pass': sum(q(cid, 1) == 'pass' for cid in REPEATS if cid in READY_IDS),
                       'repair_first_fail': sum(q(cid) == 'fail' for cid in focused.REPAIR_IDS),
                       'adequacy_flips': report['stability'][arm]['different_answer_quality']}
    m, b = counts['materiality'], counts['baseline']
    passed = (m['primary_both_fail'] == 3 and m['ready_first_pass'] == 8 and m['ready_repeat_pass'] == 5
              and m['repair_first_fail'] >= 8 and m['adequacy_flips'] <= min(1, b['adequacy_flips']))
    report.update(complete=len(results) == len(plan['jobs']),
                  materiality_criteria={'counts': counts, 'quantitative_quality_criteria_met': passed,
                                       'rationale_and_stress_inspection': 'not_automatically_scored'},
                  limits=['Twenty exposed cases; seventeen human original-answer labels and three unlabeled stress cases.',
                          'Original selection strata are preserved; two new human labels are a separate overlay.',
                          'Answer adequacy and substantive comment support remain separate; rationale inspection is required.'])
    report['quantitative_screen_pass'] = (passed and report['complete'] and not report['technical_errors']
        and not report['unknown_usage_calls'] and not report['allowance_violation'])
    return report


async def run(output, *, api_key='', client=None):
    plan = json.loads((output / 'plan.json').read_text())
    if (plan['version'] != VERSION or plan['code_hashes'] != code_hashes()
            or digest({k: v for k, v in plan.items() if k != 'experiment_id'}) != plan['experiment_id']
            or plan['plan_document_sha256'] != file_hash(Path('docs/materiality-comparison-plan.md'))):
        raise ValueError('Frozen materiality plan or implementation changed')
    verify_files(output, plan['files'])
    if not 0 < plan['budget_usd'] <= 1 or len(plan['jobs']) != 56 or plan['model'] != MODEL:
        raise ValueError('Outside frozen materiality comparison scope')
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
            budget = capacity.Budget(plan, output)
            halted = any(json.loads(p.read_text()).get('fatal_provider_error') for p in (output / 'calls').glob('*.json'))
            results = []
            semaphore = asyncio.Semaphore(plan['max_concurrency'])
            async def one(job):
                nonlocal halted
                async with semaphore:
                    key = job['key']; cid, tag = key.split('.')
                    body = json.loads((output / 'requests' / (key + '.json')).read_text())
                    if digest(body) != job['request_sha256'] or capacity.bound(body) > plan['request_bounds_usd'][key] + 1e-12:
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
                                    'result': capacity.parse(by_id[cid], 'luna', call)})
                    if len(results) % 10 == 0:
                        print(f'Recorded {len(results)}/56; accounted ${sum(budget.charges.values()):.4f}/$1', flush=True)
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
    for arg in ('source', 'human', 'access', 'output'):
        a.add_argument(arg, type=Path)
    a = sub.add_parser('run'); a.add_argument('output', type=Path)
    args = p.parse_args()
    if args.command == 'prepare':
        plan = prepare(args.source, args.human, args.access, args.output)
        print(json.dumps({k: plan[k] for k in ('experiment_id', 'max_calls', 'budget_usd')}))
    else:
        import os
        from dotenv import dotenv_values
        key = os.getenv('OPENAI_API_KEY') or dotenv_values('.env').get('OPENAI_API_KEY')
        print(json.dumps(asyncio.run(run(args.output, api_key=key)), indent=2))
