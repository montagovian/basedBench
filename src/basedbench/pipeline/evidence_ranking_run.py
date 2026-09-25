"""Freeze and run one Jev evidence-ranking comparison; never infer human ratings."""
from __future__ import annotations

import argparse
from collections import defaultdict
import fcntl
from itertools import permutations
import json
import os
from pathlib import Path
import shutil
import tempfile

from basedbench.pipeline.curation_corpus import canonical_json, digest, file_hash
from basedbench.pipeline import evidence_ranking_policy as policy
from basedbench.pipeline.evidence_ranking_io import Store, RESERVE_USD

VERSION = 'evidence-ranking-v1'
LIMITS = {'budget_usd': 1., 'max_calls': 400, 'max_questions': 40000}
DIAGNOSTICS = ('198kcl9', '1mksov2', '1udvihp', '1ucsgt3')
METHODS = ('order', 'rank', 'collate')


def read(path):
    return json.loads(Path(path).read_text())


def atomic(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w') as stream:
        stream.write(canonical_json(value) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def code_hashes():
    here = Path(__file__).resolve().parent
    repo = here.parents[2]
    files = [*sorted(here.glob('evidence_ranking_*.py')),
             here / 'jev_decomposition_questions.py', here / 'curation_corpus.py',
             repo / 'pyproject.toml', repo / 'uv.lock']
    return {str(p.relative_to(repo)): file_hash(p) for p in files}


def verify_source(root: Path):
    hashes = {}
    for folder, identity in [('dataset', 'dataset_id'), ('analysis', 'analysis_id')]:
        path = root / folder / 'manifest.json'
        manifest = read(path)
        if manifest[identity] != digest({k: v for k, v in manifest.items() if k != identity}):
            raise ValueError('Source manifest identity changed')
        hashes[str(path)] = file_hash(path)
        for name, sha in manifest['files'].items():
            source = (path.parent / name).resolve()
            if not source.is_relative_to(path.parent.resolve()) or file_hash(source) != sha:
                raise ValueError('Source artifact changed: ' + name)
    source = root / 'analysis/cases.json'
    hashes[str(source)] = file_hash(source)
    return hashes


def eligible(row):
    return (row['gold'] in ('ready', 'repair') and not row.get('image_error')
            and row['arms']['broad_observation']['state'] == 'completed')


def evidence_identity(row):
    return digest([row['input']['image_sha256'], row['comments']])


def freeze_cases(rows: list[dict], root: Path) -> tuple[list[dict], dict]:
    groups = defaultdict(list)
    for row in rows:
        if eligible(row):
            groups[row['group_id']].append(row)
    cases = []
    variants = []
    unmatched_ready = []
    for group_id, members in sorted(groups.items()):
        chosen = min(members, key=lambda row: row['case_id'])
        identity = evidence_identity(chosen)
        matched = sorted((r for r in members if r['gold'] == 'ready' and evidence_identity(r) == identity),
                         key=lambda r: r['case_id'])
        unmatched_ready.extend({'group_id': group_id, 'case_id': r['case_id'],
                                'selected_case_id': chosen['case_id']}
                               for r in members if r['gold'] == 'ready' and evidence_identity(r) != identity)
        contexts = {evidence_identity(r) for r in members}
        if len(contexts) > 1:
            variants.append({'group_id': group_id, 'selected_case_id': chosen['case_id'],
                             'context_count': len(contexts), 'source_case_ids': [r['case_id'] for r in members]})
        obs = chosen['observation']
        cases.append({'case_id': chosen['case_id'], 'group_id': group_id,
            'post_id': chosen['post_id'], 'source_case_ids': sorted(r['case_id'] for r in members),
            'image_path': str(root / 'images' / chosen['input']['image_sha256']),
            'image_sha256': chosen['input']['image_sha256'],
            'comments': [{'id': c['id'], 'text': c['text']} for c in chosen['comments']],
            'observation': {k: obs[k] for k in ('visible_text', 'visible_scene', 'uncertainties')},
            'reference_explanation': matched[0]['input']['explanation'] if matched else None,
            'reference_case_ids': [r['case_id'] for r in matched]})
    return cases, {'source_versions': len(rows), 'eligible_versions': sum(eligible(r) for r in rows),
                   'families': len(cases), 'comments': sum(len(c['comments']) for c in cases),
                   'matching_ready_references': sum(c['reference_explanation'] is not None for c in cases),
                   'unmatched_ready_reference_versions': len(unmatched_ready),
                   'unmatched_ready_references': unmatched_ready,
                   'context_variants': variants,
                   'excluded_versions': [{'case_id': r['case_id'], 'gold': r['gold'],
                         'reason': 'unknown_label' if r['gold'] not in ('ready', 'repair') else 'image_incomplete'}
                        for r in rows if not eligible(r)]}


def review_selection(cases: list[dict]) -> list[dict]:
    diagnostics = []
    for post in DIAGNOSTICS:
        found = [c for c in cases if c['post_id'] == post or any(cid.startswith(post + '-') for cid in c['source_case_ids'])]
        if len(found) != 1:
            raise ValueError('Diagnostic family missing or ambiguous: ' + post)
        diagnostics.append(found[0]['group_id'])
    other = sorted((c['group_id'] for c in cases if c['group_id'] not in diagnostics),
                   key=lambda g: digest([VERSION, 'review-sample', g]))[:12]
    if len(other) != 12 or len(set(diagnostics)) != 4:
        raise ValueError('Insufficient distinct review families')
    chosen = sorted(diagnostics + other, key=lambda g: digest([VERSION, 'review-order', g]))
    rotations = sorted(permutations(METHODS), key=lambda p: digest([VERSION, 'slot-rotation', p]))
    return [{'review_id': f'R{i + 1:02}', 'family_id': group,
             'sample_kind': 'diagnostic' if group in diagnostics else 'sampled',
             'methods': dict(zip(('A', 'B', 'C'), rotations[i % 6], strict=True))}
            for i, group in enumerate(chosen)]


def prepare(source: Path, root: Path):
    source, root = source.resolve(), root.resolve()
    if root.exists():
        raise FileExistsError('Use a new output directory; preserve previous runs')
    if root.is_relative_to(source):
        raise ValueError('New run cannot be inside the source run')
    hashes = verify_source(source)
    rows = read(source / 'analysis/cases.json')
    cases, inventory = freeze_cases(rows, root)
    if (len(rows), inventory['eligible_versions'], len(cases), inventory['comments']) != (99, 94, 81, 760):
        raise ValueError('Frozen source composition changed')
    selection = review_selection(cases)
    preflight = []
    representative_body = None
    for case in cases:
        bodies = policy.comment_requests(case) + policy.pair_requests(case)
        representative_body = representative_body or bodies[0]
        preflight.append({'case_id': case['case_id'], 'calls': len(bodies),
            'questions': sum(len(body['questions']) for body in bodies),
            'largest_request_bytes': max(len(canonical_json(body).encode()) for body in bodies),
            'source_words': sum(len(c['text'].split()) for c in case['comments']),
            'budget_words': policy.word_budget(case)})
    call_count = sum(row['calls'] for row in preflight)
    question_count = sum(row['questions'] for row in preflight)
    if call_count > LIMITS['max_calls'] or question_count > LIMITS['max_questions']:
        raise ValueError('Preflight exceeds finite request/question limits')
    if call_count * RESERVE_USD > LIMITS['budget_usd'] + 1e-12:
        raise ValueError('Preflight exceeds worst-case provider budget')
    root.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.' + root.name + '-', dir=root.parent))
    try:
        (stage / 'images').mkdir()
        by_id = {r['case_id']: r for r in rows}
        image_hashes = {}
        for case in cases:
            original = Path(by_id[case['case_id']]['image_path'])
            if file_hash(original) != case['image_sha256']:
                raise ValueError('Source image changed')
            target = stage / 'images' / case['image_sha256']
            if not target.exists():
                shutil.copyfile(original, target)
            image_hashes['images/' + case['image_sha256']] = file_hash(target)
        atomic(stage / 'cases.json', cases)
        atomic(stage / 'request-preview.json', representative_body)
        plan = {'version': VERSION, **LIMITS, 'source_root': str(source), 'source_hashes': hashes,
            'code_hashes': code_hashes(), 'cases_sha256': file_hash(stage / 'cases.json'),
            'image_hashes': image_hashes, 'preview_sha256': file_hash(stage / 'request-preview.json'),
            'inventory': inventory, 'preflight': preflight, 'review_selection': selection,
            'authorization': 'User approved the three evidence-pack arms, 16-case blinded review, '
                'and proposed $1 cap; Jev receives comments and saved observations only.',
            'invalid_response_policy': 'family abstention with known cost settled; no score correction or retry'}
        plan['plan_id'] = digest(plan)
        atomic(stage / 'plan.json', plan)
        os.replace(stage, root)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return {'root': str(root), 'inventory': inventory, 'planned_calls': call_count,
            'planned_questions': question_count, 'budget_usd': LIMITS['budget_usd'],
            'worst_case_usd': call_count * RESERVE_USD,
            'largest_request_bytes': max(row['largest_request_bytes'] for row in preflight)}


def load(root: Path):
    root = root.resolve()
    plan = read(root / 'plan.json')
    if (plan['version'] != VERSION or plan['plan_id'] != digest({k: v for k, v in plan.items() if k != 'plan_id'})
        or plan['code_hashes'] != code_hashes() or plan['cases_sha256'] != file_hash(root / 'cases.json')
        or plan['preview_sha256'] != file_hash(root / 'request-preview.json')):
        raise ValueError('Frozen plan, code, cases or preview changed')
    if any(plan[k] != value for k, value in LIMITS.items()):
        raise ValueError('Budget limits changed')
    for filename, sha in {**plan['source_hashes'], **{str(root / k): v for k, v in plan['image_hashes'].items()}}.items():
        if file_hash(Path(filename)) != sha:
            raise ValueError('Frozen source or image changed')
    return plan, read(root / 'cases.json')


def evaluate_case(case: dict, store) -> dict:
    scores, errors = {}, []
    for body in policy.comment_requests(case) + policy.pair_requests(case):
        result = store.call(body)
        if result['status'] == 'invalid':
            errors.extend(result['errors'])
            scores.clear()
            break
        scores.update(result['scores'])
    packs = policy.build_packs(case, None if errors else scores)
    return {'case_id': case['case_id'], 'family_id': case['group_id'],
            'status': 'abstained' if errors else 'completed', 'errors': errors,
            'scores': scores, 'packs': packs}


def _signature(pack):
    return [(e['comment_id'], e['start'], e['end']) for e in pack['excerpts']]


def summarize(plan: dict, cases: list, outcomes: list, accounting: dict):
    if {r['case_id'] for r in outcomes} != {c['case_id'] for c in cases} or len(outcomes) != len(cases):
        raise ValueError('Output family coverage mismatch')
    successful = [o for o in outcomes if o['status'] == 'completed']
    by_method = {}
    source_words = sum(len(comment['text'].split()) for case in cases for comment in case['comments'])
    for method in METHODS:
        available = [o['packs'][method] for o in outcomes if o['packs'][method]['status'] == 'completed']
        by_method[method] = {'available_families': len(available),
            'excerpt_words': sum(p['word_count'] for p in available),
            'budget_words': sum(p['budget_words'] for p in available),
            'excerpts': sum(len(p['excerpts']) for p in available)}
    return {'status': 'complete', 'inventory': plan['inventory'], 'provider_ledger': accounting,
        'families_completed': len(successful), 'families_abstained': len(outcomes) - len(successful),
        'abstentions': [{'case_id': o['case_id'], 'errors': o['errors']} for o in outcomes if o['status'] != 'completed'],
        'source_words': source_words, 'pack_statistics': by_method,
        'identical_packs': {'all_three': sum(len({digest(_signature(o['packs'][m])) for m in METHODS}) == 1 for o in successful),
            **{a + '_vs_' + b: sum(_signature(o['packs'][a]) == _signature(o['packs'][b]) for o in successful)
               for a, b in [('order', 'rank'), ('order', 'collate'), ('rank', 'collate')]}},
        'human_quality': {'status': 'pending', 'review_cases': len(plan['review_selection']),
                          'sampled': 12, 'diagnostic': 4, 'accuracy_claim': None}}


def make_review(root: Path, plan: dict, cases: list, outcomes: list):
    case_by_group = {c['group_id']: c for c in cases}
    result_by_group = {r['family_id']: r for r in outcomes}
    entries = []
    image_hashes = {}
    for selection in plan['review_selection']:
        case = case_by_group[selection['family_id']]
        result = result_by_group[selection['family_id']]
        entries.append({**selection, 'case_id': case['case_id'], 'image_path': case['image_path'],
            'comments': case['comments'], 'reference_explanation': case['reference_explanation'],
            'packs': {slot: result['packs'][method] for slot, method in selection['methods'].items()}})
        image_hashes[selection['review_id']] = case['image_sha256']
    target = root / 'review-cases.json'
    if target.exists():
        raise FileExistsError('Review already exists; preserve its feedback identity')
    atomic(target, entries)
    manifest = {'plan_id': plan['plan_id'], 'cases_sha256': file_hash(target), 'image_hashes': image_hashes}
    manifest['packet_id'] = digest(manifest)
    atomic(root / 'review-manifest.json', manifest)


def run(root: Path, *, client=None, api_key=''):
    root = root.resolve()
    plan, cases = load(root)
    if (root / 'complete.json').exists():
        return replay(root)
    with (root / 'run.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        store = Store(root, plan, client=client, api_key=api_key)
        try:
            outcomes = []
            for index, case in enumerate(cases):
                outcomes.append(evaluate_case(case, store))
                atomic(root / 'outcomes-partial.json', outcomes)
                if (index + 1) % 10 == 0 or index + 1 == len(cases):
                    print(json.dumps({'families_processed': index + 1, 'ledger': store.report()}), flush=True)
            report = summarize(plan, cases, outcomes, store.report())
            atomic(root / 'outcomes.json', outcomes)
            atomic(root / 'report.json', report)
            make_review(root, plan, cases, outcomes)
            # Include provider ledger/artifacts as well as derived output. Never
            # include the later mutable human feedback journal in this manifest.
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
    plan, cases = load(root)
    complete = read(root / 'complete.json')
    if complete['plan_id'] != plan['plan_id']:
        raise ValueError('Completion belongs to a different plan')
    for relative, sha in complete['files'].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or file_hash(path) != sha:
            raise ValueError('Completed artifact changed: ' + relative)
    store = Store(root, plan)
    try:
        outcomes = [evaluate_case(case, store) for case in cases]
        if outcomes != read(root / 'outcomes.json'):
            raise ValueError('Evidence packs differ from cached-response replay')
        accounting = store.report()
        if accounting['pending_calls'] or accounting['stop_reason']:
            raise ValueError('Unresolved provider accounting')
        if summarize(plan, cases, outcomes, accounting) != read(root / 'report.json'):
            raise ValueError('Aggregate replay mismatch')
        return {'status': 'verified_replay', 'families': len(cases), 'provider_ledger': accounting}
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'run', 'replay'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--env-file', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        if not args.source:
            parser.error('--source required')
        result = prepare(args.source, args.root)
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
