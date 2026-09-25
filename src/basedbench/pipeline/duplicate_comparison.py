"""Local bordered-copy and explanation retrieval experiment, with no admission writes.

Image retrieval searches a fixed small packet. Text retrieval keeps the original
full text pool and thresholds, replacing only separately supported explanations.
Neither a crop nor a semantic score constitutes copy/family adjudication.
"""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.metadata
import itertools
import json
import math
from pathlib import Path
import shutil
import time

from PIL import Image, ImageChops, ImageOps, ImageStat

from basedbench.pipeline import duplicate_audit as baseline, duplicates, curation_encoder
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json

VERSION = 'duplicate-comparison-v1'
PARAMETERS = {'working_max_side': 512, 'scales': [1.0, .95], 'positions': [0, .5, 1],
              'min_area_fraction': .30, 'hash_max': 8, 'pixel_difference_max': 18,
              'thumbnail_size': 128, 'image_top_k_per_pool': 5, 'minilm_min': .65,
              'text_top_k_per_pool': 5}


def windows(size: tuple[int, int], target_ratio: float):
    """Aspect-matched windows can recover embedded content despite textured borders."""
    width, height = size
    if target_ratio <= 0 or not math.isfinite(target_ratio):
        raise ValueError('Positive finite aspect ratio required')
    seen = set()
    for scale in PARAMETERS['scales']:
        crop_w = min(width, height * target_ratio) * scale
        crop_h = crop_w / target_ratio
        if crop_w * crop_h / (width * height) < PARAMETERS['min_area_fraction']:
            continue
        for fx, fy in itertools.product(PARAMETERS['positions'], repeat=2):
            x, y = round((width - crop_w) * fx), round((height - crop_h) * fy)
            box = (x, y, min(width, x + round(crop_w)), min(height, y + round(crop_h)))
            if box not in seen and min(box[2] - box[0], box[3] - box[1]) >= 16:
                seen.add(box)
                yield box


def load_static(path: Path | None):
    if path is None or not path.is_file():
        return None
    with Image.open(path) as raw:
        if getattr(raw, 'n_frames', 1) != 1:
            return None
        image = ImageOps.exif_transpose(raw).convert('RGBA')
        background = Image.new('RGBA', image.size, 'white')
        background.alpha_composite(image)
        image = background.convert('RGB')
        original_size = image.size
        image.thumbnail((PARAMETERS['working_max_side'],) * 2, Image.Resampling.LANCZOS)
        return image, original_size


def crop_evidence(left, right):
    if left is None or right is None:
        return None
    best = None
    # Each direction matches the full other image; do not compare two tiny patches.
    for swapped, (source, target) in enumerate(((left, right), (right, left))):
        im, source_size = source
        other, target_size = target
        dhash, ahash = duplicates._dhash(other), duplicates._ahash(other)
        thumb = other.resize((PARAMETERS['thumbnail_size'],) * 2, Image.Resampling.LANCZOS)
        for box in windows(im.size, other.width / other.height):
            if box == (0, 0, *im.size):
                continue
            crop = im.crop(box)
            dh = duplicates.hamming_distance(duplicates._dhash(crop), dhash)
            ah = duplicates.hamming_distance(duplicates._ahash(crop), ahash)
            if max(dh, ah) > PARAMETERS['hash_max']:
                continue
            pixels = crop.resize(thumb.size, Image.Resampling.LANCZOS)
            delta = sum(ImageStat.Stat(ImageChops.difference(pixels, thumb)).mean) / 3
            if delta > PARAMETERS['pixel_difference_max']:
                continue
            full_box = [round(v * source_size[i % 2] / im.size[i % 2]) for i, v in enumerate(box)]
            boxes = [full_box, [0, 0, *target_size]]
            if swapped:
                boxes.reverse()
            fraction = crop.width * crop.height / (im.width * im.height)
            evidence = {'method': 'aspect_window', 'dhash_distance': dh, 'ahash_distance': ah,
                        'pixel_difference': round(delta, 4), 'left_crop': boxes[0], 'right_crop': boxes[1],
                        'cropped_area_fraction': round(fraction, 5), 'status': 'candidate'}
            if best is None or (delta, dh + ah, -fraction) < (best['pixel_difference'], best['dhash_distance'] + best['ahash_distance'], -best['cropped_area_fraction']):
                best = evidence
    return best


def code_hashes():
    return {m.__name__: file_hash(Path(m.__file__)) for m in (baseline, duplicates, curation_encoder)} | {VERSION: file_hash(Path(__file__))}


