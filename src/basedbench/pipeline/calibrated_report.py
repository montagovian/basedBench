"""Read-only comparison report with item-level source and human provenance."""
from collections import Counter, defaultdict
import html
import json
import os
from pathlib import Path

from basedbench.pipeline.connection_eval import verify_files
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json


def build(run: Path, output: Path):
    if output.exists():
        raise FileExistsError('Use a new report directory')
    plan = json.loads((run/'plan.json').read_text())
    verify_files(run, plan['files'])
    verify_files(run, json.loads((run/'results-manifest.json').read_text()))
    cases = json.loads((run/'cases.json').read_text())
    results = json.loads((run/'results.json').read_text())
    report = json.loads((run/'report.json').read_text())
    lookup = {(r['case_id'],r['arm'],r['repeat']):r['result'] for r in results}
    rows, blocks = [], []
    esc = lambda v: html.escape(str(v))
    for c in cases:
        findings = {a:lookup.get((c['case_id'],a,0),{'error':plan['input_errors'].get(c['case_id'],'not_attempted')}) for a in plan['arms']}
        verdicts = {a:v.get('verdict','error') for a,v in findings.items()}
        quality = c.get('original_quality')
        row = {'case_id':c['case_id'],'stratum':c['stratum'],'human_original_quality':quality,
               'known_family':c['group_id'],'family_weight':c.get('family_weight',1),
               'findings':findings,'gate_disagreement':len(set(verdicts.values()))>1,
               'repeats':{a:lookup[c['case_id'],a,1] for a in plan['arms'] if (c['case_id'],a,1) in lookup}}
        rows.append(row)
        ordered = sorted(plan['arms'], key=lambda a:digest(['blind-casebook-v1',c['case_id'],a]))
        cards=[]
        for i,a in enumerate(ordered):
            v=findings[a]
            cards.append(f'<section><h3>Condition {"ABC"[i]}</h3><p>Combined gate: <b>{esc(v.get("verdict","error"))}</b></p><p>Separate answer adequacy: {esc(v.get("answer_quality","not separately recorded"))}</p><p>Source support: {esc(v.get("evidence_status","combined with answer judgment"))}</p><p>{esc(v.get("reason",v.get("error","")))}</p><p>{esc(v.get("missing_or_wrong_connection") or "")}</p></section>')
        image=os.path.relpath(run/'assets'/c['input']['image_sha256'],output)
        blocks.append(f'<article id="{esc(c["case_id"])}"><h2>{esc(c["case_id"])}</h2><p>Human original judgment: {esc(quality or "not collected")}</p><div class="pair"><img src="{esc(image)}" alt="Source meme"><div><h3>Original explanation</h3><p>{esc(c["input"]["explanation"])}</p>{"".join(cards)}</div></div><details><summary>Source comments</summary><pre>{esc(c["input"]["comment_evidence"])}</pre></details><details><summary>Reveal condition identities and full model findings</summary><pre>{esc(json.dumps({"order":ordered,**row},ensure_ascii=False,indent=2))}</pre></details></article>')
    totals=defaultdict(Counter)
    for r in rows:
        for a,v in r['findings'].items():
            totals[a][v.get('verdict','error')]+=1
    summary={'experiment_id':plan['experiment_id'],'run_report':report,'gate_totals':{a:dict(c) for a,c in totals.items()},
             'disagreement_ids':[r['case_id'] for r in rows if r['gate_disagreement']], 'rows':rows,
             'no_new_calls':True,'human_gold_only_from_frozen_feedback':plan['human_labels_available']}
    output.mkdir(parents=True)
    write_json(output/'summary.json',summary)
    (output/'casebook.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BasedBench comparison evidence</title><style>body{max-width:1250px;margin:30px auto;padding:0 20px;font:16px/1.5 system-ui;background:#f5f4ed;color:#253028}.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px}img{max-width:100%;max-height:800px;object-fit:contain}article{padding:25px 0;border-bottom:2px solid #ccc}section{padding:12px;border:1px solid #ccd3c6;margin:10px 0;background:white}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 system-ui}summary{cursor:pointer}@media(max-width:750px){.pair{grid-template-columns:1fr}}</style><h1>Explanation comparison evidence</h1><p>Model findings can be wrong. Fresh cases have no new human labels. Conditions are shuffled per case; their identities are hidden until revealed.</p>'+''.join(blocks)+'</html>')
    write_json(output/'manifest.json',{'source_results_manifest_sha256':file_hash(run/'results-manifest.json'),
                                     'files':{p.name:file_hash(p) for p in sorted(output.iterdir()) if p.is_file()}})
    return {k:v for k,v in summary.items() if k not in {'rows','run_report'}}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();print(json.dumps(build(a.run,a.output),indent=2))
