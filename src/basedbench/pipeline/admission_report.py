"""Read-only accounting and local casebook for a completed admission pilot."""
from __future__ import annotations

import argparse
from collections import Counter
import html
import json
import os
from pathlib import Path

from basedbench.pipeline import admission_pilot as pilot
from basedbench.pipeline.curation_corpus import file_hash, write_json

COMPONENT_LABELS = {'preflight': 'Available evidence', 'duplicates': 'Duplicate check',
                    'content': 'Content rules', 'answer': 'Answer check', 'suitability': 'Joke suitability'}
REASON_LABELS = {
    'available_evidence': 'The image and enough comments are available.',
    'missing_image': 'The source image could not be retrieved.',
    'source_mismatch': 'The live source no longer matches the archived source.',
    'fewer_than_three_comments': 'Fewer than three usable comments are available.',
    'unresolved_duplicate_match': 'A possible duplicate or related joke has not been resolved.',
    'no_duplicate_detected': 'No duplicate was found by the current checks.',
    'copy_outside_release': 'The matching archived copy is outside the published collection.',
    'redundant_published_copy': 'An exact copy is already published.',
    'controlled_unique_fixture': 'Duplicate checking is isolated for this historical control.',
    'no_excluded_content_found': 'The check found no content excluded by the current rules.',
    'established_exclusion': 'The check found content excluded by the current rules.',
    'policy_boundary': 'The content sits on an unsettled policy boundary.',
    'needs_context': 'More context is needed to apply the content rules.',
    'model_verified_proposal': 'The model approved this explanation against the supplied evidence.',
    'insufficient_answer_evidence': 'The model could not construct an answer with enough supporting evidence.',
    'answer_unresolved': 'The proposed answer did not clear the evidence check.',
    'repair_evidence_insufficient': 'The model could not support a repair.',
    'human_ready_answer_challenged': 'The model challenged a human-approved answer; the human judgment is preserved.',
    'known_answer_defect_not_resolved': 'The model passed an answer already known to be wrong, without fixing it.',
    'unresolved_human_judgment': 'An unsettled human judgment remains unresolved.',
    'human_model_disagreement': 'The model and an existing human judgment disagree.',
    'recoverable_task': 'The model identified a concrete joke connection to understand.',
    'unclear_task': 'The model was unsure whether there is a recoverable joke.',
    'transcription_only': 'The model found description or transcription, without a further joke connection.',
    'incoherent_connection': 'The supposed joke connection does not fit together.',
    'missing_private_context': 'The joke depends on unavailable private context.',
    'budget_exhausted': 'The remaining budget could not cover this request.',
}


def readable_reason(code: str) -> str:
    if code.startswith('blocked_by_'):
        name = code.removeprefix('blocked_by_')
        return f'Stopped earlier at {COMPONENT_LABELS.get(name, name).lower()}.'
    return REASON_LABELS.get(code, code.replace('_', ' ').capitalize() + '.')


