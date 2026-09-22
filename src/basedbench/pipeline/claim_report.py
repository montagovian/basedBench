"""Read-only paired-check casebook; invalid raw outputs never become valid outcomes."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import html
import json
import os
from pathlib import Path
from urllib.parse import quote

from basedbench.pipeline import claim_eval as evaluation
from basedbench.pipeline.curation_corpus import write_json


def build(run: Path, output: Path, inspection: Path | None = None):
    plan = json.loads((run / 'plan.json').read_text())
    evaluation.prior.verify_files(run, plan['files'])
    evaluation.prior.verify_files(run, json.loads((run / 'results-manifest.json').read_text()))
    cases = json.loads((run / 'cases.json').read_text())
    results = {r['case_id']: r for r in json.loads((run / 'results.json').read_text())}
    if set(results) != {c['case_id'] for c in cases}:
        raise ValueError('Expected the complete declared packet')
    notes = json.loads(inspection.read_text()) if inspection else {'kind': 'assistant_inspection_not_human_gold', 'items': {}}
    if notes['kind'] != 'assistant_inspection_not_human_gold' or not set(notes['items']) <= set(results):
        raise ValueError('Inspection kind or case identities differ')
    if inspection and notes.get('experiment_id') != plan['experiment_id']:
        raise ValueError('Inspection belongs to another run')
    rows, blocks = [], []
    groups = defaultdict(lambda: defaultdict(Counter))
    esc = lambda value: html.escape(str(value))
    for case in cases:
        cid = case['case_id']
        result = results[cid]
        row = {'case_id': cid, 'group': case['group'], 'human_gold': case.get('gold'),
            'human_gold_source': case.get('gold_source'), 'status': result['status'], 'repaired': result['repaired'],
            'baseline': result['stages']['baseline'].get('verdict', 'error'),
            'variant': result['stages']['check'].get('verdict', 'error'),
            'errors': {s: v['error'] for s, v in result['stages'].items() if v.get('error')},
            'inspection': notes['items'].get(cid)}
        rows.append(row)
        for stage in ('baseline', 'variant'):
            groups[case['group']][stage][row[stage]] += 1
        raw_sections = []
        for stage in result['stages']:
            call = json.loads((run / 'calls' / f'{cid}.{stage}.json').read_text())
            raw_sections.append(f'<details><summary>{esc(stage)}: raw output and validation</summary>'
                f'<pre>{esc(json.dumps(result["stages"][stage],ensure_ascii=False,indent=2))}</pre>'
                f'<pre>{esc(call.get("output_text", call.get("error")))}</pre></details>')
        image_url = quote(os.path.relpath((run / 'assets' / case['input']['image_sha256']).resolve(), output.resolve()))
        labels = {k: case[k] for k in ('gold', 'gold_source', 'human', 'notes', 'development_hypothesis') if k in case}
        blocks.append(f'''<article id="{esc(cid)}"><h2>{esc(cid)} · {esc(case['group'])}</h2>
        <p>Baseline: {esc(row['baseline'])} · Direct check: {esc(row['variant'])} · Final: {esc(row['status'])}</p>
        <div class="pair"><img src="{image_url}" alt="Source meme {esc(cid)}"><div>
        <h3>Original answer</h3><p>{esc(case['input']['explanation'])}</p>
        <h3>Final answer (model approval only)</h3><p>{esc(result['explanation'])}</p>
        <h3>Separate assistant inspection</h3><pre>{esc(json.dumps(row['inspection'],ensure_ascii=False,indent=2))}</pre>
        </div></div><details><summary>Original labels and hypothesis</summary><pre>{esc(json.dumps(labels,ensure_ascii=False,indent=2))}</pre></details>
        <details><summary>Original comments</summary><pre>{esc(case['input']['comment_evidence'])}</pre></details>
        {''.join(raw_sections)}</article>''')
    summary = {'experiment_id': plan['experiment_id'], 'cases': len(cases), 'rows': rows,
        'groups': {g: dict(stages) for g, stages in groups.items()}, 'inspection_count': len(notes['items']),
        'run_report': json.loads((run / 'report.json').read_text()), 'independent_validation': False}
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / 'summary.json', summary)
    page = '''<!doctype html><meta charset="utf-8"><title>Direct claim comparison</title>
    <style>body{font:16px system-ui;max-width:1300px;margin:30px auto;padding:0 20px;color:#172027;background:#f8f8f5}article{border-top:2px solid #879999;padding:24px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:25px}.pair img{max-width:100%;max-height:1000px;object-fit:contain}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef1ef;padding:14px}details{margin:12px 0}summary{cursor:pointer;font-weight:600}@media(max-width:700px){.pair{grid-template-columns:1fr}}</style>
    <h1>Direct claim comparison</h1><p>Exposed development cases. Human judgments and assistant hypotheses remain separate. Raw failed-validation output is diagnostic evidence, not a valid verdict or approved answer.</p>'''
    (output / 'casebook.html').write_text(page + ''.join(blocks))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inspection', type=Path)
    result = build(**vars(parser.parse_args()))
    print(json.dumps({k: result[k] for k in ('cases', 'inspection_count')}))
