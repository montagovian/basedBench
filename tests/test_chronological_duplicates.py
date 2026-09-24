from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from PIL import Image, ImageDraw
import pytest

from basedbench.pipeline import chronological_duplicates as audit
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json


def picture(path: Path, caption: str = 'JOKE ONE') -> None:
    image = Image.new('RGB', (180, 110), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 172, 65), fill='navy')
    draw.text((10, 78), caption, fill='black')
    image.save(path)


def make_inventory(path: Path, candidates: list[dict], archive_ids=('old',), releases=()):
    path.mkdir(parents=True, exist_ok=True)
    source_plan = {'version': 'fixture', 'source': path.name}
    inventory_id = digest(source_plan)
    source_plan['inventory_id'] = inventory_id
    write_json(path / 'plan.json', source_plan)
    write_json(path / 'baseline.json', {'posts': [{'post_id': pid} for pid in archive_ids],
                                        'release_ids': list(releases)})
    write_json(path / 'candidates.json', candidates)
    write_json(path / 'selection.json', [r['post_id'] for r in candidates])
    write_json(path / 'manifest.json', {'inventory_id': inventory_id, 'files': {
        p.name: file_hash(p) for p in path.iterdir() if p.name != 'manifest.json'}})


def candidate(pid: str, image: Path | None, *, status='available') -> dict:
    record = {'status': status}
    if image:
        record.update(path=str(image), sha256=file_hash(image))
    return {'post_id': pid, 'title': pid, 'image': record,
            'comment_retrieval': {'comments': []}}


def setup_database(path: Path, *, archive_image='archive.png'):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript('''
            CREATE TABLE memes(post_id TEXT, title TEXT, local_image_path TEXT, permalink TEXT);
            CREATE TABLE ground_truths(post_id TEXT, explanation TEXT);
            CREATE TABLE reviews(post_id TEXT, status TEXT);
        ''')
        db.execute('INSERT INTO memes VALUES (?, ?, ?, ?)', ('old', 'archive', archive_image, '/old'))
        db.execute('INSERT INTO ground_truths VALUES (?, ?)', ('old', 'An archived explanation.'))
        db.execute('INSERT INTO reviews VALUES (?, ?)', ('old', 'excluded'))


def prepare(tmp_path, candidates, prior=(), *, archive_image='archive.png', releases=()):
    database = tmp_path / 'data' / 'archive.db'
    archive_asset = tmp_path / 'archive.png'
    picture(archive_asset)
    setup_database(database, archive_image=archive_image)
    inventory = tmp_path / 'new'
    inventory.mkdir()
    for item in candidates:
        image = item.get('image', {}).get('path')
        if image:
            source = Path(image)
            if source.parent != inventory:
                (inventory / source.name).write_bytes(source.read_bytes())
            item['image']['path'] = source.name
            item['image']['sha256'] = file_hash(inventory / source.name)
    make_inventory(inventory, candidates, releases=releases)
    prior_dirs = []
    for index, items in enumerate(prior):
        directory = tmp_path / f'prior{index}'
        directory.mkdir()
        for item in items:
            image = item.get('image', {}).get('path')
            if image:
                source = Path(image)
                if source.parent != directory:
                    (directory / source.name).write_bytes(source.read_bytes())
                item['image']['path'] = source.name
                item['image']['sha256'] = file_hash(directory / source.name)
        make_inventory(directory, items, archive_ids=('old',), releases=('old',))
        prior_dirs.append(directory)
    known = tmp_path / 'families.json'
    write_json(known, [])
    output = tmp_path / 'audit'
    plan = audit.prepare(database, inventory, output, known, prior_inventories=prior_dirs)
    return output, plan, database


def test_prior_candidates_are_legacy_pool_and_never_release_membership(tmp_path):
    prior_dir = tmp_path / 'prior-assets'
    prior_dir.mkdir()
    prior_image = prior_dir / 'prior.png'
    picture(prior_image)
    prior = candidate('pilot', prior_image)
    new_image = tmp_path / 'new-image.png'
    picture(new_image, 'A DIFFERENT JOKE')
    output, plan, _ = prepare(tmp_path, [candidate('new', new_image)], prior=[[prior]])
    rows = json.loads((output / 'inputs.json').read_text())
    pilot = next(row for row in rows if row['post_id'] == 'pilot')
    assert pilot['pool'] == 'prior'
    assert pilot['in_release'] is False
    assert plan['inventory_id'] == json.loads((tmp_path / 'new' / 'manifest.json').read_text())['inventory_id']
    assert audit.verify(output)['audit_id'] == plan['audit_id']


