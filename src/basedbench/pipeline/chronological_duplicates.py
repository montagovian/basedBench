"""Read-only duplicate evidence for chronological backfills.

Exact bytes or decoded pixels establish image identity. Perceptual, crop, and
text matches are retrieval candidates only; they never adjudicate joke families.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import fcntl
import importlib.metadata
import itertools
import json
from pathlib import Path
import re
import sqlite3

from PIL import Image

from basedbench.pipeline import duplicate_audit as baseline, duplicate_comparison as comparison
from basedbench.pipeline import duplicates, curation_encoder
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json

VERSION = 'chronological-duplicate-audit-v1'
PARAMETERS = {'image_top_k_per_pool': 5, 'crop_top_k_per_pool': 20,
              'crop': comparison.PARAMETERS, 'baseline': baseline.PARAMETERS,
              'prior_pool': 'legacy_unpublished'}


def _safe_artifact_file(root: Path, name: str, what: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or not name or '..' in relative.parts:
        raise ValueError(f'Unsafe {what} path: {name}')
    base = root.resolve()
    if root.is_symlink():
        raise ValueError(f'Symlink artifact directory for {what}: {root}')
    path = root / relative
    # Reject symlinks at any level even when they currently point back inside.
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f'Symlink {what} path: {name}')
    resolved = path.resolve()
    if not resolved.is_relative_to(base):
        raise ValueError(f'{what} escapes its artifact directory: {name}')
    return resolved


def _verify_inventory(directory: Path) -> tuple[dict, list[dict]]:
    manifest_path = directory / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest.get('inventory_id'), str) or not isinstance(manifest.get('files'), dict):
        raise ValueError(f'Invalid inventory manifest: {directory}')
    required = {'plan.json', 'baseline.json', 'candidates.json'}
    if not required.issubset(manifest['files']):
        raise ValueError(f'Inventory manifest omits required inputs: {directory}')
    for name, expected in sorted(manifest['files'].items()):
        path = _safe_artifact_file(directory, name, 'inventory manifest')
        if not re.fullmatch(r'[0-9a-f]{64}', str(expected)) or not path.is_file() or file_hash(path) != expected:
            raise ValueError(f'Inventory changed: {directory}/{name}')
    source_plan = json.loads((directory / 'plan.json').read_text())
    inventory_id = manifest['inventory_id']
    if (source_plan.get('inventory_id') != inventory_id or
            digest({k: v for k, v in source_plan.items() if k != 'inventory_id'}) != inventory_id):
        raise ValueError(f'Inventory plan identity mismatch: {directory}')
    candidates = json.loads((directory / 'candidates.json').read_text())
    if not isinstance(candidates, list):
        raise ValueError(f'Invalid candidate inventory: {directory}')
    ids = [row.get('post_id') for row in candidates]
    if any(not isinstance(pid, str) or not pid for pid in ids) or len(set(ids)) != len(ids):
        raise ValueError(f'Invalid or duplicate candidate IDs: {directory}')
    return manifest, candidates


def _image_file(inventory: Path, candidate: dict) -> Path | None:
    image = candidate.get('image') or {}
    rel = image.get('path')
    if image.get('status') != 'available':
        return None
    if not isinstance(rel, str) or not rel:
        raise ValueError(f"Available image has no relative path: {candidate.get('post_id')}")
    path = _safe_artifact_file(inventory, rel, 'inventory image')
    expected = image.get('sha256')
    if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ValueError(f"Available image has no valid SHA256: {candidate.get('post_id')}")
    if not path.is_file():
        raise ValueError(f"Candidate image missing: {candidate.get('post_id')}")
    if file_hash(path) != expected:
        raise ValueError(f"Candidate image changed: {candidate.get('post_id')}")
    return path


def _archive_image_path(database: Path, stored: str | None) -> Path | None:
    if not stored:
        return None
    path = Path(stored)
    if not path.is_absolute():
        path = database.parent.parent / path
    return path.resolve()


def _code_hashes() -> dict:
    return {str(Path(module.__file__).resolve()): file_hash(Path(module.__file__)) for module in
        (__import__(__name__, fromlist=['x']), baseline, comparison, duplicates, curation_encoder)}


def prepare(database: Path, inventory: Path, output: Path, known_families: Path,
            *, prior_inventories: list[Path] | None = None) -> dict:
    """Freeze archive, prior pilot, and new inventory evidence without DB writes."""
    database, inventory, output, known_families = map(Path, (database, inventory, output, known_families))
    prior_inventories = [Path(p) for p in (prior_inventories or [])]
    if output.exists():
        raise FileExistsError('Use a new directory; frozen audits are not overwritten')
    inventory_manifest, candidates = _verify_inventory(inventory)
    prior_records = []
    prior_manifests = []
    for prior in prior_inventories:
        manifest, rows = _verify_inventory(prior)
        prior_manifests.append({'path': str(prior.resolve()), 'inventory_id': manifest['inventory_id'],
                                'manifest_sha256': file_hash(prior / 'manifest.json')})
        for item in rows:
            prior_records.append((prior, item))

    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only = ON')
        db.execute('BEGIN')
        archive = [dict(row) for row in db.execute('''
            SELECT m.post_id, m.title, m.local_image_path, g.explanation,
                   r.status AS review_status
            FROM memes m LEFT JOIN ground_truths g USING(post_id)
            LEFT JOIN reviews r USING(post_id) ORDER BY m.post_id
        ''')]
    baseline_file = json.loads((inventory / 'baseline.json').read_text())
    archive_ids = {r['post_id'] for r in archive}
    declared_archive = {r['post_id'] for r in baseline_file.get('posts', [])}
    if archive_ids != declared_archive:
        raise ValueError('Archive membership changed since inventory freeze')
    release = set(baseline_file.get('release_ids', []))

    rows: list[dict] = []
    for item in archive:
        path = _archive_image_path(database, item.get('local_image_path'))
        rows.append({'post_id': item['post_id'], 'pool': 'legacy', 'in_release': item['post_id'] in release,
                     'title': item.get('title') or '', 'image_path': str(path) if path else None,
                     'text': item.get('explanation') or '', 'text_source': 'stored_explanation',
                     'review_status': item.get('review_status')})

    new_ids = {r['post_id'] for r in candidates}
    for prior, item in sorted(prior_records, key=lambda pair: (pair[1]['post_id'], str(pair[0]))):
        pid = item['post_id']
        if pid in new_ids:
            raise ValueError(f'New inventory overlaps prior pool: {pid}')
        image_path = _image_file(prior, item)
        text, comment_ids = baseline.evidence_text(item)
        rows.append({'post_id': pid, 'pool': 'prior', 'in_release': False,
                     'title': item.get('title') or '', 'image_path': str(image_path) if image_path else None,
                     'expected_sha256': (item.get('image') or {}).get('sha256'), 'text': text,
                     'text_source': 'top_five_substantive_comments', 'comment_ids': comment_ids,
                     'review_status': None})
    for item in sorted(candidates, key=lambda row: (row.get('created_utc', 0), row['post_id'])):
        image_path = _image_file(inventory, item)
        text, comment_ids = baseline.evidence_text(item)
        rows.append({'post_id': item['post_id'], 'pool': 'fresh', 'in_release': False,
                     'title': item.get('title') or '', 'image_path': str(image_path) if image_path else None,
                     'expected_sha256': (item.get('image') or {}).get('sha256'), 'text': text,
                     'text_source': 'top_five_substantive_comments', 'comment_ids': comment_ids,
                     'review_status': None})
    if len({r['post_id'] for r in rows}) != len(rows):
        raise ValueError('Archive, prior, and new candidate IDs overlap')

    output.mkdir(parents=True)
    cache = {}
    for index, row in enumerate(rows):
        path = Path(row['image_path']) if row['image_path'] else None
        row['image_file_sha256'] = file_hash(path) if path and path.is_file() else None
        row['image'] = baseline.fingerprint(path, output)
        expected = row.get('expected_sha256')
        if expected and row['image'].get('sha256') != expected:
            raise ValueError(f"Image changed: {row['post_id']}")
        cache[row['post_id']] = row['image']
        if index % 500 == 0:
            print(f'Fingerprinted {index}/{len(rows)}', flush=True)
    known = json.loads(known_families.read_text())
    if (not isinstance(known, list) or any(not isinstance(group, list) or len(group) < 2
            or any(not isinstance(pid, str) for pid in group) for group in known)):
        raise ValueError('Known families must be arrays of at least two post IDs')
    row_ids = {r['post_id'] for r in rows}
    if any(pid not in row_ids for group in known for pid in group):
        raise ValueError('Unknown family member')
    write_json(output / 'inputs.json', rows)
    write_json(output / 'known_families.json', known)
    inputs = {'database_sha256': file_hash(database),
              'inventory': {'path': str(inventory.resolve()), 'inventory_id': inventory_manifest['inventory_id'],
                            'manifest_sha256': file_hash(inventory / 'manifest.json')},
              'prior_inventories': prior_manifests,
              'known_families_sha256': file_hash(known_families)}
    write_json(output / 'source_inputs.json', inputs)
    plan = {'version': VERSION, 'parameters': PARAMETERS, 'inventory_id': inventory_manifest['inventory_id'],
            'source_inputs': inputs, 'code': _code_hashes(), 'model': curation_encoder.MODEL_NAME,
            'revision': curation_encoder.MODEL_REVISION, 'paid_model_calls': 0, 'model_cost_usd': 0,
            'versions': {n: importlib.metadata.version(n) for n in
                         ['pillow', 'numpy', 'scikit-learn', 'sentence-transformers', 'torch']},
            'files': {str(p.relative_to(output)): file_hash(p) for p in sorted(output.rglob('*')) if p.is_file()}}
    plan['audit_id'] = digest(plan)
    write_json(output / 'plan.json', plan)
    return plan


def verify(output: Path) -> dict:
    plan = json.loads((output / 'plan.json').read_text())
    if plan.get('version') != VERSION or plan.get('parameters') != PARAMETERS:
        raise ValueError('Audit configuration changed')
    if plan.get('code') != _code_hashes():
        raise ValueError('Audit code changed; use a new frozen run')
    for name, expected in plan['files'].items():
        path = _safe_artifact_file(output, name, 'audit input')
        if not re.fullmatch(r'[0-9a-f]{64}', str(expected)) or not path.is_file() or file_hash(path) != expected:
            raise ValueError(f'Audit input changed: {name}')
    if digest({k: v for k, v in plan.items() if k != 'audit_id'}) != plan.get('audit_id'):
        raise ValueError('Audit plan changed')
    return plan


def _crop_best(left_path: Path | None, right_path: Path | None):
    left = comparison.load_static(left_path)
    right = comparison.load_static(right_path)
    evidence = comparison.crop_evidence(left, right)
    if evidence:
        evidence.pop('status', None)
    return evidence


def _text_edges(rows: list[dict], query_ids: set[str], output: Path, model_cache: Path):
    if not query_ids:
        selected = [r for r in rows if r['text'].strip()]
        return [], {'with_text': len(selected), 'by_pool': dict(Counter(r['pool'] for r in selected)),
                    'queries': 0, 'encoder_loaded': False}
    # The legacy audit's pool labels contain only legacy/fresh. Treat prior
    # pilot candidates as unpublished legacy comparison records for retrieval.
    text_rows = [dict(r, pool='legacy') if r['pool'] == 'prior' else r for r in rows]
    edges, coverage = baseline.text_neighbors(text_rows, query_ids, output, model_cache)
    coverage['prior_posts_in_legacy_pool'] = sum(r['pool'] == 'prior' and bool(r['text'].strip()) for r in rows)
    coverage['queries'] = len(query_ids)
    coverage['encoder_loaded'] = bool(coverage.get('with_text'))
    return edges, coverage


def run(output: Path, model_cache: Path) -> dict:
    """Perform deterministic local retrieval. Encoder loading is cache-only."""
    output, model_cache = Path(output), Path(model_cache)
    plan = verify(output)
    result_manifest = output / 'results-manifest.json'
    if result_manifest.exists():
        manifest = json.loads(result_manifest.read_text())
        for name, expected in manifest.items():
            path = _safe_artifact_file(output, name, 'audit result')
            if not re.fullmatch(r'[0-9a-f]{64}', str(expected)) or not path.is_file() or file_hash(path) != expected:
                raise ValueError(f'Audit result changed: {name}')
        return json.loads((output / 'report.json').read_text())

    lock_path = output / 'run.lock'
    with lock_path.open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another audit process holds the run lock') from exc
        plan = verify(output)
        rows = json.loads((output / 'inputs.json').read_text())
        known = json.loads((output / 'known_families.json').read_text())
        queries = {r['post_id'] for r in rows if r['pool'] == 'fresh'}
        by_id = {r['post_id']: r for r in rows}
        for row in rows:
            path = Path(row['image_path']) if row.get('image_path') else None
            expected = row.get('image_file_sha256')
            if expected and (not path or not path.is_file() or file_hash(path) != expected):
                raise ValueError(f"Source image changed after preparation: {row['post_id']}")
        edges: dict[tuple[str, str], dict] = {}

        def add(left: str, right: str, evidence: dict, confirmed: bool = False):
            key = tuple(sorted((left, right)))
            if left > right and evidence.get('method') in {'near_image', 'aspect_window'}:
                evidence = dict(evidence)
                for field in ('view', 'crop'):
                    a, b = evidence.get('left_' + field), evidence.get('right_' + field)
                    if a is not None or b is not None:
                        evidence['left_' + field], evidence['right_' + field] = b, a
            edge = edges.setdefault(key, {'left': key[0], 'right': key[1], 'status': 'candidate',
                'evidence': [], 'release_members': [p for p in key if by_id[p]['in_release']],
                'scope': 'fresh' if any(by_id[p]['pool'] == 'fresh' for p in key) else 'diagnostic'})
            if evidence not in edge['evidence']:
                edge['evidence'].append(evidence)
            if confirmed:
                edge['status'] = 'confirmed'

        image_cache = {}
        static_cache = {}
        for row in rows:
            if row['pool'] != 'fresh':
                continue
            near_by_pool = defaultdict(list)
            for other in rows:
                if other['post_id'] == row['post_id']:
                    continue
                exact = baseline.exact_kind(row['image'], other['image'])
                if exact:
                    add(row['post_id'], other['post_id'], {'method': exact}, True)
                    continue
                evidence = baseline.image_evidence(row['image'], other['image'], output, image_cache)
                if evidence:
                    evidence['query_id'] = row['post_id']
                    near_by_pool[other['pool']].append((other, evidence))
            for pool, choices in near_by_pool.items():
                choices.sort(key=lambda pair: (pair[1]['pixel_difference'],
                    pair[1]['dhash_distance'] + pair[1]['ahash_distance'], pair[0]['post_id']))
                for other, evidence in choices[:PARAMETERS['image_top_k_per_pool']]:
                    add(row['post_id'], other['post_id'], evidence)

            # Crop passes only the closest coarse full/trim candidates per pool.
            # This bounded retrieval route can miss crops and never confirms a copy.
            coarse = defaultdict(list)
            for other in rows:
                if other['post_id'] == row['post_id']:
                    continue
                left_variants = row['image'].get('variants', [])
                right_variants = other['image'].get('variants', [])
                if not left_variants or not right_variants:
                    continue
                score = min((duplicates.hamming_distance(a['dhash'], b['dhash']) +
                             duplicates.hamming_distance(a['ahash'], b['ahash'])
                             for a in left_variants for b in right_variants), default=129)
                coarse[other['pool']].append((score, other))
            crop_targets = set()
            for choices in coarse.values():
                crop_targets.update(other['post_id'] for _, other in sorted(
                    choices, key=lambda pair: (pair[0], pair[1]['post_id']))[:PARAMETERS['crop_top_k_per_pool']])
            for other in rows:
                if other['post_id'] == row['post_id'] or other['post_id'] not in crop_targets:
                    continue
                key = tuple(sorted((row['post_id'], other['post_id'])))
                if key not in static_cache:
                    static_cache[key] = _crop_best(Path(by_id[key[0]]['image_path']) if by_id[key[0]]['image_path'] else None,
                                                    Path(by_id[key[1]]['image_path']) if by_id[key[1]]['image_path'] else None)
                crop_evidence = static_cache[key]
                if crop_evidence:
                    crop_evidence = dict(crop_evidence, query_id=row['post_id'])
                    add(key[0], key[1], crop_evidence)

        text_edges, text_coverage = _text_edges(rows, queries, output, model_cache)
        for edge in text_edges:
            add(edge['left'], edge['right'], {'method': edge['method'], 'score': edge['score'],
                                               'query_id': edge['left']})
        diagnostics = []
        for group in known:
            for a, b in itertools.combinations(sorted(group), 2):
                edge = edges.get((a, b))
                assessed = a in queries or b in queries
                diagnostics.append({'left': a, 'right': b, 'retrieved': bool(edge) if assessed else None,
                    'assessed': assessed,
                    'methods': sorted({e['method'] for e in edge['evidence']}) if edge else []})
                add(a, b, {'method': 'previously_reviewed_family'}, True)
        ordered = [edges[key] for key in sorted(edges)]
        new_edges = [edge for edge in ordered if edge['scope'] == 'fresh']
        dispositions = []
        for row in rows:
            if row['pool'] != 'fresh':
                continue
            matches = [e for e in new_edges if row['post_id'] in (e['left'], e['right'])]
            dispositions.append({'post_id': row['post_id'], 'image_status': row['image']['status'],
                'text_assessed': bool(row['text'].strip()),
                'confirmed_copy_matches': sum(e['status'] == 'confirmed' for e in matches),
                'candidate_matches': sum(e['status'] == 'candidate' for e in matches),
                'decision': 'copy_found' if any(e['status'] == 'confirmed' for e in matches) else
                            'review_matches' if matches else 'not_assessed' if row['image']['status'] != 'ok'
                            else 'no_match_found'})
        report = {'audit_id': plan['audit_id'], 'inventory_id': plan['inventory_id'], 'version': VERSION,
            'coverage': {pool: {'posts': sum(r['pool'] == pool for r in rows),
                'images': dict(Counter(r['image']['status'] for r in rows if r['pool'] == pool)),
                'in_release': sum(r['in_release'] for r in rows if r['pool'] == pool)}
                for pool in ('legacy', 'prior', 'fresh')},
            'text_coverage': text_coverage, 'known_family_retrieval': diagnostics,
            'pair_statuses': dict(Counter(e['status'] for e in new_edges)),
            'pair_methods': dict(Counter(m for e in new_edges for m in {v['method'] for v in e['evidence']})),
            'paid_model_calls': 0, 'model_cost_usd': 0,
            'dispositions': dispositions, 'edges': ordered,
            'limitations': ['Similarity scores are retrieval heuristics, not duplicate probabilities.',
                'Prior pilot candidates are unpublished legacy comparison records; they do not enter release membership.',
                'Baseline full/trim image retrieval is ranked to top five per pool. Crop matching runs only on the top 20 coarse full/trim candidates per pool.',
                'Crop and semantic matches remain candidates; no automatic joke-family adjudication occurs.',
                'No match found never means proven unique. Missing or animated images and absent text remain unassessed.',
                'Fresh text uses sampled comments; archive text uses stored explanations.',
                'Known-family labels are copied from the supplied file without inferred family labels.']}
        write_json(output / 'report.json', report)
        write_json(result_manifest, {p.name: file_hash(p) for p in
            [output / 'report.json', output / 'text_vectors.npy', output / 'text_packing.json'] if p.exists()})
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--database', type=Path, default=Path('data/basedbench.db'))
    prep.add_argument('--inventory', type=Path, required=True)
    prep.add_argument('--prior-inventory', type=Path, action='append', default=[])
    prep.add_argument('--families', type=Path, default=Path('data/curation/feedback/known-review-families-v1.json'))
    prep.add_argument('--output', type=Path, required=True)
    execute = commands.add_parser('run')
    execute.add_argument('--output', type=Path, required=True)
    execute.add_argument('--model-cache', type=Path, default=Path('data/curation/models'))
    args = parser.parse_args()
    result = (prepare(args.database, args.inventory, args.output, args.families,
                      prior_inventories=args.prior_inventory) if args.command == 'prepare'
              else run(args.output, args.model_cache))
    print(json.dumps({'audit_id': result['audit_id']} if args.command == 'prepare' else
                      {k: v for k, v in result.items() if k not in {'edges', 'dispositions'}}, indent=2))


if __name__ == '__main__':
    main()