def prepare(audit: Path, controls: Path, explanations: Path, output: Path):
    if output.exists():
        raise FileExistsError('Use a new experiment directory')
    baseline.verify(audit)
    old_report = json.loads((audit / 'report.json').read_text())
    for name, sha in json.loads((audit / 'results-manifest.json').read_text()).items():
        if file_hash(audit / name) != sha:
            raise ValueError('Baseline results changed')
    records = {r['post_id']: r for r in json.loads((audit / 'inputs.json').read_text())}
    supported = json.loads(explanations.read_text())
    if len({r['post_id'] for r in supported}) != len(supported):
        raise ValueError('Explanation comparison needs one answer per post')
    known = json.loads((audit / 'known_families.json').read_text())
    pairs = []
    for group in known:
        for a, b in itertools.combinations(group, 2):
            pairs.append({'left': a, 'right': b, 'relation': 'recorded_family', 'source': 'previously_reviewed_family'})
    for name in ('control-results.json', 'fresh-inspection.json'):
        for item in json.loads((controls / name).read_text())['pairs']:
            pairs.append({k: item[k] for k in ('left', 'right', 'relation', 'note')} | {'source': 'prior_assistant_inspection_not_human_gold'})
    for edge in old_report['edges']:
        if edge['scope'] == 'fresh' and any(e['method'] in {'exact_bytes', 'exact_pixels'} for e in edge['evidence']):
            pairs.append({'left': edge['left'], 'right': edge['right'], 'relation': 'exact_copy', 'source': 'baseline_exact_identity'})
    pairs.append({'left': '1ue5z6v', 'right': '1uczut7', 'relation': 'same_image_content_and_joke',
                  'source': 'pilot_assistant_inspection_not_human_gold', 'note': 'Same photo and caption with broad nonuniform side borders.'})
    ids = {p[k] for p in pairs for k in ('left', 'right')} | {r['post_id'] for r in supported}
    # Fixed deterministic coverage control: the published animated image, if available.
    animated = sorted(r['post_id'] for r in records.values() if r['in_release'] and r['image']['status'] == 'unsupported_animation')
    ids.update(animated)
    (output / 'assets').mkdir(parents=True)
    (output / 'baseline-thumbs').mkdir()
    rows = []
    for pid in sorted(ids):
        row = json.loads(json.dumps(records[pid]))
        row['asset'] = None
        if row['image'].get('sha256'):
            source = Path(row['image_path'])
            if file_hash(source) != row['image']['sha256']:
                raise ValueError('Source asset changed: ' + pid)
            row['asset'] = 'assets/' + row['image']['sha256']
            shutil.copyfile(source, output / row['asset'])
        for variant in row['image']['variants']:
            source = audit / variant['thumbnail']
            target = output / 'baseline-thumbs' / source.name
            shutil.copyfile(source, target)
            variant['thumbnail'] = str(target.relative_to(output))
        rows.append(row)
    write_json(output / 'rows.json', rows)
    write_json(output / 'pair-controls.json', pairs)
    write_json(output / 'supported-explanations.json', supported)
    shutil.copyfile(audit / 'text_vectors.npy', output / 'baseline-vectors.npy')
    text_pool = [{'post_id': r['post_id'], 'pool': r['pool'], 'text': r['text']} for r in records.values() if r['text'].strip()]
    packing = json.loads((audit / 'text_packing.json').read_text())
    if [r['post_id'] for r in text_pool] != [r['post_id'] for r in packing]:
        raise ValueError('Baseline text vector order differs from input identities')
    write_json(output / 'text-pool.json', text_pool)
    write_json(output / 'baseline-edges.json', old_report['edges'])
    plan = {'version': VERSION, 'parameters': PARAMETERS, 'baseline_audit_id': old_report['audit_id'],
            'code_hashes': code_hashes(), 'paid_calls': 0, 'model_cost_usd': 0,
            'selection': 'All prior diagnostic pairs, exact fresh pairs, bordered pair, available inspected supported explanations, and published animation.',
            'text_model': curation_encoder.MODEL_NAME, 'text_revision': curation_encoder.MODEL_REVISION,
            'source_files': {str(p): file_hash(p) for p in [audit / 'plan.json', audit / 'report.json', explanations,
                             controls / 'control-results.json', controls / 'fresh-inspection.json']},
            'versions': {n: importlib.metadata.version(n) for n in ['pillow', 'numpy', 'torch', 'sentence-transformers']},
            'files': {str(p.relative_to(output)): file_hash(p) for p in output.rglob('*') if p.is_file()}}
    plan['experiment_id'] = digest(plan)
    write_json(output / 'plan.json', plan)
    return plan


