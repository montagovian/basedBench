"""Calibration must not turn preference, assistant opinions or partial votes into gold."""
import json
import threading

import httpx
from PIL import Image
import pytest

from basedbench import calibration_review as review
from basedbench.curation_review import ConflictError, ReviewRequest, make_server
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json


@pytest.fixture
def packet(tmp_path):
    packet = tmp_path / 'packet'
    (packet / 'images').mkdir(parents=True)
    image = packet / 'images' / 'temporary.png'
    Image.new('RGB', (40, 40), 'green').save(image)
    sha = file_hash(image)
    image.rename(image.with_name(sha))
    cases = []
    for pid, answers in [('pair', ['First joke explanation', 'Second joke explanation']), ('single', ['Cached explanation'])]:
        inp = {'image_sha256': sha, 'explanation': answers[0], 'comment_evidence': 'Private source comments',
               'answers': [{'text': t, 'source': 'hidden model identity'} for t in answers]}
        cases.append({'post_id': pid, 'input': inp, 'input_sha256': digest(inp), 'image_mime': 'image/png',
                      'split': 'calibration', 'stratum': 'targeted', 'previous_feedback': [],
                      'historical_human_feedback': {'ready': True}})
    write_json(packet / 'cases.json', cases)
    write_json(packet / 'rubric.json', review.RUBRIC)
    manifest = {'schema_version': 'curation-review-packet-v1', 'purpose': review.VERSION,
                'corpus_id': 'fixture', 'rubric_sha256': digest(review.RUBRIC),
                'files': {p.relative_to(packet).as_posix(): file_hash(p) for p in packet.rglob('*') if p.is_file()}}
    manifest['packet_id'] = digest(manifest)
    write_json(packet / 'manifest.json', manifest)
    return packet


def req(store, **changes):
    return ReviewRequest(**({'request_id': 'one', 'post_id': 'pair', 'packet_id': store.manifest['packet_id'],
                            'input_sha256': store.cases['pair']['input_sha256'],
                            'fields': {'quality_a': 'ready', 'quality_b': 'ready', 'preference': 'b'}} | changes))


def test_sampling_is_reproducible_excludes_families_without_replacement():
    rows = [{'post_id': str(i), 'group_id': str(i // 2)} for i in range(20)]
    selected = review.sample_groups(rows, 5, 'seed', {'0', '1', '2'})
    assert selected == review.sample_groups(list(reversed(rows)), 5, 'seed', {'0', '1', '2'})
    assert len({r['group_id'] for r in selected}) == 5
    assert not {r['group_id'] for r in selected} & {'0', '1', '2'}
    with pytest.raises(ValueError, match='eligible distinct'):
        review.sample_groups(rows, 8, 'seed', {'0', '1', '2'})


def test_family_exclusion_is_transitive_and_title_similarity_is_not_gold():
    records = [{'post_id': p, 'image': {'pixel_sha256': im}, 'text': t, 'text_source': source}
               for p, im, t, source in [('a', 'same', 'one', 'stored_explanation'),
                                        ('b', 'same', 'two', 'stored_explanation'),
                                        ('c', 'third', ' TWO ', 'stored_explanation'),
                                        ('d', 'fourth', 'two', 'title')]]
    g = review.family_groups(records, [{'left': 'c', 'right': 'e'}], [['e', 'f']])
    assert len({g[p] for p in 'abcef'}) == 1
    assert g['d'] != g['a']


def test_catalog_hides_sources_hypotheses_strata_and_old_labels(packet):
    store = review.CalibrationStore(packet)
    text = json.dumps(store.catalog())
    for hidden in ['hidden model identity', 'Private source comments', 'targeted', 'historical_human_feedback']:
        assert hidden not in text
    assert 'First joke explanation' in text
    assert store.events() == []


def test_both_acceptable_and_preference_remain_distinct_across_revisions(packet):
    store = review.CalibrationStore(packet)
    original = file_hash(packet / 'cases.json')
    first = store.append(req(store))['event']
    assert first['fields'] == {'quality_a': 'ready', 'quality_b': 'ready', 'preference': 'b'}
    assert first['purpose'] == 'development_feedback'
    assert store.append(req(store))['event'] == first
    revised = req(store, request_id='revision', base_revision=first['event_id'], fields={'quality_a': 'unclear'})
    store.append(revised)
    restarted = review.CalibrationStore(packet)
    assert len(restarted.events()) == 2
    assert restarted.events()[0] == first
    assert restarted.catalog()['cases'][0]['latest']['fields'] == {'quality_a': 'unclear'}
    assert file_hash(packet / 'cases.json') == original
    with pytest.raises(ConflictError):
        store.append(req(store, request_id='stale'))


def test_reveal_checkpoints_partial_draft_and_rejects_opinion_or_phantom_answer(packet):
    store = review.CalibrationStore(packet)
    opened = store.append(req(store, kind='reveal', reveal='comments', fields={'quality_a': 'unclear'}))
    assert opened['state']['latest'] is None
    assert opened['context'] == {'comments': 'Private source comments'}
    assert opened['event']['fields'] == {'quality_a': 'unclear'}
    assert opened['event']['exposed_before'] == []
    with pytest.raises(ValueError, match='opinions'):
        store.append(req(store, kind='reveal', reveal='opinions'))
    with pytest.raises(ValueError, match='only one answer'):
        store.append(req(store, post_id='single', input_sha256=store.cases['single']['input_sha256']))
    assert len(store.events()) == 1


def test_http_calibration_uses_separate_ui_and_existing_write_boundaries(packet):
    server = make_server(packet, 0, store=review.CalibrationStore(packet), static_dir=review.STATIC)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.server_port}', trust_env=False) as client:
            catalog = client.get('/api/cases').json()
            assert 'Does it get the joke?' in client.get('/').text
            assert 'Both answers are acceptable' in client.get('/').text
            assert client.get('/image/pair').headers['content-type'] == 'image/png'
            assert client.get('/manifest.json').status_code == 404
            body = req(review.CalibrationStore(packet)).model_dump()
            assert client.post('/api/events', json=body).status_code == 403
            headers = {'X-Review-Token': catalog['token']}
            assert client.post('/api/events', json=body, headers=headers | {'Origin': 'https://other.example'}).status_code == 403
            assert client.post('/api/events', json=body, headers=headers).status_code == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
