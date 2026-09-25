"""Freeze unseen cached candidates, then hold retrieval links without replacing rows."""
from __future__ import annotations

from collections import Counter
import itertools
import json
from pathlib import Path
import shutil
import sqlite3

import numpy as np

from basedbench.calibration_review import family_groups
from basedbench.pipeline import duplicate_audit as audit, duplicate_comparison as crop, duplicates
from basedbench.pipeline.curation_corpus import _historical_input, digest, file_hash, write_json

VERSION = 'calibrated-fresh-v1'


def prepare(root: Path, feedback: Path, output: Path):
    if output.exists():
        raise FileExistsError('Fresh sampling is not resampled after inspection')
    root = root.resolve()
    prior_packet = root / 'data/curation/explanation-calibration-v1'
    original_selection = json.loads((prior_packet / 'selection.json').read_text())
    reviewed = json.loads((feedback / 'cases.json').read_text())
    reviewed_ids = {c['post_id'] for c in reviewed}
    eligible = [r for r in original_selection['eligibility'] if r['eligible'] and r['post_id'] not in reviewed_ids]
    # Freeze the 30 identities before the additional image/text screen. Holds are
    # retained in the denominator and never replaced with cleaner candidates.
    selected = sorted(eligible, key=lambda r: digest([VERSION, 'selection', r['post_id']]))[:30]
    if len(selected) != 30:
        raise ValueError('Need 30 remaining cached candidates before screening')
    chosen = {r['post_id'] for r in selected}
    output.mkdir(parents=True)
    (output / 'assets').mkdir()
    write_json(output / 'selection-before-screen.json', {'version': VERSION, 'pool_size': len(eligible),
        'selected_ids': [r['post_id'] for r in selected], 'selection': 'Frozen hash order from remaining eligible cached rows; no post-screen replacement.'})
    old_audit = root / 'data/backfill/duplicate-audit-v1'
    records = json.loads((old_audit / 'inputs.json').read_text())
    by_id = {r['post_id']: r for r in records}
    report = json.loads((old_audit / 'report.json').read_text())
    known = json.loads((old_audit / 'known_families.json').read_text())
    known += [[r['left'], r['right']] for r in json.loads((feedback / 'duplicate-inspection.json').read_text())]
    groups = family_groups(records, report['edges'], known)
    db = root / 'data/basedbench.db'
    before = file_hash(db)
    blocked = set(reviewed_ids)
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('BEGIN')
        blocked.update(r[0] for r in conn.execute('SELECT post_id FROM reviews UNION SELECT post_id FROM consensus_eval_items UNION SELECT post_id FROM consensus_regression UNION SELECT post_id FROM gate_feedback'))
        for base in ('data/curation', 'data/backfill'):
            for path in (root / base).rglob('cases.json'):
                if path.is_relative_to(output.resolve()):
                    continue
                values = json.loads(path.read_text())
                if isinstance(values, list):
                    blocked.update(c['post_id'] for c in values if isinstance(c, dict) and 'post_id' in c)
        candidates = []
        for item in selected:
            pid = item['post_id']
            g = conn.execute('SELECT * FROM ground_truths WHERE post_id=?', (pid,)).fetchone()
            calls = list(conn.execute("SELECT * FROM llm_calls WHERE post_id=? AND role='consensus' AND verdict='consensus' AND error IS NULL AND abs(julianday(created_at)-julianday(?))*86400 < 2", (pid, g['created_at'])))
            if len(calls) != 1:
                raise ValueError('Generation provenance changed')
            inp = _historical_input(dict(calls[0]))
            if inp['explanation'] != g['explanation'].strip():
                raise ValueError('Stored explanation changed')
            inp['image_sha256'] = by_id[pid]['image']['sha256']
            candidates.append({'case_id': pid, 'post_id': pid, 'input': inp, 'input_sha256': digest(inp),
                               'stratum': 'fresh_cached', 'group_id': groups[pid], 'family_weight': 1,
                               'generation_call_sha256': digest(dict(calls[0]))})
    if file_hash(db) != before:
        raise ValueError('Database changed during preparation')
    blocked_groups = {groups.get(pid, pid) for pid in blocked}
    reference_ids = blocked | chosen
    refs = [r for r in records if r['post_id'] in reference_ids]
    cached_images, thumbs, rows, retained = {}, {}, [], []
    def image(pid):
        if pid not in cached_images:
            record = by_id[pid]
            path = Path(record['image_path']) if record.get('image_path') else None
            if path and path.is_file() and file_hash(path) != record['image'].get('sha256'):
                raise ValueError('Image differs from frozen audit')
            cached_images[pid] = crop.load_static(path)
        return cached_images[pid]
    packing = json.loads((old_audit / 'text_packing.json').read_text())
    vectors = np.load(old_audit / 'text_vectors.npy')
    vector_index = {r['post_id']: i for i, r in enumerate(packing)}
    if len(vectors) != len(packing):
        raise ValueError('Semantic vector identity mismatch')
    for c in candidates:
        pid = c['post_id']; record = by_id[pid]; edges = []
        if pid in blocked or groups[pid] in blocked_groups:
            edges.append({'method': 'prior_exposure_or_family', 'match': groups[pid]})
        coarse = []
        for other in refs:
            oid = other['post_id']
            if oid == pid:
                continue
            kind = audit.exact_kind(record['image'], other['image'])
            if kind:
                edges.append({'method': kind, 'match': oid})
                continue
            near = audit.image_evidence(record['image'], other['image'], old_audit, thumbs)
            if near and near['pixel_difference'] <= 18:
                edges.append(dict(near, match=oid))
            distance = min((max(duplicates.hamming_distance(a['dhash'], b['dhash']),
                                duplicates.hamming_distance(a['ahash'], b['ahash']))
                            for a, b in itertools.product(record['image']['variants'], other['image']['variants'])), default=65)
            if distance <= 18:
                coarse.append((distance, oid))
        crop_ids = reviewed_ids | {oid for _, oid in sorted(coarse)[:20]}
        for oid in sorted(crop_ids - {pid}):
            if oid in by_id:
                evidence = crop.crop_evidence(image(pid), image(oid))
                if evidence:
                    edges.append(dict(evidence, match=oid))
        if pid in vector_index:
            scores = vectors @ vectors[vector_index[pid]]
            semantic = sorted(((float(scores[i]), oid) for oid, i in vector_index.items()
                               if oid in reference_ids and oid != pid and scores[i] >= .65), reverse=True)[:5]
            edges += [{'method': 'minilm', 'match': oid, 'score': round(score, 6)} for score, oid in semantic]
        status = 'family_or_exposure_hold' if edges else 'eligible'
        if record['image']['status'] != 'ok':
            status = 'image_hold'
        rows.append({'post_id': pid, 'status': status, 'retrieval_candidates_not_gold': edges})
        if status == 'eligible':
            retained.append(c)
            shutil.copyfile(Path(record['image_path']), output / 'assets' / c['input']['image_sha256'])
        print(f'Fresh screen {len(rows)}/30; retained {len(retained)}', flush=True)
    write_json(output / 'cases.json', retained)
    write_json(output / 'screening.json', rows)
    selection = {'selected': 30, 'pool': len(eligible), 'statuses': dict(Counter(r['status'] for r in rows)),
                 'no_replacement': True, 'paid_calls': 0, 'cost_usd': 0,
                 'scope': 'All recorded reviewed/evaluation cases: exact and full/trim near-image retrieval; aspect crops against all 50 human cases plus 20 coarse image neighbors; saved MiniLM top-five links at .65. Links conservatively hold rows, not gold duplicate adjudications.',
                 'limitations': ['Conditional cached-generation sample, not full chronological admission yield.',
                                 'Semantic families and crop retrieval remain incomplete.',
                                 'No new human labels; model outcomes are routing evidence only.']}
    write_json(output / 'selection-report.json', selection)
    manifest = {'version': VERSION, 'source_database_sha256': before,
                'feedback_manifest_sha256': file_hash(feedback / 'manifest.json'),
                'code_sha256': file_hash(Path(__file__)), 'retrieval_code': crop.code_hashes(),
                'source_hashes': {name: file_hash(old_audit / name) for name in ('inputs.json', 'report.json', 'text_packing.json', 'text_vectors.npy')},
                'files': {str(p.relative_to(output)): file_hash(p) for p in sorted(output.rglob('*')) if p.is_file()}}
    manifest['snapshot_id'] = digest(manifest)
    write_json(output / 'manifest.json', manifest)
    return selection


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    print(json.dumps(prepare(Path.cwd(), Path('data/curation/explanation-calibration-feedback-v1'), args.output), indent=2))