def summarize(cases: list[dict], report: dict, inspection: dict) -> dict:
    if not report['complete']:
        raise ValueError('Assessment requires a completed batch')
    outcomes = report['outcomes']
    ids = [c['post_id'] for c in cases]
    result_ids = [o['post_id'] for o in outcomes]
    if len(ids) != len(set(ids)) or len(result_ids) != len(set(result_ids)) or set(ids) != set(result_ids):
        raise ValueError('Every frozen candidate must have exactly one outcome')
    notes = inspection.get('items', {})
    if inspection and inspection.get('experiment_id') != report['experiment_id']:
        raise ValueError('Inspection belongs to another experiment')
    if set(notes) - set(ids):
        raise ValueError('Inspection includes unknown candidates')
    counts = dict(Counter(o['decision'] for o in outcomes))
    if counts != report['counts']:
        raise ValueError('Outcome counts disagree with the report')
    by_id = {c['post_id']: c for c in cases}
    stages = ('preflight', 'duplicates', 'content', 'answer', 'suitability')
    stop = Counter()
    for o in outcomes:
        stop[next((s for s in stages if o['components'][s]['decision'] != 'pass'), 'accepted')] += 1
    groups = {}
    for name, key in [('community', 'subreddit'), ('day', 'source_date')]:
        rows = {}
        for o in outcomes:
            value = by_id[o['post_id']].get('provenance', {}).get(key) or 'unknown'
            if name == 'day' and value != 'unknown':
                value = value[:10]
            row = rows.setdefault(value, Counter())
            row['total'] += 1
            row[o['decision']] += 1
        groups[name] = {k: dict(v) for k, v in sorted(rows.items())}
    accepted = [o for o in outcomes if o['decision'] == 'accept']
    inspected_accepted = [o for o in accepted if o['post_id'] in notes]
    unflagged = [o for o in inspected_accepted if notes[o['post_id']]['assessment'] == 'no_issue_found']
    repairs = [o for o in outcomes if any(s.endswith('_repair') for s in o.get('answer_stages', {}))]
    verified_repairs = [o for o in repairs if o['components']['answer'].get('repaired')]
    cost = report['cost']['estimated_usd']
    cost_known = report['cost']['unknown_usage_calls'] == 0
    tag_rows = {}
    for o in outcomes:
        for tag in set(notes.get(o['post_id'], {}).get('tags', [])):
            row = tag_rows.setdefault(tag, Counter())
            row['inspected'] += 1
            row[o['decision']] += 1
    return {
        'experiment_id': report['experiment_id'], 'candidate_count': len(cases), 'counts': counts,
        'exclusive_stopping_stage': dict(stop),
        'component_decisions': {s: dict(Counter(o['components'][s]['decision'] for o in outcomes)) for s in stages},
        'component_technical_errors': {s: sum(o['components'][s]['technical_status'] == 'error' for o in outcomes) for s in stages},
        'technical_error_candidates': sum(o['technical_status'] == 'error' for o in outcomes),
        'reason_counts_overlapping': dict(Counter(r for o in outcomes for r in o['reason_codes'])),
        'repair_attempts': len(repairs), 'model_verified_repairs': len(verified_repairs),
        'accepted_after_repair': sum(o['decision'] == 'accept' for o in verified_repairs),
        'coverage': groups, 'cost': report['cost'],
        'cost_per_automatic_accept_usd': cost / len(accepted) if accepted and cost_known else None,
        'inspection': {'kind': 'assistant_inspection_not_human_gold', 'inspected_count': len(notes),
            'inspected_accepts': len(inspected_accepted), 'uninspected_accepts': len(accepted) - len(inspected_accepted),
            'accepted_without_detected_issue': len(unflagged),
            'accepted_with_flags': len(inspected_accepted) - len(unflagged),
            'flags_overlapping': dict(Counter(flag for n in notes.values() for flag in n.get('flags', []))),
            'exploratory_tags_overlapping': {k: dict(v) for k, v in sorted(tag_rows.items())},
            'cost_per_inspected_unflagged_accept_usd': cost / len(unflagged) if unflagged and cost_known else None},
        'definitions': {
            'automatic_accept': 'All frozen admission components passed; not independent validation.',
            'accepted_without_detected_issue': 'Automatic accept inspected by the assistant with no concrete issue found; not human gold or an accuracy estimate.',
            'cost': 'All batch model costs, including rejected/deferred candidates; excludes earlier development, collection infrastructure and assistant inspection.',
            'component_decisions': 'All recorded findings, including precomputed duplicate findings on candidates stopped at preflight; not sequential stage throughput.',
            'exclusive_stopping_stage': 'First component without a pass in pipeline order; sums to every candidate.',
            'tags': 'Assistant descriptions of inspected material only, overlapping and exploratory; no formal taxonomy or source-population prevalence claim.'}}


