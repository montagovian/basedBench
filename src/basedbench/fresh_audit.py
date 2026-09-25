"""Freeze the remaining cached pool for a blinded, zero-call human audit."""
from __future__ import annotations

import argparse
from collections import Counter
import itertools
import json
from pathlib import Path
import re
import shutil
import sqlite3

import numpy as np
from PIL import Image

from basedbench import calibration_review as review
from basedbench.curation_review import make_server
from basedbench.materiality_review import identified_manifest
from basedbench.pipeline import duplicate_audit as audit, duplicate_comparison as crop, duplicates
from basedbench.pipeline.connection_eval import verify_files
from basedbench.pipeline.curation_corpus import _historical_input, digest, file_hash, write_json

VERSION = 'fresh-human-audit-v1'
PLAN = Path('docs/fresh-human-audit.md')


def remaining_pool(selection, prior_selected, expected=18):
    eligible = {r['post_id'] for r in selection['eligibility'] if r['eligible']}
    chosen = eligible - set(selection['random_ids']) - set(prior_selected)
    if len(chosen) != expected:
        raise ValueError(f'Remaining pool changed: expected {expected}, found {len(chosen)}')
    return sorted(chosen, key=lambda pid: digest([VERSION, 'selection', pid]))


def exposure_ids(value):
    """Read actual case/dispatch/reference identities, not every eligibility mention."""
    found = set()
    if isinstance(value, list):
        for row in value:
            found.update(exposure_ids(row))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in {'post_id', 'case_id', 'left', 'right'} and isinstance(item, str):
                found.add(item)
            elif key in {'evaluation_ids', 'reference_ids', 'selected_ids', 'targeted_ids', 'random_ids'} and isinstance(item, list):
                found.update(x for x in item if isinstance(x, str))
            elif key == 'input_hashes' and isinstance(item, dict):
                found.update(item)
            elif key not in {'eligibility', 'exposure_scan', 'files', 'source_hashes'}:
                found.update(exposure_ids(item))
    return found


def exposure_ledger(root, conn, selected):
    blocked = {r[0] for r in conn.execute('SELECT post_id FROM reviews UNION SELECT post_id FROM consensus_eval_items UNION SELECT post_id FROM consensus_regression UNION SELECT post_id FROM gate_feedback')}
    blocked.update(r[0] for r in conn.execute("SELECT DISTINCT post_id FROM llm_calls WHERE role NOT IN ('consensus', 'safety_gate') AND post_id IS NOT NULL"))
    safety_ids = {r[0] for r in conn.execute("SELECT DISTINCT post_id FROM llm_calls WHERE role='safety_gate' AND post_id IS NOT NULL")}
    ledger = [{'path': 'data/basedbench.db', 'kind': 'review_evaluation_and_calls_outside_legacy_generation',
               'ids': sorted(blocked), 'legacy_safety_gate_ids': sorted(safety_ids)}]
    names = {'cases.json', 'plan.json', 'events.jsonl', 'reassessments.jsonl', 'inspection.json',
             'assistant-inspection.json', 'decisions.jsonl', 'components.jsonl', 'selection-before-screen.json'}
    for base in ('data/curation', 'data/backfill'):
        for path in sorted((root / base).rglob('*')):
            if not path.is_file() or not (path.name in names or 'inspection' in path.name and path.suffix == '.json'):
                continue
            values = ([json.loads(line) for line in path.read_text().splitlines() if line.strip()]
                      if path.suffix == '.jsonl' else json.loads(path.read_text()))
            ids = exposure_ids(values)
            blocked.update(ids)
            ledger.append({'path': str(path.relative_to(root)), 'sha256': file_hash(path), 'ids': sorted(ids)})
    pattern = re.compile(r'(?<![a-zA-Z0-9])(' + '|'.join(map(re.escape, selected)) + r')(?![a-zA-Z0-9])')
    for path in sorted((root / 'docs').rglob('*.md')):
        ids = set(pattern.findall(path.read_text()))
        blocked.update(ids)
        ledger.append({'path': str(path.relative_to(root)), 'sha256': file_hash(path), 'ids': sorted(ids)})
    return blocked, ledger