def text_comparison(output, query_ids, model_cache):
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer
    pool = json.loads((output / 'text-pool.json').read_text())
    vectors = np.load(output / 'baseline-vectors.npy')
    if vectors.shape[0] != len(pool):
        raise ValueError('Baseline vector identities do not align')
    replacements = json.loads((output / 'supported-explanations.json').read_text())
    index = {r['post_id']: i for i, r in enumerate(pool)}
    eligible = [r for r in replacements if r['post_id'] in index]
    if len(eligible) != len(replacements):
        raise ValueError('Replacement lacks a frozen baseline text slot')
    revised = vectors.copy()
    if eligible:
        torch.set_num_threads(4)
        torch.manual_seed(0)
        encoder = SentenceTransformer(curation_encoder.MODEL_NAME, revision=curation_encoder.MODEL_REVISION,
            cache_folder=str(model_cache), local_files_only=True, device='cpu', token=False,
            trust_remote_code=False, model_kwargs={'use_safetensors': True})
        if encoder.max_seq_length != 256 or encoder[0].auto_model.config.model_type != 'bert':
            raise ValueError('Unexpected encoder packing')
        features, packing = curation_encoder.encode_evidence([{'explanation': r['explanation'], 'comment_evidence': ''} for r in eligible], encoder)
        for row, vector in zip(eligible, features[:, :features.shape[1] // 2], strict=True):
            revised[index[row['post_id']]] = vector
        write_json(output / 'replacement-packing.json', packing)
    np.save(output / 'revised-vectors.npy', revised)
    # Same full comparison pool, thresholds and per-pool top five for both arms.
    arms = {}
    for name, matrix in [('comments_or_stored_answers', vectors), ('supported_answers', revised)]:
        hits = set()
        for pid in sorted(query_ids & set(index)):
            i = index[pid]
            scores = matrix @ matrix[i]
            for pool_name in ('fresh', 'legacy'):
                choices = [j for j, r in enumerate(pool) if j != i and r['pool'] == pool_name and scores[j] >= PARAMETERS['minilm_min']]
                for j in sorted(choices, key=lambda j: (-float(scores[j]), pool[j]['post_id']))[:PARAMETERS['text_top_k_per_pool']]:
                    hits.add(tuple(sorted((pid, pool[j]['post_id']))))
        arms[name] = hits
    pair_scores = {}
    for pair in json.loads((output / 'pair-controls.json').read_text()):
        a, b = pair['left'], pair['right']
        key = tuple(sorted((a, b)))
        pair_scores[key] = {name: {'score': round(float(matrix[index[a]] @ matrix[index[b]]), 6) if a in index and b in index else None,
                                  'retrieved': key in arms[name]} for name, matrix in [('comments_or_stored_answers', vectors), ('supported_answers', revised)]}
    return pair_scores, {'full_pool': len(pool), 'replacements': len(eligible), 'queries': len(query_ids & set(index)),
                        'hit_pairs': {name: [list(k) for k in sorted(hits)] for name, hits in arms.items()},
                        'outside_packet_links_are_unadjudicated': True}


def run(output: Path, model_cache: Path):
    start = time.monotonic()
    cpu_start = time.process_time()
    plan = json.loads((output / 'plan.json').read_text())
    if plan['version'] != VERSION or plan['parameters'] != PARAMETERS or plan['code_hashes'] != code_hashes():
        raise ValueError('Configuration changed; prepare a new run')
    if digest({k: v for k, v in plan.items() if k != 'experiment_id'}) != plan['experiment_id']:
        raise ValueError('Plan identity changed')
    for name, sha in plan['files'].items():
        if file_hash(output / name) != sha:
            raise ValueError('Frozen input changed: ' + name)
    rows = json.loads((output / 'rows.json').read_text())
    by_id = {r['post_id']: r for r in rows}
    loaded = {r['post_id']: load_static(output / r['asset']) if r['asset'] else None for r in rows}
    baseline_cache, edges = {}, {}
    for a, b in itertools.combinations(rows, 2):
        key = (a['post_id'], b['post_id'])
        exact = baseline.exact_kind(a['image'], b['image'])
        old = baseline.image_evidence(a['image'], b['image'], output, baseline_cache)
        crop = crop_evidence(loaded[key[0]], loaded[key[1]])
        if exact or old or crop:
            edges[key] = {'left': key[0], 'right': key[1], 'exact': exact, 'baseline_image': old, 'crop': crop,
                          'automatic_status': 'confirmed_copy' if exact else 'candidate',
                          'release_members': [r['post_id'] for r in (a, b) if r['in_release']]}
    # Compare candidate ranking with the same top-five cap; keep exact identity outside the cap.
    retrieved = {name: set() for name in ('baseline_image', 'broader_image')}
    for name in retrieved:
        for row in rows:
            for pool in ('fresh', 'legacy'):
                choices = []
                for key, edge in edges.items():
                    if row['post_id'] not in key:
                        continue
                    other = key[1] if key[0] == row['post_id'] else key[0]
                    if by_id[other]['pool'] != pool:
                        continue
                    if edge['exact']:
                        retrieved[name].add(key)
                        continue
                    options = [edge['baseline_image']] + ([edge['crop']] if name == 'broader_image' else [])
                    options = [e for e in options if e]
                    if options:
                        score = min((e['pixel_difference'], e['dhash_distance'] + e['ahash_distance']) for e in options)
                        choices.append((score, key))
                for _, key in sorted(choices)[:PARAMETERS['image_top_k_per_pool']]:
                    retrieved[name].add(key)
    text_scores, text_summary = text_comparison(output, set(by_id), model_cache)
    old_edges = {tuple(sorted((e['left'], e['right']))): e for e in json.loads((output / 'baseline-edges.json').read_text())}
    results = []
    for pair in json.loads((output / 'pair-controls.json').read_text()):
        key = tuple(sorted((pair['left'], pair['right'])))
        old = old_edges.get(key, {})
        # Explicit reviewed-family edges were added AFTER the baseline retrieval measurement.
        old_methods = sorted({e['method'] for e in old.get('evidence', [])} - {'previously_reviewed_family'})
        results.append({**pair, 'baseline_full_audit_methods': old_methods,
                        'packet_image_retrieval': {name: key in found for name, found in retrieved.items()},
                        'image_evidence': edges.get(key), 'text_comparison': text_scores[key],
                        'release_members': [pid for pid in key if by_id[pid]['in_release']],
                        'relation_is_separate_from_retrieval': True})
    report = {'experiment_id': plan['experiment_id'], 'packet_rows': len(rows),
              'image_statuses': dict(Counter(r['image']['status'] for r in rows)),
              'all_packet_pairs': len(rows) * (len(rows) - 1) // 2,
              'static_image_pairs': sum(loaded[a] is not None and loaded[b] is not None for a, b in itertools.combinations(by_id, 2)),
              'control_pairs': len(results), 'results': results,
              'image_hit_pairs': {name: [list(k) for k in sorted(hits)] for name, hits in retrieved.items()},
              'image_edges': list(edges.values()), 'text': text_summary,
              'paid_model_calls': 0, 'model_cost_usd': 0,
              'wall_seconds': round(time.monotonic() - start, 3), 'cpu_seconds': round(time.process_time() - cpu_start, 3),
              'limitations': ['Selected exposed development packet; no population precision/recall estimate.',
                  'Image ranking is within the packet; text ranking retains the full baseline pool.',
                  'Supported explanations have model and assistant provenance, not human validation.',
                  'Crop matching cannot establish that discarded text is irrelevant.',
                  'Unadjudicated similarities are candidate links; no keeper, split or admission changes.']}
    write_json(output / 'report.json', report)
    write_json(output / 'results-manifest.json', {p.name: file_hash(p) for p in [output / 'report.json', output / 'revised-vectors.npy', output / 'replacement-packing.json'] if p.exists()})
    return {k: v for k, v in report.items() if k not in {'results', 'image_edges', 'image_hit_pairs', 'text'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--audit', type=Path, default=Path('data/backfill/duplicate-audit-v1'))
    prep.add_argument('--controls', type=Path, default=Path('data/backfill/duplicate-controls-v1'))
    prep.add_argument('--explanations', type=Path, required=True)
    prep.add_argument('--output', type=Path, required=True)
    local = sub.add_parser('run')
    local.add_argument('--output', type=Path, required=True)
    local.add_argument('--model-cache', type=Path, default=Path('data/curation/models'))
    args = parser.parse_args()
    values = vars(args)
    command = values.pop('command')
    result = prepare(**values) if command == 'prepare' else run(**values)
    print(json.dumps({k: v for k, v in result.items() if k not in {'files', 'source_files'}}))


if __name__ == '__main__':
    main()