def render_casebook(cases: list[dict], report: dict, inspection: dict, summary: dict,
                    run: Path, output: Path) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    by_id = {c['post_id']: c for c in cases}
    notes = inspection.get('items', {})
    cards = []
    for o in report['outcomes']:
        pid = o['post_id']
        c = by_id[pid]
        note = notes.get(pid, {})
        sha = c['input'].get('image_sha256')
        asset = run / 'assets' / (sha or '')
        src = os.path.relpath(asset, output) if sha and asset.is_file() else None
        image = f'<a href="{esc(src)}" target="_blank"><img loading="lazy" src="{esc(src)}" alt="Meme {esc(pid)}"></a>' if src else '<p class="missing">Image unavailable in the frozen inventory.</p>'
        component_rows = ''.join(f'<li><b>{esc(label)}</b>: {esc(" ".join(readable_reason(r) for r in o["components"][k]["reason_codes"]))}</li>' for k, label in COMPONENT_LABELS.items())
        stages = esc(json.dumps(o.get('answer_stages', {}), indent=2, ensure_ascii=False))
        flags = ', '.join(note.get('flags', [])) or 'None recorded'
        cards.append(f'''<article data-decision="{esc(o['decision'])}" data-flagged="{'yes' if note.get('flags') else 'no'}">
<header><span class="badge {esc(o['decision'])}">{esc(o['decision'])}</span><b>{esc(pid)}</b>
<small>{esc(c.get('provenance', {}).get('subreddit', ''))} · {esc(c.get('provenance', {}).get('source_date', ''))}</small></header>
<div class="case"><div>{image}</div><div><h2>Proposed answer</h2><p>{esc(o.get('candidate_answer') or 'No answer cleared all answer checks.')}</p>
<h2>Why this outcome?</h2><ul>{component_rows}</ul><h2>Assistant inspection</h2>
<p>{esc(note.get('note', 'Not inspected.'))}</p><p class="meta">Flags: {esc(flags)}<br>Topics: {esc(', '.join(note.get('tags', [])))}</p>
<details><summary>Source comments supplied to the model</summary><pre>{esc(c['input']['comment_evidence'])}</pre></details>
<details><summary>Answer proposals, checks and repair history</summary><pre>{stages}</pre></details>
<details><summary>All component findings</summary><pre>{esc(json.dumps(o['components'], indent=2, ensure_ascii=False))}</pre></details>
</div></div></article>''')
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>basedBench · Admission assessment</title><style>
:root{font:17px/1.55 system-ui;color:#25332d;background:#f5f6ef}body{margin:0 auto;max-width:1300px;padding:32px}h1{font-size:40px;line-height:1.15;margin:10px 0}h2{font-size:18px;margin:18px 0 6px}p{margin:8px 0 15px}.intro{max-width:850px}.toolbar{position:sticky;top:0;background:#f5f6eff5;padding:16px 0;z-index:1;border-bottom:1px solid #ccd3c7;display:flex;gap:16px;align-items:center;flex-wrap:wrap}select{font:inherit;padding:8px;border:1px solid #abb7a8;border-radius:6px;background:white}article{background:white;border:1px solid #d7ddcf;border-radius:14px;margin:24px 0;overflow:hidden}header{padding:18px 24px;border-bottom:1px solid #e1e5da;display:flex;gap:16px;align-items:center;flex-wrap:wrap}small,.meta{font-size:14px;color:#5b6e61}.badge{padding:3px 12px;border-radius:20px;font-weight:650;text-transform:uppercase;font-size:13px}.accept{background:#d8eedc}.reject{background:#f2d4cc}.defer{background:#f1e6bb}.case{display:grid;grid-template-columns:minmax(280px,1fr) minmax(340px,1.2fr);gap:30px;padding:24px}.case img{width:100%;max-height:720px;object-fit:contain;background:#f5f6ef}li{margin:5px 0}ul{padding-left:22px}details{margin:12px 0;padding:12px;background:#f4f6f0;border-radius:8px}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 ui-monospace,monospace}.missing{padding:40px;background:#f3f3ec}article[hidden]{display:none}@media(max-width:800px){body{padding:16px}.case{grid-template-columns:1fr;padding:16px}h1{font-size:30px}}
</style><main><p class="meta">BASED BENCH / DEVELOPMENT PILOT</p><h1>What made it through?</h1>
<p class="intro">The frozen pilot batch contains ''' + str(summary['candidate_count']) + ''' candidates. These are automatic development decisions. Assistant inspection is shown separately; none of these findings is human validation or a published release.</p>
<p>''' + esc(' · '.join(f'{v} {k}' for k, v in summary['counts'].items())) + f''' · Estimated batch cost ${summary['cost']['estimated_usd']:.4f}</p>
<div class="toolbar"><label>Outcome <select id="outcome"><option value="all">All outcomes</option><option value="accept">Accepted</option><option value="reject">Rejected</option><option value="defer">Deferred</option></select></label>
<label>Inspection <select id="flags"><option value="all">All items</option><option value="yes">With inspection flags</option></select></label><span id="count"></span></div>
''' + '\n'.join(cards) + '''</main><script>
const outcome=document.querySelector('#outcome'),flags=document.querySelector('#flags'),cards=[...document.querySelectorAll('article')];
function filter(){let n=0;for(const card of cards){card.hidden=!((outcome.value==='all'||card.dataset.decision===outcome.value)&&(flags.value==='all'||card.dataset.flagged==='yes'));if(!card.hidden)n++;}document.querySelector('#count').textContent=n+' items shown';}
outcome.addEventListener('change',filter);flags.addEventListener('change',filter);filter();</script></html>'''


def build(run: Path, output: Path, inspection_path: Path | None = None) -> dict:
    if output.resolve().is_relative_to(run.resolve()):
        raise ValueError('Assessment must not write inside the frozen run')
    plan = pilot.load_plan(run)
    pilot.verify_manifest(run, json.loads((run / 'results-manifest.json').read_text()))
    report = json.loads((run / 'report.json').read_text())
    if report['experiment_id'] != plan['experiment_id']:
        raise ValueError('Report belongs to another experiment')
    cases = json.loads((run / 'cases.json').read_text())
    inspection = json.loads(inspection_path.read_text()) if inspection_path else {}
    summary = summarize(cases, report, inspection)
    summary['source_hashes'] = {str(p): file_hash(p) for p in [run / 'plan.json', run / 'cases.json', run / 'report.json', *([inspection_path] if inspection_path else [])]}
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / 'summary.json', summary)
    (output / 'casebook.html').write_text(render_casebook(cases, report, inspection, summary, run, output))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inspection', type=Path)
    args = parser.parse_args()
    summary = build(args.run, args.output, args.inspection)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