def recover(conn, pid, record, root):
    """Recover one exact original; missing/changed evidence is a hold, not replacement."""
    row = conn.execute('SELECT g.*, m.created_utc, m.subreddit FROM ground_truths g JOIN memes m USING(post_id) WHERE post_id=?', (pid,)).fetchone()
    if row is None or not row['explanation'].strip():
        raise ValueError('missing_cached_answer')
    calls = list(conn.execute("SELECT * FROM llm_calls WHERE post_id=? AND role='consensus' AND verdict='consensus' AND error IS NULL AND abs(julianday(created_at)-julianday(?))*86400 < 2", (pid, row['created_at'])))
    if len(calls) != 1:
        raise ValueError('ambiguous_generation_context')
    inp = _historical_input(dict(calls[0]))
    if inp['explanation'] != row['explanation'].strip():
        raise ValueError('changed_answer')
    path = Path(record.get('image_path') or '')
    if not path.is_absolute():
        path = root / path
    if not path.is_file() or file_hash(path) != record['image'].get('sha256'):
        raise ValueError('missing_or_changed_image')
    with Image.open(path) as image:
        if getattr(image, 'n_frames', 1) != 1:
            raise ValueError('unsupported_animated_image')
        mime = Image.MIME[image.format]
        image.verify()
    inp['image_sha256'] = file_hash(path)
    inp['answers'] = [{'source': 'original', 'text': inp['explanation']}]
    return {'post_id': pid, 'input': inp, 'input_sha256': digest(inp), 'image_path': str(path),
            'image_mime': mime, 'split': 'calibration', 'stratum': 'remaining_cached_pool', 'previous_feedback': [],
            'provenance': {'generation_call_id': calls[0]['id'], 'generation_record_sha256': digest(dict(calls[0])),
                           'generation_model': row['consensus_model'], 'created_utc': row['created_utc'],
                           'subreddit': row['subreddit'], 'previous_automated_retrieval_exposure': True}}


def screen(selected, records, groups, blocked, human_ids, directory, vectors, packing):
    """Conservative existing retrieval rules; no labels or explanation inspection."""
    by_id = {r['post_id']: r for r in records}
    if len(by_id) != len(records) or len(packing) != len(vectors):
        raise ValueError('Duplicate or mismatched retrieval identities')
    vector_index = {r['post_id']: i for i, r in enumerate(packing)}
    if len(vector_index) != len(packing):
        raise ValueError('Duplicate semantic-vector identity')
    refs = [r for r in records if r['post_id'] in blocked | set(selected)]
    blocked_groups = {groups.get(pid, pid) for pid in blocked}
    images, thumbs, rows = {}, {}, []
    def image(pid):
        if pid not in images:
            r = by_id[pid]
            path = Path(r['image_path']) if r.get('image_path') else None
            if path and path.is_file() and file_hash(path) != r['image'].get('sha256'):
                raise ValueError('Frozen retrieval image changed')
            images[pid] = crop.load_static(path)
        return images[pid]
    for pid in selected:
        record = by_id.get(pid)
        edges = []
        if pid in blocked or groups.get(pid, pid) in blocked_groups:
            edges.append({'method': 'prior_exposure_or_family', 'match': groups.get(pid, pid)})
        if record is None or record['image']['status'] != 'ok':
            rows.append({'post_id': pid, 'status': 'image_hold', 'retrieval_candidates_not_gold': edges})
            continue
        coarse = []
        for other in refs:
            oid = other['post_id']
            if oid == pid:
                continue
            kind = audit.exact_kind(record['image'], other['image'])
            if kind:
                edges.append({'method': kind, 'match': oid})
                continue
            near = audit.image_evidence(record['image'], other['image'], directory, thumbs)
            if near and near['pixel_difference'] <= 18:
                edges.append(dict(near, match=oid))
            distance = min((max(duplicates.hamming_distance(a['dhash'], b['dhash']), duplicates.hamming_distance(a['ahash'], b['ahash']))
                            for a, b in itertools.product(record['image']['variants'], other['image']['variants'])), default=65)
            if distance <= 18:
                coarse.append((distance, oid))
        for oid in sorted((human_ids | {oid for _, oid in sorted(coarse)[:20]}) - {pid}):
            if oid in by_id and (link := crop.crop_evidence(image(pid), image(oid))):
                edges.append(dict(link, match=oid))
        if pid in vector_index:
            scores = vectors @ vectors[vector_index[pid]]
            matches = sorted(((float(scores[i]), oid) for oid, i in vector_index.items()
                              if oid in blocked | set(selected) and oid != pid and scores[i] >= .65), reverse=True)[:5]
            edges.extend({'method': 'minilm', 'match': oid, 'score': round(score, 6)} for score, oid in matches)
        rows.append({'post_id': pid, 'status': 'family_or_exposure_hold' if edges else 'eligible', 'retrieval_candidates_not_gold': edges})
        print(f'Fresh audit screen {len(rows)}/{len(selected)}', flush=True)
    return rows


