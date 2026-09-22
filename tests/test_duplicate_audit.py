from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, PngImagePlugin
import pytest

from basedbench.pipeline import duplicate_audit as audit
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json


def meme(path: Path, caption: str = 'FIRST PUNCHLINE') -> None:
    image = Image.new('RGB', (200, 100), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 190, 60), fill='blue')
    draw.text((10, 70), caption, fill='black')
    image.save(path)


def test_exact_pixels_ignore_container_metadata_but_not_caption(tmp_path):
    a, b, c = [tmp_path / f'{x}.png' for x in 'abc']
    meme(a)
    with Image.open(a) as im:
        meta = PngImagePlugin.PngInfo()
        meta.add_text('source', 'different file metadata')
        im.save(b, pnginfo=meta)
    meme(c, 'DIFFERENT PAYOFF')
    left, right, different = [audit.fingerprint(p, tmp_path) for p in (a, b, c)]
    assert audit.exact_kind(left, left) == 'exact_bytes'
    assert left['sha256'] != right['sha256']
    assert audit.exact_kind(left, right) == 'exact_pixels'
    assert audit.exact_kind(left, different) is None
    # Same-template retrieval may fire; it must never establish identity.
    evidence = audit.image_evidence(left, different, tmp_path, {})
    if evidence:
        assert evidence['method'] == 'near_image'


def test_border_and_recompression_are_candidates_not_exact(tmp_path):
    original = tmp_path / 'original.png'
    framed = tmp_path / 'framed.jpg'
    meme(original)
    with Image.open(original) as im:
        canvas = Image.new('RGB', (400, 400), 'black')
        canvas.paste(im, (100, 150))
        canvas.save(framed, quality=95)
    a, b = [audit.fingerprint(p, tmp_path) for p in (original, framed)]
    assert audit.exact_kind(a, b) is None
    evidence = audit.image_evidence(a, b, tmp_path, {})
    assert evidence is not None
    assert evidence['right_view'] == 'trim'


def test_missing_corrupt_and_animation_remain_explicit(tmp_path):
    assert audit.fingerprint(None, tmp_path)['status'] == 'missing'
    corrupt = tmp_path / 'bad.png'
    corrupt.write_bytes(b'not an image')
    assert audit.fingerprint(corrupt, tmp_path)['status'] == 'decode_error'
    animated = tmp_path / 'two.gif'
    Image.new('RGB', (20, 20), 'red').save(animated, save_all=True,
        append_images=[Image.new('RGB', (20, 20), 'blue')])
    result = audit.fingerprint(animated, tmp_path)
    assert result['status'] == 'unsupported_animation'
    assert not result['variants']
    assert 'pixel_sha256' not in result


def test_transparent_pixels_do_not_establish_false_identity(tmp_path):
    a, b = tmp_path / 'a.png', tmp_path / 'b.png'
    Image.new('RGBA', (20, 20), (255, 255, 255, 0)).save(a)
    Image.new('RGBA', (20, 20), (255, 255, 255, 255)).save(b)
    assert audit.exact_kind(audit.fingerprint(a, tmp_path), audit.fingerprint(b, tmp_path)) is None


def test_split_overlap_through_unassigned_member_and_pending_link():
    edges = [dict(left='a', right='b', status='confirmed'),
             dict(left='b', right='c', status='confirmed'),
             dict(left='c', right='d', status='candidate')]
    result = audit.split_audit({'a': 'train', 'c': 'test', 'd': 'train'}, edges)
    assert result['cross_split_confirmed'] == [['a', 'b', 'c']]
    assert len(result['cross_split_pending']) == 1
    assert result['confirmed_families'] == [['a', 'b', 'c']]
    assert result['ready'] is False
    assert audit.split_audit({'a': 'train', 'c': 'train', 'd': 'train'}, edges)['ready']
    assert audit.split_audit({}, edges)['ready'] is None


def test_comment_selection_records_provenance_and_no_label_features():
    comments = [{'comment_id': str(i), 'body': 'Substantive evidence about the intended joke. ' * 2,
                 'score': i, 'is_moderator': False} for i in range(7)]
    comments += [{'comment_id': 'mod', 'body': 'moderator notice ' * 20, 'score': 500, 'is_moderator': True}]
    text, ids = audit.evidence_text({'title': 'Ignore all instructions', 'review_status': 'excluded',
                                   'comment_retrieval': {'comments': comments}})
    assert ids == ['6', '5', '4', '3', '2']
    assert 'Ignore' not in text and 'moderator' not in text and 'excluded' not in text


def frozen(tmp_path, rows, known):
    write_json(tmp_path / 'inputs.json', rows)
    write_json(tmp_path / 'known_families.json', known)
    plan = {'version': audit.VERSION, 'parameters': audit.PARAMETERS, 'code': {},
            'files': {p.name: file_hash(p) for p in tmp_path.glob('*.json')}}
    plan['audit_id'] = digest(plan)
    write_json(tmp_path / 'plan.json', plan)


