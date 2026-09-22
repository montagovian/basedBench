"""Offline inspection of source-first proposals, retaining separate provenance."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import html
import json
from pathlib import Path

from basedbench.pipeline import connection_eval as evaluation
from basedbench.pipeline.curation_corpus import file_hash, write_json


def build(run: Path, output: Path, inspection: Path | None = None, continuation: Path | None = None):
    plan = json.loads((run / 'plan.json').read_text())
    evaluation.verify_files(run, plan['files'])
    evaluation.verify_files(run, json.loads((run / 'results-manifest.json').read_text()))
    cases = json.loads((run / 'cases.json').read_text())
    results = {r['case_id']: r for r in json.loads((run / 'results.json').read_text())}
    if set(results) != {c['case_id'] for c in cases}:
        raise ValueError('Expected all declared case outcomes')
    initial_results = dict(results)
    result_runs = {cid: run for cid in results}
    second_plan = None
    if continuation:
        second_plan = json.loads((continuation / 'plan.json').read_text())
        evaluation.verify_files(continuation, second_plan['files'])
        evaluation.verify_files(continuation, json.loads((continuation / 'results-manifest.json').read_text()))
        if second_plan['prior_files'].get(str((run / 'plan.json').resolve())) != file_hash(run / 'plan.json'):
            raise ValueError('Continuation has a different source run')
        continued = {r['case_id']: r for r in json.loads((continuation / 'results.json').read_text())}
        if set(continued) != {cid for cid, r in results.items() if r['status'] == 'error'}:
            raise ValueError('Continuation must contain exactly the technical-error cases')
        for cid in continued:
            if second_plan['input_hashes'][cid] != plan['input_hashes'][cid]:
                raise ValueError('Continuation changed evidence')
            result_runs[cid] = continuation
        results.update(continued)
    notes = json.loads(inspection.read_text()) if inspection else {'kind': 'assistant_inspection_not_human_gold', 'items': {}}
    if notes['kind'] != 'assistant_inspection_not_human_gold' or not set(notes['items']) <= set(results):
        raise ValueError('Inspection identity mismatch')
    if inspection and notes.get('experiment_id') != plan['experiment_id']:
        raise ValueError('Inspection belongs to another experiment')
    if inspection and notes.get('continuation_experiment_id') != (second_plan or {}).get('experiment_id'):
        raise ValueError('Inspection continuation differs')
    rows, groups = [], defaultdict(Counter)
    for case in cases:
        cid = case['case_id']
        result = results[cid]
        initial = result['stages'].get('check', {})
        baseline = case['baseline']
        old_check = baseline.get('answer_stages', baseline.get('stages', {}))
        old_check = old_check.get('generated_check', {}) if 'decision' in baseline else old_check.get('original_check', {})
        row = {'case_id': cid, 'post_id': case['post_id'], 'group': case['group'],
               'original_human_gold': case.get('gold'), 'original_human_gold_source': case.get('gold_source'),
               'baseline_verdict': old_check.get('verdict', 'not_checked'),
               'first_pass_status': initial_results[cid]['status'],
               'result_run': str(result_runs[cid]),
               'map_status': result['stages']['map'].get('status', 'error'),
               'variant_verdict': initial.get('verdict', 'error' if initial.get('error') else 'not_checked'),
               'final_status': result['status'], 'repaired': result['repaired'],
               'inspection': notes['items'].get(cid)}
        rows.append(row)
        groups[row['group']][row['variant_verdict']] += 1
    # Hypotheses never enter a binary accuracy denominator.
    human = [r for r in rows if r['original_human_gold'] in {'pass', 'fail'}]
    cost = {'initial': json.loads((run / 'report.json').read_text())}
    if continuation:
        cost['continuation'] = json.loads((continuation / 'report.json').read_text())
    cost['combined_estimated_usd'] = sum(r['cost_estimate_usd'] for r in list(cost.values()))
    cost['combined_accounted_usd'] = sum(r['accounted_usd'] for r in cost.values() if isinstance(r, dict))
    summary = {'experiment_id': plan['experiment_id'], 'continuation_experiment_id': (second_plan or {}).get('experiment_id'), 'cases': len(rows),
               'group_verdicts': dict(groups),
               'human_label_comparison': {label: dict(Counter(r['variant_verdict'] for r in human if r['original_human_gold'] == label)) for label in ('pass', 'fail')},
               'inspection_count': len(notes['items']), 'cost': cost,
               'rows': rows, 'independent_validation': False}
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / 'summary.json', summary)
    supported = []
    for case, row in zip(cases, rows, strict=True):
        result = results[case['case_id']]
        note = row['inspection'] or {}
        if result['status'] == 'model_supported' and note.get('semantic_comparison_eligible') is True:
            supported.append({'post_id': case['post_id'], 'case_id': case['case_id'], 'explanation': result['explanation'],
                              'provenance': 'model_supported_and_assistant_inspected_not_human_gold',
                              'experiment_id': (second_plan if result_runs[case['case_id']] == continuation else plan)['experiment_id'],
                              'result_sha256': file_hash(result_runs[case['case_id']] / 'results.json'),
                              'inspection_sha256': file_hash(inspection)})
    write_json(output / 'supported-explanations.json', supported)
    esc = lambda value: html.escape(str(value))
    blocks = []
    for case, row in zip(cases, rows, strict=True):
        cid = case['case_id']
        result = results[cid]
        path = (run / 'assets' / case['input']['image_sha256']).resolve()
        calls = []
        versions = [(run, initial_results[cid])]
        if result_runs[cid] != run:
            versions.append((result_runs[cid], result))
        for directory, version_result in versions:
            for stage in version_result['stages']:
                raw_path = directory / 'calls' / f'{cid}.{stage}.json'
                raw = json.loads(raw_path.read_text())
                calls.append(f'<details><summary>{esc(directory.name)}: {esc(stage)} raw model output</summary><pre>{esc(raw.get("output_text", raw.get("error")))}</pre></details>')
        blocks.append(f'''<article id="{esc(cid)}"><h2>{esc(cid)} · {esc(case['group'])}</h2>
        <p>Baseline {esc(row['baseline_verdict'])}; new check {esc(row['variant_verdict'])}; final {esc(row['final_status'])}</p>
        <div class="pair"><img src="{path.as_uri()}" alt="Source meme {esc(cid)}"><div>
        <h3>Original proposal</h3><p>{esc(case['input']['explanation'])}</p>
        <h3>Final proposal (model approval only)</h3><p>{esc(result['explanation'])}</p>
        <h3>Separate assistant inspection</h3><pre>{esc(json.dumps(row['inspection'],ensure_ascii=False,indent=2))}</pre></div></div>
        <details><summary>Original judgments / development hypothesis</summary><pre>{esc(json.dumps({k:case[k] for k in ['human','gold','gold_source','notes','development_hypothesis'] if k in case},ensure_ascii=False,indent=2))}</pre></details>
        <details><summary>Original supplied comments</summary><pre>{esc(case['input']['comment_evidence'])}</pre></details>
        {''.join(calls)}</article>''')
    page = '''<!doctype html><meta charset="utf-8"><title>Connection comparison inspection</title>
    <style>body{font:16px system-ui;max-width:1300px;margin:30px auto;padding:0 20px;color:#172027;background:#f8f8f5}article{border-top:2px solid #879999;padding:24px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:25px}.pair img{max-width:100%;max-height:1000px;object-fit:contain}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef1ef;padding:14px}details{margin:12px 0}summary{cursor:pointer;font-weight:600}h3{margin-bottom:5px}</style>
    <h1>Source-first explanation comparison</h1><p>Development inspection only. Source hypotheses, historical human judgments, model proposals and assistant inspection remain separate.</p>'''
    (output / 'casebook.html').write_text(page + ''.join(blocks))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inspection', type=Path)
    parser.add_argument('--continuation', type=Path)
    args = parser.parse_args()
    summary = build(**vars(args))
    print(json.dumps({k: summary[k] for k in ('cases', 'human_label_comparison', 'inspection_count')}))
