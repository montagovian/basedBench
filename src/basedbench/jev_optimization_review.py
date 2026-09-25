"""Render a read-only, static local review of the Jev optimization run."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path

from basedbench.pipeline.jev_optimization_protocol import summarize

METHODS = (
    ('broad', 'Broad check'),
    ('combined', 'Combined features'),
    ('calibrated', 'Calibrated check'),
    ('seed', 'Unoptimized seed'),
    ('optimized', 'Optimized policy'),
)


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)


def _read(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _shell(title: str, content: str) -> str:
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title><style>
:root{{--ink:#20251e;--muted:#59635a;--line:#d9ded5;--paper:#faf9f4;--card:#fff;--accent:#274d3b}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 system-ui,-apple-system,sans-serif}}
main{{max-width:1080px;margin:auto;padding:2.5rem 1.25rem 5rem}}h1{{font-size:clamp(2rem,5vw,3.6rem);line-height:1.08;letter-spacing:-.035em;margin:0 0 1.3rem}}
h2{{font-size:1.45rem;margin:2.8rem 0 .7rem}}h3{{font-size:1.12rem;margin:.2rem 0}}p{{max-width:75ch}}.lead{{font-size:1.22rem;max-width:68ch}}
.muted,small{{color:var(--muted)}}.callout{{border-left:4px solid var(--accent);padding:.1rem 1rem;background:#edf3ec}}
.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;background:var(--card)}}th,td{{text-align:left;border-bottom:1px solid var(--line);padding:.7rem .65rem;vertical-align:top}}
th{{font-size:.86rem;color:var(--muted)}}tbody tr:last-child td{{border-bottom:0}}.case{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:1.1rem 1.3rem;margin:1rem 0}}
.case p{{margin:.45rem 0}}.casehead{{display:flex;gap:1rem;justify-content:space-between;flex-wrap:wrap}}.badge{{display:inline-block;border-radius:2rem;padding:.1rem .55rem;background:#e8eee6;font-size:.82rem}}
.evidence{{margin:.6rem 0;padding:.5rem .7rem;border-left:3px solid #c18a46;background:#fbf6e9}}details{{margin:.6rem 0}}summary{{cursor:pointer;color:var(--accent)}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;max-height:28rem;overflow:auto;background:#f3f4f0;border:1px solid var(--line);padding:.8rem;font-size:.8rem}}
input[type=search]{{width:100%;max-width:35rem;border:1px solid #a8b4aa;border-radius:8px;padding:.65rem .8rem;font:inherit}}
@media(max-width:650px){{th,td{{padding:.48rem;font-size:.9rem}}}}
</style></head><body><main>{content}</main></body></html>'''


def _outcome(report: dict) -> str:
    screen = report['development_screen']
    broad = report['metrics']['broad']
    opt = report['metrics']['optimized']
    change = opt['repair_catches'] - broad['repair_catches']
    direction = f'{change:+d}'
    if screen['met']:
        return (f'The optimized policy met the preset development screen: {direction} net repairs caught '
                f'compared with the broad check, with {opt["ready_passes"]} of 77 ready explanations passed. '
                'This is a development result for human review, not a release decision.')
    return (f'The optimized policy did not meet the preset development screen: {direction} net repairs caught '
            f'compared with the broad check, with {opt["ready_passes"]} of 77 ready explanations passed. '
            'The benchmark labels and production checker have not changed.')


def _essential_issues(case: dict, result: dict) -> list[str]:
    items = []
    comments = {c['id']: c['text'] for c in case['comments']}
    for row in result.get('trace', {}).get('units', []):
        if not row.get('essential'):
            continue
        coverage = row.get('coverage', {})
        if coverage.get('choice') not in ('missing', 'contradicted', 'unresolved'):
            continue
        unit = row['unit']
        text = comments.get(unit['comment_id'])
        start, end = unit['start'], unit['end']
        if text is None or type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
            raise ValueError('Trace source offset does not match comment')
        excerpt = text[start:end]
        if excerpt != unit['text']:
            raise ValueError('Trace unit text differs from exact source slice')
        items.append(f'<div class="evidence"><b>{_esc(coverage["choice"])} essential source</b> '
                     f'({_esc(unit["comment_id"])}:{start}–{end})<br>{_esc(excerpt)}</div>')
    return items


def _case_card(case: dict, seed: dict, optimized: dict) -> str:
    cid = case['case_id']
    trace_seed = seed['result']['trace']
    trace_opt = optimized['result']['trace']
    evidence = ''.join(_essential_issues(case, optimized['result'])) or '<p class="muted">No essential source unit marked missing, contradicted, or unresolved.</p>'
    comments = ''.join(f'<p><b>{_esc(c["id"])}</b> {_esc(c["text"])}</p>' for c in case['comments'])
    seed_reason = trace_seed.get('reason_codes') or [trace_seed.get('hold', 'reason unavailable')]
    opt_reason = trace_opt.get('reason_codes') or [trace_opt.get('hold', 'reason unavailable')]
    decisions = (f'Broad {_esc(case["baseline"]["broad"])} · '
                 f'Seed {_esc(seed["prediction"])} ({_esc(", ".join(map(str, seed_reason)))}) · '
                 f'Optimized {_esc(optimized["prediction"])} ({_esc(", ".join(map(str, opt_reason)))})')
    raw = {'case': case, 'seed': seed, 'optimized': optimized}
    return f'''<article class="case"><div class="casehead"><h3>{_esc(cid)}</h3><span class="badge">Human: {_esc(case['gold'])}</span></div>
<p><b>{decisions}</b></p><p>{_esc(case['input']['explanation'])}</p>
{evidence}<details><summary>Reader comments</summary>{comments}</details>
<details><summary>Full source-linked trace and case JSON</summary><pre>{_esc(_json(raw))}</pre></details></article>'''


def complete_html(report: dict, cases: list[dict], records: list[dict]) -> str:
    """Render complete matched results and every broad-or-seed changed case."""
    by_id = {case['case_id']: case for case in cases}
    if len(by_id) != 94 or len(cases) != 94:
        raise ValueError('Review requires exact 94-case matched set')
    recomputed = summarize(by_id, records)
    for key in ('eligible', 'gold', 'metrics', 'paired_families', 'development_screen'):
        if report.get(key) != recomputed[key]:
            raise ValueError(f'Report differs from cases and records: {key}')
    finals = {(r['case_id'], r['method']): r for r in records}
    if len(finals) != 188 or len(records) != 188:
        raise ValueError('Review requires seed and optimized decisions for every case')
    rows = []
    for method, label in METHODS:
        m = report['metrics'][method]
        uncertain = m['counts']['ready'].get('uncertain', 0) + m['counts']['repair'].get('uncertain', 0)
        rows.append(f'<tr><td>{_esc(label)}</td><td>{m["ready_passes"]}/77</td>'
                    f'<td>{m["repair_catches"]}/17</td><td>{uncertain}</td></tr>')
    changed = []
    for cid in sorted(by_id):
        case = by_id[cid]
        seed, opt = finals[cid, 'seed'], finals[cid, 'optimized']
        if opt['prediction'] != case['baseline']['broad'] or opt['prediction'] != seed['prediction']:
            changed.append(_case_card(case, seed, opt))
    cost = report.get('provider_ledger', {}).get('spent_or_reserved_usd')
    cost_text = f'${float(cost):.4f}' if type(cost) in (int, float) else 'not reported'
    pairs = report['paired_families']
    section = f'''<h1>Did optimization help?</h1><p class="lead">{_esc(_outcome(report))}</p>
<div class="callout"><p>These are the same 94 previously exposed development versions: 77 labeled ready and 17 labeled repair. Human labels and notes were not changed. An undecided result is neither a ready pass nor a repair catch.</p></div>
<h2>Matched decisions</h2><div class="scroll"><table><thead><tr><th>Method</th><th>Ready passed</th><th>Repairs caught</th><th>Undecided</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p class="muted">Six paired families have both ready and repair versions. Both versions judged correctly: broad {pairs['broad']['both_correct']}/6; seed {pairs['seed']['both_correct']}/6; optimized {pairs['optimized']['both_correct']}/6. Accounted provider cost: {_esc(cost_text)}.</p>
<h2>Changed cases ({len(changed)})</h2><p>Optimized differs from the broad check or the unoptimized seed. Search the explanations, comments, and traces.</p>
<label for="find">Search changed cases</label><br><input id="find" type="search" placeholder="Search text or case ID" autocomplete="off">
<div id="cases">{''.join(changed) or '<p>No changed decisions.</p>'}</div>
<details><summary>All 94 case inputs and labels</summary><pre>{_esc(_json(cases))}</pre></details>
<p class="muted">This page is a local review of saved decisions. It does not promote a policy, change the active checker, or alter human judgments.</p>
<script>const search=document.getElementById('find');search.addEventListener('input',()=>{{const query=search.value.toLocaleLowerCase();for(const card of document.querySelectorAll('.case'))card.hidden=!card.textContent.toLocaleLowerCase().includes(query)}});</script>'''
    return _shell('Jev optimization review', section)


def partial_html(partial: dict, diagnostic: dict | None = None) -> str:
    ledger = partial.get('provider_ledger') or {}
    calls = diagnostic.get('total_attempted_calls', ledger.get('calls', 0)) if diagnostic else ledger.get('calls', 0)
    cost = diagnostic.get('total_accounted_usd', ledger.get('spent_or_reserved_usd', 0)) if diagnostic else ledger.get('spent_or_reserved_usd', 0)
    pending = ledger.get('pending_calls', 0)
    reason = partial.get('reason') or ledger.get('stop_reason') or 'Unknown technical stop'
    detail = ''
    if diagnostic:
        problem = diagnostic.get('response_problem', {})
        probabilities = problem.get('probabilities', {})
        chosen = problem.get('choice')
        if isinstance(probabilities, dict) and chosen is not None:
            ranked = sorted(((str(key), value) for key, value in probabilities.items()
                             if type(value) in (int, float)), key=lambda pair: -pair[1])
            top = ranked[0] if ranked else None
            if top:
                detail = (f'<p>One Jev response chose <b>{_esc(chosen)}</b> at '
                          f'{_esc(probabilities.get(chosen))} probability while '
                          f'<b>{_esc(top[0])}</b> had the higher probability '
                          f'{_esc(top[1])}. The strict parser stopped on that mismatch.</p>')
        detail += (f'<p>The first fold stopped after {_esc(diagnostic.get("reflections_completed", 0))} '
                   f'reflection proposals and {_esc(diagnostic.get("actual_case_evaluations_completed", 0))} '
                   f'case-policy evaluations. {_esc(diagnostic.get("outer_folds_completed", 0))} folds and '
                   f'{_esc(diagnostic.get("final_cases_evaluated", 0))} final cases completed.</p>')
        detail += ('<p>A new declared run could treat an invalid provider response as an abstention for '
                   'that case. This stopped run did not auto-correct or drop the response.</p>')
    section = f'''<h1>Run stopped before comparison</h1>
<p class="lead">The search stopped before the five methods could be compared on all 94 cases. No quality result is available yet.</p>
<div class="callout">{detail if diagnostic else '<p><b>Technical stop:</b> ' + _esc(reason) + '</p>'}</div>
<p>Attempted calls: {_esc(calls)}. Accounted spend or reserve: {_esc(f'${float(cost):.4f}')}. Pending calls: {_esc(pending)}.</p>
<details><summary>Technical error</summary><pre>{_esc(reason)}</pre></details>
<p>This partial search does not show whether optimization helped. Existing human labels, notes, and the active checker remain unchanged.</p>'''
    return _shell('Jev optimization stopped', section)


def render(root: Path, output: Path | None = None) -> Path:
    """Read frozen run files and write only root/review/index.html."""
    root = Path(root).resolve()
    output = Path(output).resolve() if output is not None else root / 'review'
    if output != root / 'review':
        raise ValueError('Review output must be the dedicated root/review directory')
    if (root / 'complete.json').is_file():
        complete = _read(root / 'complete.json')
        for name in ('report.json', 'records.json', 'policies.json'):
            expected = complete.get('files', {}).get(name)
            if not isinstance(expected, str) or _sha(root / name) != expected:
                raise ValueError('Completed run artifact hash mismatch: ' + name)
        report = _read(root / 'report.json')
        if report.get('status') != 'complete':
            raise ValueError('Report is not complete')
        page = complete_html(report, _read(root / 'cases.json'), _read(root / 'records.json'))
    elif (root / 'partial.json').is_file():
        stop_path = root / 'stop-analysis.json'
        stopped_manifest = root / 'stopped-manifest.json'
        if stopped_manifest.is_file():
            hashes = _read(stopped_manifest).get('files', {})
            for name in ('partial.json', 'stop-analysis.json'):
                path = root / name
                expected = hashes.get(name)
                if not isinstance(expected, str) or not path.is_file() or _sha(path) != expected:
                    raise ValueError('Stopped run artifact hash mismatch: ' + name)
        page = partial_html(_read(root / 'partial.json'), _read(stop_path) if stop_path.is_file() else None)
    else:
        raise ValueError('Run has neither complete nor partial status')
    output.mkdir(parents=True, exist_ok=True)
    target = output / ('index.html' if (root / 'complete.json').is_file() else 'partial.html')
    if target.exists():
        raise FileExistsError('Review already exists; preserve the earlier rendering')
    target.write_text(page, encoding='utf-8')
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(render(args.root, args.output))


if __name__ == '__main__':
    main()