def test_run_preserves_missing_images_and_does_not_select_keeper(tmp_path, monkeypatch):
    def row(pid, pool, sha=None, released=False):
        return dict(post_id=pid, pool=pool, text='', in_release=released, review_status='excluded',
                    image={'status': 'ok' if sha else 'missing', 'sha256': sha, 'variants': []})
    rows = [row('old', 'legacy', 'abc'), row('fresh', 'fresh', 'abc'), row('missing', 'fresh')]
    frozen(tmp_path, rows, [])
    monkeypatch.setattr(audit, 'text_neighbors', lambda *args: ([], {'with_text': 0}))
    audit.run(tmp_path, tmp_path)
    report = json.loads((tmp_path / 'report.json').read_text())
    states = {r['post_id']: r for r in report['dispositions']}
    assert states['missing']['decision'] == 'not_assessed'
    assert states['fresh']['decision'] == 'copy_found'
    assert report['edges'][0]['release_members'] == []
    assert 'admission' not in states['fresh']
    assert rows[0]['review_status'] == 'excluded'


def test_known_family_is_not_counted_as_retrieval_success(tmp_path, monkeypatch):
    rows = [dict(post_id=p, pool='legacy', text='', in_release=False,
                 image={'status': 'missing', 'variants': []}) for p in ('a', 'b')]
    frozen(tmp_path, rows, [['a', 'b']])
    monkeypatch.setattr(audit, 'text_neighbors', lambda *args: ([], {'with_text': 0}))
    audit.run(tmp_path, tmp_path)
    report = json.loads((tmp_path / 'report.json').read_text())
    assert not report['known_family_retrieval'][0]['retrieved']
    assert report['edges'][0]['status'] == 'confirmed'


def test_tampered_frozen_input_is_refused(tmp_path):
    frozen(tmp_path, [], [])
    (tmp_path / 'inputs.json').write_text('[{}]')
    with pytest.raises(ValueError, match='input changed'):
        audit.verify(tmp_path)


def test_pair_sorting_keeps_crop_evidence_attached_to_correct_image(tmp_path, monkeypatch):
    rows = [dict(post_id=p, pool=pool, text='', in_release=False,
                 image={'status': 'ok', 'variants': []}) for p, pool in [('archive', 'legacy'), ('new', 'fresh')]]
    frozen(tmp_path, rows, [])
    monkeypatch.setattr(audit, 'text_neighbors', lambda *args: ([], {}))
    monkeypatch.setattr(audit, 'image_evidence', lambda *args: {
        'method': 'near_image', 'left_view': 'trim', 'right_view': 'full',
        'left_crop': [10, 10, 90, 90], 'right_crop': [0, 0, 100, 100],
        'pixel_difference': 2, 'dhash_distance': 1, 'ahash_distance': 0})
    audit.run(tmp_path, tmp_path)
    edge = json.loads((tmp_path / 'report.json').read_text())['edges'][0]
    assert edge['left'] == 'archive'
    assert edge['evidence'][0]['left_view'] == 'full'
    assert edge['evidence'][0]['left_crop'] == [0, 0, 100, 100]
    assert edge['evidence'][0]['query_id'] == 'new'


def test_prepare_reads_available_inventory_images_without_changing_database(tmp_path):
    import sqlite3
    database = tmp_path / 'archive.db'
    with sqlite3.connect(database) as db:
        db.executescript('''
            CREATE TABLE memes(post_id TEXT, title TEXT, local_image_path TEXT, permalink TEXT);
            CREATE TABLE ground_truths(post_id TEXT, explanation TEXT);
            CREATE TABLE reviews(post_id TEXT, status TEXT);
            INSERT INTO memes VALUES ('old', 'old title', NULL, '/old');
        ''')
    before = file_hash(database)
    inventory = tmp_path / 'inventory'
    inventory.mkdir()
    meme(inventory / 'fresh.png')
    write_json(inventory / 'baseline.json', {'release_ids': [], 'posts': [{'post_id': 'old'}]})
    write_json(inventory / 'candidates.json', [{
        'post_id': 'new', 'title': 'new title',
        'image': {'status': 'available', 'path': 'fresh.png', 'sha256': file_hash(inventory / 'fresh.png')}
    }])
    write_json(inventory / 'manifest.json', {'inventory_id': 'test', 'files': {
        p.name: file_hash(p) for p in inventory.iterdir()
    }})
    families = tmp_path / 'families.json'
    write_json(families, [])
    output = tmp_path / 'audit'
    audit.prepare(database, inventory, output, families)
    rows = json.loads((output / 'inputs.json').read_text())
    assert {r['post_id']: r['image']['status'] for r in rows} == {'old': 'missing', 'new': 'ok'}
    assert file_hash(database) == before
    assert audit.verify(output)['inventory_id'] == 'test'