def build_packet(output, candidates, screening, selection, source_hashes, root):
    """Leave all holds in the selection; show only unheld originals in the gallery."""
    write_json(output / 'screening.json', screening)
    cases = []
    (output / 'images').mkdir()
    for row in screening:
        if row['status'] != 'eligible':
            continue
        c = dict(candidates[row['post_id']])
        path = Path(c.pop('image_path'))
        if file_hash(path) != c['input']['image_sha256']:
            raise ValueError('Image changed during packet copy')
        shutil.copyfile(path, output / 'images' / c['input']['image_sha256'])
        cases.append(c)
    if not cases:
        raise ValueError('All selected identities held; selection remains frozen, do not replace')
    cases.sort(key=lambda c: digest([VERSION, 'display', c['post_id']]))
    write_json(output / 'cases.json', cases)
    write_json(output / 'rubric.json', review.RUBRIC)
    (output / 'ui').mkdir()
    for name in ('review.js', 'review.css'):
        shutil.copyfile(review.STATIC / name, output / 'ui' / name)
    html = (review.STATIC / 'index.html').read_text()
    html = html.replace('Human calibration · round 2', 'Fresh candidate audit')
    html = html.replace('Short can be sufficient. Both answers can be acceptable.', 'Short can be sufficient. Optional detail is not a requirement.')
    html = html.replace('50 cases: 20 targeted examples and 30 random cached examples, mixed together. This is calibration, not an untouched test set. Model identities and past opinions stay hidden.',
        f'{len(cases)} original explanations from a fixed pool of {len(selection["selected_ids"])} cached candidates. Overlap and unavailable-evidence holds remain outside this gallery. Model identities and past opinions stay hidden. Record source support, fit or duplicate concerns separately in the note; they do not automatically make the answer wrong.')
    html = html.replace('Leave blank if ready. You can also note an optional improvement or uncertainty about source support.',
        'Leave blank if ready. You can separately note source support, fit, a possible duplicate, or an optional improvement.')
    (output / 'ui' / 'index.html').write_text(html)
    summary = {'selected': len(selection['selected_ids']), 'reviewable': len(cases),
               'statuses': dict(Counter(r['status'] for r in screening)), 'no_replacement': True,
               'new_api_calls': 0, 'cost_usd': 0, 'human_feedback_complete': False}
    write_json(output / 'selection-report.json', summary)
    manifest = {'schema_version': 'curation-review-packet-v1', 'purpose': review.VERSION,
                'study_version': VERSION, 'corpus_id': digest(source_hashes), 'rubric_sha256': digest(review.RUBRIC),
                'counts': {'remaining_cached_pool': len(cases)}, 'selected_count': len(selection['selected_ids']),
                'paired_cases': 0, 'new_api_calls': 0, 'cost_usd': 0, 'source_hashes': source_hashes,
                'implementation_hashes': {str(p.relative_to(root)): file_hash(p) for p in
                    (Path(__file__).resolve(), Path(review.__file__).resolve(), *sorted(review.STATIC.glob('*')))},
                'limitations': ['Conditional census of remaining cached legacy answers, not full admission yield or Luna generation performance.',
                                'Previously reviewed/evaluated families are conservatively held; semantic-family coverage is incomplete.',
                                'Automated retrieval exposure persists; no claim of an untouched benchmark test set.',
                                'Human answer readiness does not certify source support or suitability.'],
                'files': {str(p.relative_to(output)): file_hash(p) for p in sorted(output.rglob('*')) if p.is_file()}}
    manifest['packet_id'] = digest(manifest)
    write_json(output / 'manifest.json', manifest)
    review.CalibrationStore(output)
    return summary | {'packet_id': manifest['packet_id']}


