"""Versioned duplicate integration using strictly offline frozen-call replay.

Expanded crop retrieval retains its measured packet scope. Both semantic views
and all old evidence survive. No provider client, new human label or keeper choice.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import copy
import fcntl
import json
from pathlib import Path

from basedbench.pipeline import admission_pilot as pilot, duplicate_comparison as comparison
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json

VERSION = 'admission-v2-duplicate-replay'
DUPLICATE_VERSION = 'duplicate-evidence-union-v2'


def code_hashes():
    return pilot.code_hashes() | comparison.code_hashes() | {'admission_v2': file_hash(Path(__file__))}


def merge_edges(baseline_edges, additions, records):
    """New retrieval can add evidence, never upgrade candidate adjudication."""
    by_id = {r['post_id']: r for r in records}
    edges = {tuple(sorted((e['left'], e['right']))): copy.deepcopy(e) for e in baseline_edges}
    for item in additions:
        key = tuple(sorted((item['left'], item['right'])))
        if key[0] == key[1] or not set(key) <= set(by_id):
            raise ValueError('Retrieval edge has invalid identities')
        if item['left'] != key[0]:
            raise ValueError('Additional retrieval coordinates must use canonical pair order')
        if key not in edges:
            edges[key] = {'left': key[0], 'right': key[1], 'status': 'candidate', 'evidence': [],
                'release_members': [p for p in key if by_id[p]['in_release']],
                'scope': 'fresh' if any(by_id[p]['pool'] == 'fresh' for p in key) else 'diagnostic'}
        evidence = copy.deepcopy(item['evidence'])
        if evidence['method'] in {'exact_bytes', 'exact_pixels', 'previously_reviewed_family'}:
            raise ValueError('Additional retrieval cannot invent identity or adjudication')
        if evidence not in edges[key]['evidence']:
            edges[key]['evidence'].append(evidence)
    return [edges[k] for k in sorted(edges)]


def comparison_additions(directory, report):
    import numpy as np
    additions = []
    retrieved = {tuple(p) for p in report['image_hit_pairs']['broader_image']}
    for edge in report['image_edges']:
        key = (edge['left'], edge['right'])
        if key not in retrieved:
            continue
        for name in ('baseline_image', 'crop'):
            if edge.get(name):
                evidence = {**edge[name], 'retrieval_scope': 'fixed_56_post_packet',
                            'comparison_experiment_id': report['experiment_id']}
                additions.append({'left': key[0], 'right': key[1], 'evidence': evidence})
    pool = json.loads((directory / 'text-pool.json').read_text())
    index = {r['post_id']: i for i, r in enumerate(pool)}
    for view, filename in (('comments_or_stored_answers', 'baseline-vectors.npy'), ('supported_answers', 'revised-vectors.npy')):
        vectors = np.load(directory / filename, allow_pickle=False)
        if vectors.shape[0] != len(pool):
            raise ValueError('Semantic vector identities differ')
        for a, b in report['text']['hit_pairs'][view]:
            score = float(vectors[index[a]] @ vectors[index[b]])
            if score + 1e-6 < comparison.PARAMETERS['minilm_min']:
                raise ValueError('Saved semantic edge violates the frozen threshold')
            additions.append({'left': a, 'right': b, 'evidence': {
                'method': 'minilm_' + view, 'score': round(score, 6),
                'comparison_experiment_id': report['experiment_id'],
                'retrieval_scope': '52_packet_queries_against_2634_records',
                'explanation_provenance': 'development_model_and_assistant_inspection_not_human_gold'}})
    return additions


def prepare(source: Path, duplicates: Path, audit: Path, output: Path):
    if output.exists():
        raise FileExistsError('Use a new admission version directory')
    source_plan = pilot.load_plan(source)
    pilot.verify_manifest(source, json.loads((source / 'results-manifest.json').read_text()))
    source_report = json.loads((source / 'report.json').read_text())
    if not source_report['complete'] or list((source / 'calls').glob('*.pending')):
        raise ValueError('Prior admission run must be complete')
    audit_plan = pilot.duplicate_audit.verify(audit)
    pilot.verify_manifest(audit, json.loads((audit / 'results-manifest.json').read_text()))
    comp_plan = json.loads((duplicates / 'plan.json').read_text())
    if comp_plan['version'] != comparison.VERSION or comp_plan['code_hashes'] != comparison.code_hashes() or comp_plan['parameters'] != comparison.PARAMETERS:
        raise ValueError('Unexpected comparison configuration')
    if digest({k: v for k, v in comp_plan.items() if k != 'experiment_id'}) != comp_plan['experiment_id']:
        raise ValueError('Comparison plan identity changed')
    pilot.verify_manifest(duplicates, comp_plan['files'])
    pilot.verify_manifest(duplicates, json.loads((duplicates / 'results-manifest.json').read_text()))
    if source_plan['scope'].get('duplicate_audit_id') != audit_plan['audit_id'] or comp_plan['baseline_audit_id'] != audit_plan['audit_id']:
        raise ValueError('Admission and comparison must share the same baseline audit')
    original = json.loads((source / 'cases.json').read_text())
    records = json.loads((audit / 'inputs.json').read_text())
    by_id = {r['post_id']: r for r in records}
    baseline = json.loads((audit / 'report.json').read_text())
    comp = json.loads((duplicates / 'report.json').read_text())
    if comp['experiment_id'] != comp_plan['experiment_id'] or baseline['audit_id'] != audit_plan['audit_id']:
        raise ValueError('Retrieval report identity mismatch')
    if json.loads((duplicates / 'baseline-edges.json').read_text()) != baseline['edges']:
        raise ValueError('Comparison baseline edges differ from the admission audit')
    edges = merge_edges(baseline['edges'], comparison_additions(duplicates, comp), records)
    packet = {r['post_id']: r for r in json.loads((duplicates / 'rows.json').read_text())}
    text_ids = {r['post_id'] for r in json.loads((duplicates / 'text-pool.json').read_text())}
    fresh_ids = {c['post_id'] for c in original}
    cases = []
    for case in original:
        case = copy.deepcopy(case)
        pid = case['post_id']
        if by_id[pid]['image'].get('sha256') != case['input']['image_sha256']:
            raise ValueError('Admission and duplicate image evidence differ')
        if pid in packet and packet[pid]['image'].get('sha256') != by_id[pid]['image'].get('sha256'):
            raise ValueError('Expanded retrieval used a different image')
        matches = [{**e, 'fresh_pair': e['left'] in fresh_ids and e['right'] in fresh_ids}
                   for e in edges if pid in (e['left'], e['right'])]
        case['prior_duplicate_route'] = case['duplicate']
        case['duplicate'] = pilot.duplicate_route(matches)
        case['duplicate_coverage'] = {'baseline_full_audit': True,
            'baseline_image_status': by_id[pid]['image']['status'],
            'expanded_image_packet_member': pid in packet,
            'expanded_image_assessed': pid in packet and packet[pid]['image']['status'] == 'ok',
            'semantic_comparison_query': pid in packet and pid in text_ids,
            'new_full_corpus_crop_audit': False}
        case['provenance'] = {**case.get('provenance', {}), 'admission_version': VERSION,
            'source_admission_experiment_id': source_plan['experiment_id'],
            'duplicate_component_version': DUPLICATE_VERSION,
            'comparison_experiment_id': comp_plan['experiment_id']}
        cases.append(case)
    output.mkdir(parents=True)
    write_json(output / 'cases.json', cases)
    write_json(output / 'duplicate-edges.json', edges)
    # Include every source's input/result manifest as well as the original plan.
    source_files = {}
    for directory, plan, names in ((source, source_plan, ['plan.json', 'report.json', 'results-manifest.json']),
        (audit, audit_plan, ['plan.json', 'report.json', 'results-manifest.json']),
        (duplicates, comp_plan, ['plan.json', 'report.json', 'results-manifest.json'])):
        files = set(plan['files']) | set(json.loads((directory / 'results-manifest.json').read_text())) | set(names)
        source_files.update({str((directory / name).resolve()): file_hash(directory / name) for name in files})
    plan = {'version': VERSION, 'component_versions': {**source_plan['component_versions'], 'duplicates': DUPLICATE_VERSION},
        'source_directory': str(source.resolve()), 'source_experiment_id': source_plan['experiment_id'],
        'source_files': source_files, 'code_hashes': code_hashes(), 'cases': len(cases),
        'paid_model_calls': 0, 'model_cost_usd': 0, 'network_access': False,
        'comparison_experiment_id': comp_plan['experiment_id'],
        'retrieval_scope': {'expanded_image_packet': comp['packet_rows'], 'semantic_queries': comp['text']['queries'],
                            'semantic_pool': comp['text']['full_pool'], 'new_full_corpus_crop_audit': False},
        'files': {p.name: file_hash(p) for p in output.iterdir() if p.is_file()},
        'limitations': ['Counterfactual duplicate integration using unchanged historical model responses.',
            'Prior answer-check weaknesses remain; no new quality or human validation.',
            'Expanded image matching has packet scope, not full-corpus recall.',
            'Crop and semantic evidence remain candidates pending explicit adjudication.',
            'No old outcome, human judgment, keeper, split or release membership is changed.']}
    plan['experiment_id'] = digest(plan)
    write_json(output / 'plan.json', plan)
    return plan


async def replay_case(case, source, source_plan, ledger):
    async def invoke(stage, **kwargs):
        name = case['post_id'] + '.' + stage + '.json'
        path, request_path = source / 'calls' / name, source / 'requests' / name
        if not path.exists() or not request_path.exists():
            message = 'No frozen response for this stage; offline replay cannot call a provider'
            return pilot.error('missing_historical_call', message) if stage in {'content', 'suitability'} else {'error': message}
        request = pilot.make_request(case, stage, source, **kwargs)
        call = json.loads(path.read_text())
        if json.loads(request_path.read_text()) != request or call.get('request_content_sha256') != digest(request):
            raise ValueError('Inherited request identity mismatch')
        if (call['experiment_id'] != source_plan['experiment_id'] or call['post_id'] != case['post_id']
            or call['arm'] != stage or call['input_sha256'] != case['input_sha256']
            or digest(case['input']) != case['input_sha256']):
            raise ValueError('Inherited response/input identity mismatch')
        ledger.append({'post_id': case['post_id'], 'stage': stage, 'source_call_sha256': file_hash(path),
            'request_sha256': digest(request), 'source_experiment_id': source_plan['experiment_id']})
        return pilot.parse(case, stage, call)
    result = await pilot.evaluate(case, invoke)
    return {**result, 'admission_version': VERSION, 'evaluation_mode': 'frozen_response_replay',
            'duplicate_coverage': case.get('duplicate_coverage', {}), 'new_model_calls': 0}


async def run(output: Path):
    plan = json.loads((output / 'plan.json').read_text())
    if plan['version'] != VERSION or plan['code_hashes'] != code_hashes() or digest({k: v for k, v in plan.items() if k != 'experiment_id'}) != plan['experiment_id']:
        raise ValueError('Frozen integration configuration changed')
    pilot.verify_manifest(output, plan['files'])
    for path, sha in plan['source_files'].items():
        if file_hash(Path(path)) != sha:
            raise ValueError('Frozen source changed: ' + path)
    source = Path(plan['source_directory'])
    source_plan = pilot.load_plan(source)
    old_report = json.loads((source / 'report.json').read_text())
    old = {r['post_id']: r for r in old_report['outcomes']}
    with (output / 'run.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (output / 'results-manifest.json').exists():
            pilot.verify_manifest(output, json.loads((output / 'results-manifest.json').read_text()))
        ledger, outcomes, changes = [], [], []
        cases = json.loads((output / 'cases.json').read_text())
        for case in cases:
            value = await replay_case(case, source, source_plan, ledger)
            outcomes.append(value)
            previous = old[case['post_id']]
            if previous['decision'] != value['decision'] or previous['reason_codes'] != value['reason_codes']:
                changes.append({'post_id': case['post_id'], 'before': previous['decision'], 'after': value['decision'],
                    'old_reasons': previous['reason_codes'], 'new_reasons': value['reason_codes']})
        report = {'experiment_id': plan['experiment_id'], 'version': VERSION, 'cases': len(cases),
            'component_versions': plan['component_versions'], 'outcomes': outcomes,
            'counts': dict(Counter(r['decision'] for r in outcomes)), 'old_counts': old_report['counts'],
            'changes': changes, 'reused_call_count': len(ledger), 'paid_model_calls': 0, 'model_cost_usd': 0,
            'historical_source_cost': old_report['cost'], 'retrieval_scope': plan['retrieval_scope'],
            'coverage': {k: sum(c['duplicate_coverage'][k] for c in cases) for k in
                         ('expanded_image_packet_member', 'expanded_image_assessed', 'semantic_comparison_query')},
            'human_validation': False, 'limitations': plan['limitations']}
        write_json(output / 'report.json', report)
        write_json(output / 'reused-calls.json', ledger)
        write_json(output / 'results-manifest.json', {name: file_hash(output / name) for name in ('report.json', 'reused-calls.json')})
        return {k: v for k, v in report.items() if k != 'outcomes'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--source', type=Path, default=Path('data/backfill/admission-june20-26-v1'))
    prep.add_argument('--duplicates', type=Path, default=Path('data/backfill/duplicate-comparison-v1'))
    prep.add_argument('--audit', type=Path, default=Path('data/backfill/duplicate-audit-v1'))
    prep.add_argument('--output', type=Path, required=True)
    execute = sub.add_parser('run')
    execute.add_argument('output', type=Path)
    args = vars(parser.parse_args())
    command = args.pop('command')
    result = prepare(**args) if command == 'prepare' else asyncio.run(run(**args))
    print(json.dumps({k: v for k, v in result.items() if k not in {'files', 'source_files', 'code_hashes'}}))


if __name__ == '__main__':
    main()
