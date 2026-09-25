"""Read-only duplicate evidence for a frozen pilot; never changes admission labels.

Exact byte/pixel identity establishes a copy, not a preferred representative.
Image/text similarity retrieves candidates, not confirmed joke families.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sqlite3

from PIL import Image, ImageChops, ImageOps, ImageStat

from basedbench.pipeline import curation_encoder, duplicates
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json

VERSION = 'duplicate-audit-v1'
PARAMETERS = {'image_dhash_max': 8, 'image_ahash_max': 8, 'image_top_k_per_pool': 5,
              'tfidf_min': .35, 'minilm_min': .65, 'text_top_k_per_pool': 5,
              'thumbnail_size': 128, 'border_tolerance': 20, 'fresh_comment_limit': 5}


def trim_border(image: Image.Image) -> tuple[Image.Image, list[int]]:
    """Remove only uniform outer rows/columns; never assert cropped identity."""
    # A corner color is a retrieval aid, not evidence that discarded text is irrelevant.
    small = image.copy()
    small.thumbnail((1024, 1024))
    diff = ImageChops.difference(small, Image.new('RGB', small.size, small.getpixel((0, 0))))
    channels = diff.split()
    maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
    box = maximum.point(lambda p: 255 if p > PARAMETERS['border_tolerance'] else 0).getbbox()
    if not box:
        return image, [0, 0, *image.size]
    box = [round(v * image.size[i % 2] / small.size[i % 2]) for i, v in enumerate(box)]
    if box[2] - box[0] < 16 or box[3] - box[1] < 16:
        return image, [0, 0, *image.size]
    return image.crop(box), box


def fingerprint(path: Path | None, output: Path) -> dict:
    if path is None or not path.is_file():
        return {'status': 'missing', 'variants': []}
    raw_hash = file_hash(path)
    try:
        with Image.open(path) as raw:
            frames = getattr(raw, 'n_frames', 1)
            if frames != 1:
                return {'status': 'unsupported_animation', 'sha256': raw_hash, 'variants': []}
            # RGBA identity preserves transparent pixels and alpha; RGB is only for retrieval.
            rgba = ImageOps.exif_transpose(raw).convert('RGBA')
            pixel_hash = hashlib.sha256(str(rgba.size).encode() + rgba.tobytes()).hexdigest()
            image = Image.new('RGBA', rgba.size, 'white')
            image.alpha_composite(rgba)
            image = image.convert('RGB')
        cropped, box = trim_border(image)
        variants = []
        for name, view, crop in [('full', image, [0, 0, *image.size]), ('trim', cropped, box)]:
            if name == 'trim' and crop == [0, 0, *image.size]:
                continue
            thumb = view.resize((PARAMETERS['thumbnail_size'],) * 2, Image.Resampling.LANCZOS)
            thumb_path = output / 'thumbs' / f'{raw_hash}-{name}.png'
            thumb_path.parent.mkdir(exist_ok=True)
            thumb.save(thumb_path)
            variants.append({'name': name, 'crop': crop, 'width': view.width, 'height': view.height,
                             'dhash': duplicates._dhash(view), 'ahash': duplicates._ahash(view),
                             'thumbnail': str(thumb_path.relative_to(output))})
        return {'status': 'ok', 'sha256': raw_hash, 'pixel_sha256': pixel_hash, 'variants': variants}
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        return {'status': 'decode_error', 'sha256': raw_hash, 'error': type(exc).__name__, 'variants': []}


def evidence_text(candidate: dict) -> tuple[str, list[str]]:
    comments = candidate.get('comment_retrieval', {}).get('comments', [])
    selected = sorted((c for c in comments if len(c['body'].strip()) >= 40
                       and not c.get('is_moderator')), key=lambda c: (-c.get('score', 0), c['comment_id']))[:5]
    return '\n\n'.join(c['body'] for c in selected), [c['comment_id'] for c in selected]


def prepare(database: Path, inventory: Path, output: Path, known_families: Path) -> dict:
    if output.exists():
        raise FileExistsError('Use a new directory; frozen audits are not overwritten')
    manifest = json.loads((inventory / 'manifest.json').read_text())
    for name, expected in manifest['files'].items():
        if file_hash(inventory / name) != expected:
            raise ValueError(f'Inventory changed: {name}')
    baseline = json.loads((inventory / 'baseline.json').read_text())
    release = set(baseline['release_ids'])
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        archive = [dict(r) for r in db.execute('''SELECT m.post_id, m.title, m.local_image_path,
            m.permalink, g.explanation, r.status AS review_status FROM memes m
            LEFT JOIN ground_truths g USING(post_id) LEFT JOIN reviews r USING(post_id)
            ORDER BY m.post_id''')]
    if {r['post_id'] for r in archive} != {r['post_id'] for r in baseline['posts']}:
        raise ValueError('Archive membership changed since inventory freeze')
    candidates = json.loads((inventory / 'candidates.json').read_text())
    rows = []
    output.mkdir(parents=True)
    for item in archive:
        rows.append({'post_id': item['post_id'], 'pool': 'legacy', 'in_release': item['post_id'] in release,
                     'title': item['title'], 'image_path': item['local_image_path'],
                     'text': item['explanation'] or '', 'text_source': 'stored_explanation',
                     'review_status': item['review_status']})
    for item in candidates:
        text, ids = evidence_text(item)
        relative = item['image'].get('path') if item['image']['status'] == 'available' else None
        rows.append({'post_id': item['post_id'], 'pool': 'fresh', 'in_release': False,
                     'title': item['title'], 'image_path': str(inventory / relative) if relative else None,
                     'expected_sha256': item['image'].get('sha256'), 'text': text,
                     'text_source': 'top_five_substantive_comments', 'comment_ids': ids, 'review_status': None})
    if len({r['post_id'] for r in rows}) != len(rows):
        raise ValueError('Fresh and legacy IDs overlap')
    for index, row in enumerate(rows):
        path = Path(row['image_path']).resolve() if row['image_path'] else None
        row['image_path'] = str(path) if path else None
        row['image'] = fingerprint(path, output)
        if row.get('expected_sha256') and row['image'].get('sha256') != row['expected_sha256']:
            raise ValueError(f"Image changed: {row['post_id']}")
        if index % 500 == 0:
            print(f'Fingerprinted {index}/{len(rows)}', flush=True)
    known = json.loads(known_families.read_text())
    if any(pid not in {r['post_id'] for r in rows} for family in known for pid in family):
        raise ValueError('Unknown family member')
    write_json(output / 'inputs.json', rows)
    write_json(output / 'known_families.json', known)
    plan = {'version': VERSION, 'parameters': PARAMETERS, 'inventory_id': manifest['inventory_id'],
            'source_files': {str(p): file_hash(p) for p in [database, known_families, inventory / 'manifest.json']},
            'code': {str(Path(p).resolve()): file_hash(Path(p)) for p in
                     [__file__, duplicates.__file__, curation_encoder.__file__]},
            'model': curation_encoder.MODEL_NAME, 'revision': curation_encoder.MODEL_REVISION,
            'paid_model_calls': 0, 'model_cost_usd': 0,
            'versions': {n: importlib.metadata.version(n) for n in
                         ['pillow', 'numpy', 'scikit-learn', 'sentence-transformers', 'torch']},
            'files': {str(p.relative_to(output)): file_hash(p) for p in sorted(output.rglob('*')) if p.is_file()}}
    plan['audit_id'] = digest(plan)
    write_json(output / 'plan.json', plan)
    return plan


def verify(output: Path) -> dict:
    plan = json.loads((output / 'plan.json').read_text())
    if plan['version'] != VERSION or plan['parameters'] != PARAMETERS:
        raise ValueError('Audit configuration changed')
    for name, expected in plan['code'].items():
        if file_hash(Path(name)) != expected:
            raise ValueError('Audit code changed; use a new frozen run')
    for name, expected in plan['files'].items():
        if file_hash(output / name) != expected:
            raise ValueError(f'Audit input changed: {name}')
    if digest({k: v for k, v in plan.items() if k != 'audit_id'}) != plan['audit_id']:
        raise ValueError('Audit plan changed')
    return plan


def exact_kind(left: dict, right: dict) -> str | None:
    for key, name in [('sha256', 'exact_bytes'), ('pixel_sha256', 'exact_pixels')]:
        if left.get(key) and left[key] == right.get(key):
            return name
    return None


def image_evidence(left: dict, right: dict, output: Path, cache: dict) -> dict | None:
    best = None
    for a in left['variants']:
        for b in right['variants']:
            dh = duplicates.hamming_distance(a['dhash'], b['dhash'])
            ah = duplicates.hamming_distance(a['ahash'], b['ahash'])
            if dh > PARAMETERS['image_dhash_max'] or ah > PARAMETERS['image_ahash_max']:
                continue
            for v in (a, b):
                if v['thumbnail'] not in cache:
                    with Image.open(output / v['thumbnail']) as im:
                        cache[v['thumbnail']] = im.convert('RGB').copy()
            delta = sum(ImageStat.Stat(ImageChops.difference(cache[a['thumbnail']], cache[b['thumbnail']])).mean) / 3
            evidence = {'method': 'near_image', 'dhash_distance': dh, 'ahash_distance': ah,
                        'pixel_difference': round(delta, 4), 'left_view': a['name'], 'right_view': b['name'],
                        'left_crop': a['crop'], 'right_crop': b['crop']}
            if best is None or (delta, dh + ah) < (best['pixel_difference'], best['dhash_distance'] + best['ahash_distance']):
                best = evidence
    return best


def split_audit(assignments: dict[str, str], edges: list[dict]) -> dict:
    """Hold unresolved cross-split links; union only confirmed copy/family edges.

    Connected confirmed families are indivisible even through unassigned members.
    Pending similarity is a hold for adjudication, not a semantic union.
    """
    parents = {p: p for e in edges for p in (e['left'], e['right'])}
    def root(p):
        while parents[p] != p:
            parents[p] = parents[parents[p]]
            p = parents[p]
        return p
    for edge in edges:
        if edge['status'] == 'confirmed':
            a, b = sorted((root(edge['left']), root(edge['right'])))
            parents[b] = a
    members = defaultdict(list)
    for p in parents:
        members[root(p)].append(p)
    splits = {g: sorted({assignments[p] for p in group if p in assignments}) for g, group in members.items()}
    violations = [sorted(group) for g, group in members.items() if len(splits[g]) > 1]
    pending = [e for e in edges if e['status'] == 'candidate'
               and len(set(splits[root(e['left'])] + splits[root(e['right'])])) > 1]
    return {'confirmed_families': sorted(sorted(g) for g in members.values() if len(g) > 1),
            'cross_split_confirmed': violations, 'cross_split_pending': pending,
            'assigned_posts': len(assignments),
            'ready': (not violations and not pending) if assignments else None,
            'scope': 'Only recorded links; absence of a match does not prove family independence.'}


def text_neighbors(rows: list[dict], query_ids: set[str], output: Path, model_cache: Path) -> tuple[list[dict], dict]:
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer
    from sklearn.feature_extraction.text import TfidfVectorizer
    selected = [r for r in rows if r['text'].strip()]
    if not selected:
        return [], {'with_text': 0}
    tfidf = TfidfVectorizer(stop_words='english', ngram_range=(1, 2), sublinear_tf=True)
    lexical = tfidf.fit_transform([r['text'] for r in selected])
    torch.set_num_threads(4)
    torch.manual_seed(0)
    encoder = SentenceTransformer(curation_encoder.MODEL_NAME, revision=curation_encoder.MODEL_REVISION,
        cache_folder=str(model_cache), local_files_only=True, device='cpu', token=False,
        trust_remote_code=False, model_kwargs={'use_safetensors': True})
    if encoder.max_seq_length != 256 or encoder[0].auto_model.config.model_type != 'bert':
        raise ValueError('Unexpected encoder packing')
    features, packing = curation_encoder.encode_evidence(
        [{'explanation': r['text'], 'comment_evidence': ''} for r in selected], encoder)
    features = features[:, :features.shape[1] // 2]
    np.save(output / 'text_vectors.npy', features)
    write_json(output / 'text_packing.json', [{'post_id': r['post_id'], **p['explanation']}
                                            for r, p in zip(selected, packing, strict=True)])
    indices = [i for i, r in enumerate(selected) if r['post_id'] in query_ids]
    scores = {'tfidf': (lexical[indices] @ lexical.T).toarray(), 'minilm': features[indices] @ features.T}
    edges = []
    for name, matrix in scores.items():
        for qi, i in enumerate(indices):
            for pool in ('legacy', 'fresh'):
                choices = [j for j, r in enumerate(selected) if j != i and r['pool'] == pool
                           and float(matrix[qi, j]) >= PARAMETERS[name + '_min']]
                for j in sorted(choices, key=lambda j: (-float(matrix[qi, j]), selected[j]['post_id']))[:PARAMETERS['text_top_k_per_pool']]:
                    edges.append({'left': selected[i]['post_id'], 'right': selected[j]['post_id'],
                                  'method': name, 'score': round(float(matrix[qi, j]), 6)})
    return edges, {'with_text': len(selected), 'by_pool': dict(Counter(r['pool'] for r in selected)),
                   'tokens': sum(p['explanation']['tokens'] for p in packing), 'omitted_tokens': 0}


def run(output: Path, model_cache: Path) -> dict:
    plan = verify(output)
    rows = json.loads((output / 'inputs.json').read_text())
    known = json.loads((output / 'known_families.json').read_text())
    queries = {r['post_id'] for r in rows if r['pool'] == 'fresh'} | {p for group in known for p in group}
    by_id = {r['post_id']: r for r in rows}
    edges = {}
    def add(left, right, evidence, confirmed=False):
        key = tuple(sorted((left, right)))
        if left > right and evidence['method'] == 'near_image':
            evidence = dict(evidence)
            for field in ('view', 'crop'):
                evidence['left_' + field], evidence['right_' + field] = (
                    evidence['right_' + field], evidence['left_' + field])
        if key not in edges:
            edges[key] = {'left': key[0], 'right': key[1], 'status': 'candidate', 'evidence': [],
                          'release_members': [p for p in key if by_id[p]['in_release']],
                          'scope': 'fresh' if any(by_id[p]['pool'] == 'fresh' for p in key) else 'diagnostic'}
        if evidence not in edges[key]['evidence']:
            edges[key]['evidence'].append(evidence)
        if confirmed:
            edges[key]['status'] = 'confirmed'
    cache = {}
    for row in rows:
        if row['post_id'] not in queries:
            continue
        near = defaultdict(list)
        for other in rows:
            if row['post_id'] == other['post_id']:
                continue
            kind = exact_kind(row['image'], other['image'])
            if kind:
                add(row['post_id'], other['post_id'], {'method': kind}, True)
                continue
            evidence = image_evidence(row['image'], other['image'], output, cache)
            if evidence:
                evidence['query_id'] = row['post_id']
                near[other['pool']].append((other['post_id'], evidence))
        for choices in near.values():
            choices.sort(key=lambda p: (p[1]['pixel_difference'], p[1]['dhash_distance'] + p[1]['ahash_distance'], p[0]))
            for pid, evidence in choices[:PARAMETERS['image_top_k_per_pool']]:
                add(row['post_id'], pid, evidence)
    print('Image retrieval complete; encoding text locally', flush=True)
    text_edges, text_coverage = text_neighbors(rows, queries, output, model_cache)
    for edge in text_edges:
        add(edge['left'], edge['right'], {'method': edge['method'], 'score': edge['score'], 'query_id': edge['left']})
    # Evaluate retrieval BEFORE adding explicit known families.
    diagnostics = []
    for group in known:
        for a in group:
            for b in group:
                if a >= b:
                    continue
                edge = edges.get((a, b))
                diagnostics.append({'left': a, 'right': b, 'retrieved': bool(edge),
                                    'methods': sorted({e['method'] for e in edge['evidence']}) if edge else []})
                add(a, b, {'method': 'previously_reviewed_family'}, True)
    ordered = [edges[k] for k in sorted(edges)]
    fresh = [e for e in ordered if e['scope'] == 'fresh']
    dispositions = []
    for row in rows:
        if row['pool'] != 'fresh':
            continue
        matches = [e for e in fresh if row['post_id'] in (e['left'], e['right'])]
        dispositions.append({'post_id': row['post_id'], 'image_status': row['image']['status'],
            'text_assessed': bool(row['text'].strip()),
            'confirmed_copy_matches': sum(e['status'] == 'confirmed' for e in matches),
            'candidate_matches': sum(e['status'] == 'candidate' for e in matches),
            'decision': 'copy_found' if any(e['status'] == 'confirmed' for e in matches) else
                        'review_matches' if matches else 'not_assessed' if row['image']['status'] != 'ok' else 'no_match_found'})
    report = {'audit_id': plan['audit_id'], 'version': VERSION, 'coverage': {
        pool: {'posts': sum(r['pool'] == pool for r in rows),
               'images': dict(Counter(r['image']['status'] for r in rows if r['pool'] == pool)),
               'in_release': sum(r['in_release'] for r in rows if r['pool'] == pool)} for pool in ('legacy', 'fresh')},
        'text_coverage': text_coverage, 'known_family_retrieval': diagnostics,
        'fresh_pair_statuses': dict(Counter(e['status'] for e in fresh)),
        'fresh_pair_methods': dict(Counter(m for e in fresh for m in {v['method'] for v in e['evidence']})),
        'dispositions': dispositions, 'edges': ordered, 'split_constraints': split_audit({}, ordered),
        'limitations': ['Similarity scores are retrieval heuristics, not duplicate probabilities.',
            'No admission changes or keeper selection; a rejected legacy copy is not a release duplicate.',
            'Top-five retrieval can miss families. No match found never means proven unique.',
            'Fresh text uses sampled comments; legacy text uses potentially defective stored answers.',
            'Shared template/topic is not sufficient to establish the same joke.',
            'Missing/animated images and missing text remain coverage gaps.',
            'Only fresh and six diagnostic queries are searched; this is not an all-archive family audit.']}
    write_json(output / 'report.json', report)
    write_json(output / 'results-manifest.json', {p.name: file_hash(p) for p in
               [output / 'report.json', output / 'text_vectors.npy', output / 'text_packing.json'] if p.exists()})
    return {k: v for k, v in report.items() if k not in {'edges', 'dispositions', 'split_constraints'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--database', type=Path, default=Path('data/basedbench.db'))
    prep.add_argument('--inventory', type=Path, required=True)
    prep.add_argument('--families', type=Path, default=Path('data/curation/feedback/known-review-families-v1.json'))
    prep.add_argument('--output', type=Path, required=True)
    audit = sub.add_parser('run')
    audit.add_argument('--output', type=Path, required=True)
    audit.add_argument('--model-cache', type=Path, default=Path('data/curation/models'))
    args = parser.parse_args()
    result = prepare(args.database, args.inventory, args.output, args.families) if args.command == 'prepare' else run(args.output, args.model_cache)
    print(json.dumps(result if args.command == 'run' else {'audit_id': result['audit_id']}, indent=2))


if __name__ == '__main__':
    main()