def test_prior_text_is_included_as_unpublished_legacy_retrieval(monkeypatch, tmp_path):
    seen = {}
    def neighbors(rows, query_ids, output, model_cache):
        seen['prior'] = next(r for r in rows if r['post_id'] == 'pilot')['pool']
        seen['query_ids'] = query_ids
        return [], {'with_text': 2}
    monkeypatch.setattr(audit.baseline, 'text_neighbors', neighbors)
    rows = [{'post_id': 'pilot', 'pool': 'prior', 'text': 'pilot evidence'},
            {'post_id': 'new', 'pool': 'fresh', 'text': 'new evidence'}]
    audit._text_edges(rows, {'new'}, tmp_path, tmp_path / 'cache')
    assert seen == {'prior': 'legacy', 'query_ids': {'new'}}


def test_archive_relative_image_paths_resolve_from_database_parent_parent(tmp_path):
    output, _, _ = prepare(tmp_path, [], archive_image='archive.png')
    row = json.loads((output / 'inputs.json').read_text())[0]
    assert row['image_path'] == str((tmp_path / 'archive.png').resolve())
    assert row['image']['status'] == 'ok'


def test_inventory_manifest_tampering_is_refused(tmp_path):
    image = tmp_path / 'new.png'
    picture(image)
    inventory = tmp_path / 'inventory'
    make_inventory(inventory, [candidate('new', image)])
    (inventory / 'candidates.json').write_text('[]')
    with pytest.raises(ValueError, match='Inventory changed'):
        audit._verify_inventory(inventory)


def test_available_inventory_image_requires_relative_path_and_sha256(tmp_path):
    inventory = tmp_path / 'inventory'
    inventory.mkdir()
    outside = tmp_path / 'outside.png'
    picture(outside)
    with pytest.raises(ValueError, match='Unsafe inventory image path'):
        audit._image_file(inventory, {'post_id': 'new', 'image': {
            'status': 'available', 'path': '../outside.png', 'sha256': file_hash(outside)}})
    with pytest.raises(ValueError, match='no valid SHA256'):
        audit._image_file(inventory, {'post_id': 'new', 'image': {
            'status': 'available', 'path': 'outside.png'}})


def test_new_candidate_dispositions_include_exact_confirmed_and_near_candidate(tmp_path, monkeypatch):
    same = tmp_path / 'same.png'
    near = tmp_path / 'near.png'
    picture(same)
    picture(near, 'JOKE TWO')
    output, _, _ = prepare(tmp_path, [candidate('exact', same), candidate('near', near)])
    def image_evidence(left, right, *args):
        if left.get('sha256') != right.get('sha256') and left.get('status') == right.get('status') == 'ok':
            return {'method': 'near_image', 'pixel_difference': 2.0, 'dhash_distance': 1,
                    'ahash_distance': 1, 'left_view': 'full', 'right_view': 'full',
                    'left_crop': [0, 0, 180, 110], 'right_crop': [0, 0, 180, 110]}
        return None
    monkeypatch.setattr(audit.baseline, 'image_evidence', image_evidence)
    monkeypatch.setattr(audit, '_text_edges', lambda *args: ([], {'with_text': 0}))
    report = audit.run(output, tmp_path / 'cache')
    states = {r['post_id']: r for r in report['dispositions']}
    assert states['exact']['decision'] == 'copy_found'
    assert states['near']['decision'] == 'review_matches'
    exact_edge = next(e for e in report['edges'] if {'old', 'exact'} == {e['left'], e['right']})
    assert exact_edge['status'] == 'confirmed'
    assert any(e['status'] == 'candidate' for e in report['edges'])


def test_empty_new_inventory_returns_no_dispositions_and_replays_locally(tmp_path):
    output, _, _ = prepare(tmp_path, [])
    first = audit.run(output, tmp_path / 'missing-cache')
    second = audit.run(output, tmp_path / 'missing-cache')
    assert first['dispositions'] == []
    assert second == first
    assert first['paid_model_calls'] == 0
    assert first['model_cost_usd'] == 0
    assert first['text_coverage']['encoder_loaded'] is False


def test_prior_manifest_tampering_is_refused(tmp_path):
    prior_asset_dir = tmp_path / 'p-assets'
    prior_asset_dir.mkdir()
    prior_image = prior_asset_dir / 'p.png'
    picture(prior_image)
    prior_dir = tmp_path / 'prior'
    prior_dir.mkdir()
    (prior_dir / 'p.png').write_bytes(prior_image.read_bytes())
    item = candidate('pilot', prior_dir / 'p.png')
    make_inventory(prior_dir, [item])
    (prior_dir / 'candidates.json').write_text('[]')
    image = tmp_path / 'new.png'
    picture(image, 'new')
    database = tmp_path / 'data' / 'archive.db'
    archive_asset = tmp_path / 'archive.png'
    picture(archive_asset)
    setup_database(database)
    inventory = tmp_path / 'new-inventory'
    make_inventory(inventory, [candidate('new', image)])
    known = tmp_path / 'families.json'
    write_json(known, [])
    with pytest.raises(ValueError, match='Inventory changed'):
        audit.prepare(database, inventory, tmp_path / 'out', known, prior_inventories=[prior_dir])
