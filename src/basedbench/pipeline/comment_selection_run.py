"""One frozen follow-up of Jev relevance filtering and first-read ordering."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile

from basedbench.pipeline.curation_corpus import canonical_json, digest, file_hash
from basedbench.pipeline import evidence_ranking_run as previous
from basedbench.pipeline import comment_selection_policy as policy
from basedbench.pipeline.evidence_ranking_io import Store, RESERVE_USD

VERSION = 'comment-selection-v2'
TOTAL_BUDGET = 1.0
PRIOR_SPENT = .075391344
PRIOR_PLAN_ID = '3953282d61fb8a96709690be447fd3078b96633c0ba8dc98ba1852cc8531d934'
LIMITS = {'max_calls': 340, 'max_questions': 20000}
METHODS = ('baseline', 'pointwise', 'pairwise')
DEVELOPMENT_REVIEWS = ('R03', 'R08', 'R12', 'R14')
read, atomic = previous.read, previous.atomic


def code_hashes():
    here = Path(__file__).resolve().parent
    repo = here.parents[2]
    files = [here / 'comment_selection_policy.py', here / 'comment_selection_run.py',
             here.parent / 'comment_selection_feedback.py']
    return {**previous.code_hashes(), **{str(p.relative_to(repo)): file_hash(p) for p in files}}


def review_selection(cases, old_review):
    by_review = {c['review_id']: c for c in old_review}
    if any(rid not in by_review for rid in DEVELOPMENT_REVIEWS):
        raise ValueError('Development review missing')
    development = {by_review[rid]['family_id'] for rid in DEVELOPMENT_REVIEWS}
    old_groups = {c['family_id'] for c in old_review}
    all_groups = {c['group_id'] for c in cases}
    if len(development) != 4 or not old_groups <= all_groups:
        raise ValueError('Review family mismatch')
    fresh = sorted(all_groups - old_groups, key=lambda g: digest([VERSION, 'new-review', g]))[:4]
    if len(fresh) != 4:
        raise ValueError('Insufficient newly reviewed families')
    chosen = sorted(development, key=lambda g: digest([VERSION, 'order', g])) + fresh
    return [{'review_id': f'S{i+1:02}', 'family_id': group,
             'sample_kind': 'development' if group in development else 'newly_reviewed',
             'methods': dict(zip(('A', 'B'), ('baseline', 'pairwise') if i % 2 == 0
                                 else ('pairwise', 'baseline'), strict=True))}
            for i, group in enumerate(chosen)]


def preflight(cases, budget):
    rows, preview = [], None
    for case in cases:
        bodies = policy.comment_requests(case) + policy.pair_requests(case)
        if bodies and preview is None:
            preview = bodies[0]
        rows.append({'case_id': case['case_id'], 'calls': len(bodies),
                     'questions': sum(len(b['questions']) for b in bodies),
                     'largest_request_bytes': max((len(canonical_json(b).encode()) for b in bodies), default=0)})
    calls = sum(r['calls'] for r in rows)
    questions = sum(r['questions'] for r in rows)
    if calls > LIMITS['max_calls'] or questions > LIMITS['max_questions']:
        raise ValueError('Request/question preflight exceeds limit')
    if calls * RESERVE_USD > budget + 1e-12:
        raise ValueError('Worst-case preflight exceeds remaining budget')
    return rows, preview


def prepare(source: Path, root: Path, anchors: Path):
    source, root, anchors = source.resolve(), root.resolve(), anchors.resolve()
    if root.exists():
        raise FileExistsError('Preserve existing runs; choose a new output directory')
    if root.is_relative_to(source):
        raise ValueError('New run cannot be inside source run')
    verified = previous.replay(source)
    if read(source / 'plan.json')['plan_id'] != PRIOR_PLAN_ID:
        raise ValueError('This is not the intended frozen v1 source run')
    accounting = verified['provider_ledger']
    prior_spent = accounting['spent_usd']
    if accounting['pending_calls'] or accounting['stop_reason'] or prior_spent != PRIOR_SPENT:
        raise ValueError('Previous budget is not settled')
    remaining = TOTAL_BUDGET - prior_spent
    original_cases = read(source / 'cases.json')
    old_outcomes = read(source / 'outcomes.json')
    baselines = {o['case_id']: o['packs']['rank'] for o in old_outcomes}
    if len(baselines) != len(original_cases) or set(baselines) != {c['case_id'] for c in original_cases}:
        raise ValueError('Baseline coverage mismatch')
    cases = [{k: c[k] for k in ('case_id', 'group_id', 'post_id', 'comments', 'observation', 'image_sha256')}
             for c in original_cases]
    for case in cases:
        case['image_path'] = str(root / 'images' / case['image_sha256'])
        policy.build_lists(case, baselines[case['case_id']], None)  # Validate baseline before spending.
    if (len(cases), sum(len(c['comments']) for c in cases)) != (81, 760):
        raise ValueError('Frozen source composition changed')
    # Human provenance is a local dependency. Its contents never enter cases or requests.
    anchor_document = read(anchors)
    if not isinstance(anchor_document, dict):
        raise ValueError('Invalid anchor inventory')
    from basedbench.comment_selection_feedback import _verify_provenance
    _verify_provenance(anchor_document)
    source_hashes = {str(source / name): sha for name, sha in read(source / 'complete.json')['files'].items()}
    source_hashes[str(source / 'complete.json')] = file_hash(source / 'complete.json')
    source_hashes[str(anchors)] = file_hash(anchors)
    source_hashes.update({anchor_document['source_paths'][name]: sha
                         for name, sha in anchor_document['sources'].items()})
    selection = review_selection(cases, read(source / 'review-cases.json'))
    rows, preview = preflight(cases, remaining)
    root.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.' + root.name + '-', dir=root.parent))
    try:
        (stage / 'images').mkdir()
        image_hashes = {}
        for case in cases:
            old = source / 'images' / case['image_sha256']
            if file_hash(old) != case['image_sha256']:
                raise ValueError('Source image changed')
            target = stage / 'images' / case['image_sha256']
            if not target.exists():
                shutil.copyfile(old, target)
            image_hashes[str(target.relative_to(stage))] = file_hash(target)
        atomic(stage / 'cases.json', cases)
        atomic(stage / 'baseline-packs.json', baselines)
        atomic(stage / 'request-preview.json', preview)
        plan = {'version': VERSION, **LIMITS, 'budget_usd': remaining,
                'cumulative_budget_usd': TOTAL_BUDGET, 'prior_spent_usd': prior_spent,
                'source_root': str(source), 'anchors_path': str(anchors),
                'source_hashes': source_hashes, 'code_hashes': code_hashes(),
                'input_hashes': {name: file_hash(stage / name) for name in
                                 ('cases.json', 'baseline-packs.json', 'request-preview.json')},
                'image_hashes': image_hashes,
                'inventory': {'families': len(cases), 'comments': sum(len(c['comments']) for c in cases)},
                'preflight': rows, 'review_selection': selection,
                'authorization': 'User requested Jev selection follow-up; existing authorized saved comments '
                    'and image observations only to TypeSafe, within the cumulative $1 issue cap. '
                    'Human feedback and anchors stay local.',
                'invalid_response_policy': 'family abstention with known cost settled; no repair or retry'}
        plan['plan_id'] = digest(plan)
        atomic(stage / 'plan.json', plan)
        os.replace(stage, root)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    calls = sum(r['calls'] for r in rows)
    return {'root': str(root), 'inventory': plan['inventory'], 'planned_calls': calls,
            'planned_questions': sum(r['questions'] for r in rows), 'remaining_budget_usd': remaining,
            'prior_spent_usd': prior_spent, 'worst_case_new_usd': calls * RESERVE_USD,
            'worst_case_cumulative_usd': prior_spent + calls * RESERVE_USD}


def load(root: Path):
    root = root.resolve()
    plan = read(root / 'plan.json')
    if (plan['version'] != VERSION or plan['plan_id'] != digest({k: v for k, v in plan.items() if k != 'plan_id'})
            or plan['code_hashes'] != code_hashes()):
        raise ValueError('Frozen plan or code changed')
    if any(plan[key] != value for key, value in LIMITS.items()) or plan['cumulative_budget_usd'] != TOTAL_BUDGET:
        raise ValueError('Budget limits changed')
    old_report = read(Path(plan['source_root']) / 'report.json')['provider_ledger']
    if (old_report['pending_calls'] or old_report['stop_reason']
            or plan['prior_spent_usd'] != old_report['spent_usd']
            or plan['budget_usd'] != TOTAL_BUDGET - old_report['spent_usd']):
        raise ValueError('Prior spending changed')
    for filename, sha in plan['source_hashes'].items():
        if file_hash(Path(filename)) != sha:
            raise ValueError('Frozen source or anchors changed')
    for name, sha in {**plan['input_hashes'], **plan['image_hashes']}.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or file_hash(path) != sha:
            raise ValueError('Frozen input or image changed')
    cases = read(root / 'cases.json')
    baselines = read(root / 'baseline-packs.json')
    return plan, cases, baselines


def evaluate_case(case, baseline, store):
    scores, errors = {}, []
    for body in policy.comment_requests(case) + policy.pair_requests(case):
        result = store.call(body)
        if result['status'] == 'invalid':
            errors.extend(result['errors'])
            scores.clear()
            break
        scores.update(result['scores'])
    lists = policy.build_lists(case, baseline, None if errors else scores)
    return {'case_id': case['case_id'], 'family_id': case['group_id'],
            'status': 'abstained' if errors else 'completed', 'errors': errors,
            'scores': scores, 'lists': lists}


def summarize(plan, cases, outcomes, accounting):
    if len(outcomes) != len(cases) or {o['case_id'] for o in outcomes} != {c['case_id'] for c in cases}:
        raise ValueError('Output coverage mismatch')
    if plan['prior_spent_usd'] + accounting['spent_or_reserved_usd'] > TOTAL_BUDGET + 1e-12:
        raise ValueError('Cumulative budget exceeded')
    statistics = {}
    for method in METHODS:
        available = [o['lists'][method] for o in outcomes if o['lists'][method]['status'] == 'completed']
        statistics[method] = {'available_families': len(available),
            'empty_families': sum(not p['retained_ids'] for p in available),
            'selected_comments': sum(len(p['selected_ids']) for p in available),
            'retained_comments': sum(len(p['retained_ids']) for p in available),
            'initial_words': sum(p['word_count'] for p in available),
            'retained_words': sum(p['total_word_count'] for p in available)}
    return {'status': 'complete', 'inventory': plan['inventory'], 'provider_ledger': accounting,
            'prior_spent_usd': plan['prior_spent_usd'],
            'cumulative_spent_usd': plan['prior_spent_usd'] + accounting['spent_usd'],
            'families_completed': sum(o['status'] == 'completed' for o in outcomes),
            'families_abstained': sum(o['status'] != 'completed' for o in outcomes),
            'list_statistics': statistics,
            'identical_initial_lists': {a + '_vs_' + b: sum(o['lists'][a]['selected_ids'] == o['lists'][b]['selected_ids']
                  for o in outcomes if o['status'] == 'completed')
                  for a, b in [('baseline', 'pointwise'), ('baseline', 'pairwise'), ('pointwise', 'pairwise')]},
            'human_quality': {'status': 'pending', 'review_cases': len(plan['review_selection']),
                              'development_checks_are_exposed': True, 'accuracy_claim': None}}


def make_review(root, plan, cases, outcomes):
    by_group = {c['group_id']: c for c in cases}
    results = {o['family_id']: o for o in outcomes}
    entries, image_hashes = [], {}
    for selected in plan['review_selection']:
        case = by_group[selected['family_id']]
        entries.append({**selected, 'case_id': case['case_id'], 'image_path': case['image_path'],
                        'comments': case['comments'],
                        'packs': {slot: results[case['group_id']]['lists'][method]
                                  for slot, method in selected['methods'].items()}})
        image_hashes[selected['review_id']] = case['image_sha256']
    target = root / 'review-cases.json'
    if target.exists():
        if read(target) != entries:
            raise ValueError('Existing review differs; preserve its identity and feedback')
    else:
        atomic(target, entries)
    manifest = {'plan_id': plan['plan_id'], 'cases_sha256': file_hash(target), 'image_hashes': image_hashes}
    manifest['packet_id'] = digest(manifest)
    manifest_path = root / 'review-manifest.json'
    if manifest_path.exists():
        if read(manifest_path) != manifest:
            raise ValueError('Existing review manifest differs')
    else:
        atomic(manifest_path, manifest)


def run(root: Path, *, client=None, api_key=''):
    root = root.resolve()
    plan, cases, baselines = load(root)
    if (root / 'complete.json').exists():
        return replay(root)
    with (root / 'run.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        store = Store(root, plan, client=client, api_key=api_key)
        try:
            outcomes = []
            for index, case in enumerate(cases):
                outcomes.append(evaluate_case(case, baselines[case['case_id']], store))
                atomic(root / 'outcomes-partial.json', outcomes)
                if (index + 1) % 10 == 0 or index + 1 == len(cases):
                    print(json.dumps({'families_processed': index + 1, 'ledger': store.report()}), flush=True)
            report = summarize(plan, cases, outcomes, store.report())
            atomic(root / 'outcomes.json', outcomes)
            atomic(root / 'report.json', report)
            make_review(root, plan, cases, outcomes)
            files = {str(p.relative_to(root)): file_hash(p) for p in root.rglob('*') if p.is_file()
                     and p.name not in ('complete.json', 'run.lock', 'run.log')
                     and 'review-feedback' not in p.relative_to(root).parts}
            atomic(root / 'complete.json', {'plan_id': plan['plan_id'], 'files': files})
            return report
        except BaseException as exc:
            atomic(root / 'partial.json', {'status': 'partial', 'error_type': type(exc).__name__,
                                          'reason': str(exc), 'ledger': store.report()})
            raise
        finally:
            store.close()


def replay(root: Path):
    root = root.resolve()
    plan, cases, baselines = load(root)
    complete = read(root / 'complete.json')
    if complete['plan_id'] != plan['plan_id']:
        raise ValueError('Completion identity changed')
    for name, sha in complete['files'].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or file_hash(path) != sha:
            raise ValueError('Completed artifact changed: ' + name)
    store = Store(root, plan)
    try:
        outcomes = [evaluate_case(c, baselines[c['case_id']], store) for c in cases]
        if outcomes != read(root / 'outcomes.json'):
            raise ValueError('Cached-response replay differs')
        accounting = store.report()
        if accounting['pending_calls'] or accounting['stop_reason']:
            raise ValueError('Unresolved provider accounting')
        if summarize(plan, cases, outcomes, accounting) != read(root / 'report.json'):
            raise ValueError('Aggregate replay differs')
        return {'status': 'verified_replay', 'families': len(cases), 'frozen_files': len(complete['files']),
                'provider_ledger': accounting,
                'cumulative_spent_usd': plan['prior_spent_usd'] + accounting['spent_usd']}
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'run', 'replay'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--anchors', type=Path)
    parser.add_argument('--env-file', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        if not args.source or not args.anchors:
            parser.error('--source and --anchors required')
        result = prepare(args.source, args.root, args.anchors)
    elif args.command == 'replay':
        result = replay(args.root)
    else:
        from dotenv import dotenv_values
        local = dotenv_values(args.env_file) if args.env_file else {}
        result = run(args.root, api_key=os.getenv('JEV_API_KEY') or os.getenv('TYPESAFE_API_KEY')
                     or local.get('JEV_API_KEY') or local.get('TYPESAFE_API_KEY', ''))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