def prepare(root: Path, output: Path, *, selection_source: Path | None = None):
    if output.exists():
        raise FileExistsError('Never overwrite or resample the frozen audit')
    root, output = root.resolve(), output.resolve()
    old = root / 'data/backfill/duplicate-audit-v1'
    previous = root / 'data/curation/explanation-calibration-v1'
    fresh = root / 'data/backfill/calibrated-fresh-packet-v1'
    human = root / 'data/curation/explanation-calibration-feedback-v1'
    boundary = root / 'data/curation/materiality-boundary-feedback-v1'
    sources = [old/'plan.json', old/'results-manifest.json', previous/'manifest.json', fresh/'manifest.json',
               human/'manifest.json', boundary/'manifest.json', root/PLAN, root/'data/basedbench.db']
    for directory, name, identity in [(old,'plan.json','audit_id'), (previous,'manifest.json','packet_id'),
                                     (fresh,'manifest.json','snapshot_id'), (human,'manifest.json','snapshot_id'),
                                     (boundary,'manifest.json','snapshot_id')]:
        identified_manifest(directory, name, identity)
    verify_files(old, json.loads((old/'results-manifest.json').read_text()))
    source_hashes = {str(p.relative_to(root)): file_hash(p) for p in sources}
    original = json.loads((previous/'selection.json').read_text())
    prior_selected = json.loads((fresh/'selection-before-screen.json').read_text())['selected_ids']
    selected = remaining_pool(original, prior_selected)
    if selection_source is not None:
        selection_source = selection_source.resolve()
        if ((selection_source.parent/'cases.json').exists()
                or (selection_source.parent/'manifest.json').exists()
                or (selection_source.parent/'events.jsonl').exists()):
            raise ValueError('Only an unserved failed preparation can supply the same frozen selection')
        prior = json.loads(selection_source.read_text())
        if prior['selected_ids'] != selected or prior['source_hashes'] != source_hashes:
            raise ValueError('Frozen selection or original sources changed')
        source_hashes[str(selection_source.relative_to(root))] = file_hash(selection_source)
    selection = {'version': VERSION, 'selected_ids': selected, 'seed': VERSION,
                 'original_eligible': sum(r['eligible'] for r in original['eligibility']),
                 'prior_human_random_ids': original['random_ids'], 'prior_fresh_selected_ids': prior_selected,
                 'source_hashes': source_hashes, 'code_sha256': file_hash(Path(__file__)),
                 'rule': 'All remaining identities, fixed before exposure/retrieval/context screen; no replacement.'}
    output.mkdir(parents=True)
    write_json(output/'selection-before-screen.json', selection)
    records = json.loads((old/'inputs.json').read_text()); by_id = {r['post_id']: r for r in records}
    families = json.loads((old/'known_families.json').read_text())
    families += [[r['left'],r['right']] for r in json.loads((human/'duplicate-inspection.json').read_text())]
    groups = review.family_groups(records, json.loads((old/'report.json').read_text())['edges'], families)
    human_ids = {r['post_id'] for d in (human,boundary) for r in json.loads((d/'cases.json').read_text())}
    candidates, input_holds = {}, {}
    with sqlite3.connect((root/'data/basedbench.db').as_uri()+'?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only = ON'); conn.execute('BEGIN')
        blocked, ledger = exposure_ledger(root, conn, selected)
        # The just-written selection belongs to this audit, not prior exposure.
        own = str((output/'selection-before-screen.json').relative_to(root))
        ignored = {own}
        if selection_source is not None:
            ignored.add(str(selection_source.relative_to(root)))
        ledger = [r for r in ledger if r['path'] not in ignored]
        blocked = {pid for row in ledger for pid in row['ids']}
        blocked.update(prior_selected)
        for pid in selected:
            try:
                candidates[pid] = recover(conn, pid, by_id[pid], root) | {'group_id': groups.get(pid,pid)}
            except (ValueError, KeyError, TypeError, OSError) as exc:
                input_holds[pid] = str(exc)
    write_json(output/'exposure-ledger.json', ledger)
    screening = screen(selected, records, groups, blocked, human_ids, old,
                       np.load(old/'text_vectors.npy'), json.loads((old/'text_packing.json').read_text()))
    for row in screening:
        if row['post_id'] in input_holds:
            row['retrieval_status'] = row['status']; row['status'] = 'input_hold'
            row['input_error'] = input_holds[row['post_id']]
    if any(file_hash(root/name) != sha for name,sha in source_hashes.items()):
        raise ValueError('Source changed during preparation; frozen selection retained')
    for row in ledger:
        if 'sha256' in row and file_hash(root/row['path']) != row['sha256']:
            raise ValueError('Exposure source changed during preparation')
    return build_packet(output, candidates, screening, selection, source_hashes, root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare'); p.add_argument('output', type=Path)
    p.add_argument('--selection-source', type=Path)
    p = sub.add_parser('serve'); p.add_argument('packet', type=Path); p.add_argument('--port', type=int, default=9878)
    args = parser.parse_args()
    if args.command == 'prepare':
        print(json.dumps(prepare(Path.cwd(), args.output, selection_source=args.selection_source), indent=2))
    else:
        server = make_server(args.packet, args.port, store=review.CalibrationStore(args.packet), static_dir=args.packet/'ui')
        print(f'Fresh answer audit: http://127.0.0.1:{server.server_port}/', flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()


if __name__ == '__main__':
    main()
