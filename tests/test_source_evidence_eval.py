"""Mocked contract checks for the frozen source-evidence replay."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from PIL import Image
import pytest

from basedbench.pipeline import source_evidence_eval as evidence
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json


def _case(image: Path, index: int = 0) -> dict:
    input_value = {'explanation': 'The sign says the opposite of the image.',
                   'comment_evidence': 'ID: c1 | Score: 1\nThe sign reverses the pictured scene.',
                   'image_sha256': file_hash(image)}
    sha = digest(input_value)
    return {'case_id': f'p{index}-{sha[:16]}', 'post_id': f'p{index}', 'input': input_value,
            'input_sha256': sha, 'image_path': str(image), 'image_error': None,
            'group_id': f'g{index}', 'human': {'quality': 'repair',
            'events': [{'note': 'secret human defect; never send this to the model'}]},
            'provenance': {'label_source': 'secret-label-file.json'}}


def _source(post_id='p0', status='accessible'):
    return {'source_id': 's1', 'post_ids': [post_id], 'url': 'https://example.org/source',
            'source_type': 'original', 'access_status': status, 'retrieved_at': '2026-09-24',
            'title': 'Original reference', 'passage': 'This is the documented inversion.',
            'lineage_id': 'l1', 'discovered_from': 'human repair note: secret',
            'limitations': 'One variant only.', 'support_scope': 'The reference inversion.'}


def _fixture(tmp_path, count=1, sources=None, budget=1.0):
    data = tmp_path / 'dataset'
    data.mkdir()
    image = data / 'image.png'
    Image.new('RGB', (24, 24), 'white').save(image)
    cases = [_case(image, index) for index in range(count)]
    write_json(data / 'cases.json', cases)
    write_json(data / 'report.json', {'cases': count})
    write_json(data / 'manifest.json', {'files': {
        'cases.json': file_hash(data / 'cases.json'), 'report.json': file_hash(data / 'report.json')}})
    source_path = tmp_path / 'sources.json'
    write_json(source_path, [_source()] if sources is None else sources)
    output = tmp_path / 'run'
    plan = evidence.prepare(data, source_path, output, budget_usd=budget)
    return output, plan, cases, data, source_path


def _payload(*, basis='comments', comments=None, sources=None, anchor=None,
             answer='pass', status='supported', claim_status='supported'):
    return {'answer_quality': answer, 'evidence_status': status, 'material_defects': [],
            'missing_or_wrong_connection': None, 'reason': 'The intended inversion is established.',
            'essential_claims': [{'claim': 'The sign reverses the scene.', 'status': claim_status,
                'basis': basis, 'image_anchor': anchor, 'comment_ids': comments or [],
                'source_ids': sources or [], 'connection': 'This exact image shows the reversal.'}]}


def _response(payload, *, model=evidence.MODEL, tier='default', usage=None):
    usage = {'input_tokens': 100, 'output_tokens': 80} if usage is None else usage
    body = {'model': model, 'status': 'completed', 'service_tier': tier, 'usage': usage}
    return SimpleNamespace(status='completed', output_text=json.dumps(payload),
                           usage=SimpleNamespace(model_dump=lambda **_: usage),
                           model_dump=lambda **_: body)


def _client(*responses):
    return SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=responses)))


def test_allowlist_frozen_requests_and_adjacent_pairs(tmp_path):
    output, plan, cases, _, _ = _fixture(tmp_path, count=2)
    assert len(plan['jobs']) == 3
    first_two = [job for job in plan['jobs'] if job['case_id'] == cases[0]['case_id']]
    assert [job['arm'] for job in first_two] == list(evidence.ARMS)
    for job in plan['jobs']:
        body = json.loads((output / 'requests' / (job['key'] + '.json')).read_text())
        visible = body['input'][0]['content'][0]['text']
        assert 'secret' not in visible and 'quality' not in visible and 'provenance' not in visible
        assert 'source-evidence' not in visible
        assert body['model'] == evidence.MODEL and body['max_output_tokens'] == 3200
        assert body['input'][0]['content'][1]['detail'] == 'high'
        assert body['service_tier'] == 'default' and body['reasoning']['effort'] == 'medium'
        if job['arm'] == 'original_evidence':
            assert 'external_evidence' not in visible
        else:
            assert 's1' in visible and 'lineage_id' in visible and 'source_type' in visible
            assert 'retrieved_at' in visible and 'discovered_from' not in visible


def test_citations_single_chain_and_image_only_are_allowed():
    basic = {'status': 'completed', 'response': {'model': evidence.MODEL, 'service_tier': 'default'}}
    one_comment = evidence.parse({**basic, 'output_text': json.dumps(_payload(comments=['c1']))},
                                 comment_ids={'c1'}, source_ids=set())
    assert one_comment['verdict'] == 'pass'
    image = evidence.parse({**basic, 'output_text': json.dumps(_payload(basis='image', anchor='The sign at top.'))},
                           comment_ids=set(), source_ids=set())
    assert image['verdict'] == 'pass'
    wrong = evidence.parse({**basic, 'output_text': json.dumps(_payload(basis='external', sources=['s1']))},
                           comment_ids={'c1'}, source_ids=set())
    assert 'error' in wrong


def test_schema_requires_logical_consistency():
    basic = {'status': 'completed', 'response': {'model': evidence.MODEL, 'service_tier': 'default'},
             'output_text': json.dumps(_payload(comments=['c1']))}
    bad = json.loads(basic['output_text'])
    bad['evidence_status'] = 'insufficient'
    assert 'error' in evidence.parse({**basic, 'output_text': json.dumps(bad)},
                                     comment_ids={'c1'}, source_ids=set())
    bad = json.loads(basic['output_text'])
    bad['essential_claims'][0]['basis'] = 'mixed'
    assert 'error' in evidence.parse({**basic, 'output_text': json.dumps(bad)},
                                     comment_ids={'c1'}, source_ids=set())
    bad = json.loads(basic['output_text'])
    bad['essential_claims'][0]['comment_ids'] = []
    assert 'error' in evidence.parse({**basic, 'output_text': json.dumps(bad)},
                                     comment_ids={'c1'}, source_ids=set())
    bad = json.loads(basic['output_text'])
    bad['essential_claims'] = bad['essential_claims'] * 7
    assert 'error' in evidence.parse({**basic, 'output_text': json.dumps(bad)},
                                     comment_ids={'c1'}, source_ids=set())


def test_unavailable_source_and_image_hold_are_retained(tmp_path):
    output, plan, cases, _, _ = _fixture(tmp_path, sources=[_source(status='unavailable')])
    assert len(plan['jobs']) == 1
    assert plan['jobs'][0]['arm'] == 'original_evidence'
    report = asyncio.run(evidence.run(output, client=_client(_response(_payload(comments=['c1'])))))
    assert report['planned_calls'] == 1
    # An unsupported asset remains a case in the frozen denominator.
    other = tmp_path / 'other'
    other.mkdir()
    data = other / 'dataset'
    data.mkdir()
    case = {**cases[0], 'image_error': 'animated_image_unsupported'}
    write_json(data / 'cases.json', [case])
    write_json(data / 'manifest.json', {'files': {'cases.json': file_hash(data / 'cases.json')}})
    write_json(other / 'sources.json', [])
    hold_plan = evidence.prepare(data, other / 'sources.json', other / 'run')
    assert hold_plan['max_calls'] == 0 and case['case_id'] in hold_plan['holds']


def test_failed_prepare_does_not_publish_partial_run(tmp_path):
    _, _, cases, data, source_path = _fixture(tmp_path, count=2)
    cases[1]['input_sha256'] = '0' * 64
    write_json(data / 'cases.json', cases)
    write_json(data / 'manifest.json', {'files': {'cases.json': file_hash(data / 'cases.json'),
                                                 'report.json': file_hash(data / 'report.json')}})
    destination = tmp_path / 'retryable-run'
    with pytest.raises(ValueError, match='Case input hash'):
        evidence.prepare(data, source_path, destination)
    assert not destination.exists()


@pytest.mark.asyncio
async def test_budget_stop_and_replay_without_credentials(tmp_path):
    output, plan, _, _, _ = _fixture(tmp_path, count=4, budget=.3)
    usage = {'input_tokens': 300000, 'output_tokens': 3200}
    api = _client(*[_response(_payload(comments=['c1']), usage=usage) for _ in range(8)])
    report = await evidence.run(output, client=api)
    assert report['stop_reason'] == 'budget_cap'
    assert report['cost']['accounted_usd'] <= .3
    assert api.responses.create.call_count < plan['max_calls']
    assert await evidence.run(output, api_key='') == report
    assert api.responses.create.call_count < plan['max_calls']


@pytest.mark.asyncio
async def test_interrupted_call_reserves_and_never_repeats(tmp_path):
    output, plan, _, _, _ = _fixture(tmp_path)
    api = _client(asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await evidence.run(output, client=api)
    assert list((output / 'calls').glob('*.pending'))
    report = await evidence.run(output, api_key='')
    assert report['stop_reason'] == 'unknown_or_fatal_call'
    assert report['cost']['accounted_usd'] == plan['request_bound_usd']
    assert api.responses.create.call_count == 1


@pytest.mark.asyncio
async def test_malformed_usage_keeps_reservation_and_stops(tmp_path):
    output, plan, _, _, _ = _fixture(tmp_path, count=2)
    api = _client(_response(_payload(comments=['c1']), usage={'input_tokens': True,
                                                               'output_tokens': 80}))
    report = await evidence.run(output, client=api)
    assert report['stop_reason'] == 'unknown_or_fatal_call'
    assert report['cost']['unknown_usage_calls'] == 1
    assert report['cost']['accounted_usd'] == plan['request_bound_usd']
    assert api.responses.create.call_count == 1
    assert await evidence.run(output, api_key='') == report


@pytest.mark.asyncio
async def test_wrong_model_tier_and_fatal_failure_stop(tmp_path):
    for index, response in enumerate((
        _response(_payload(comments=['c1']), model='gpt-5.6-luna'),
        _response(_payload(comments=['c1']), tier='priority'),
        SimpleNamespace(status='failed', output_text='', usage=None,
                        model_dump=lambda **_: {'model': evidence.MODEL, 'status': 'failed',
                                                 'error': {'code': 'insufficient_quota'}}),
    )):
        folder = tmp_path / str(index)
        folder.mkdir()
        output, plan, _, _, _ = _fixture(folder, count=2)
        api = _client(response)
        report = await evidence.run(output, client=api)
        assert report['stop_reason'] == 'unknown_or_fatal_call'
        assert api.responses.create.call_count == 1
        assert report['results'][0]['result'].get('error') or index == 2
        assert report['cost']['accounted_usd'] == plan['request_bound_usd']


@pytest.mark.asyncio
async def test_manifest_tampering_detected_before_replay(tmp_path):
    output, _, _, data, _ = _fixture(tmp_path)
    api = _client(_response(_payload(comments=['c1'])), _response(_payload(basis='external', sources=['s1'])))
    report = await evidence.run(output, client=api)
    assert report['complete'] and report['missing_calls'] == 0
    assert await evidence.run(output, api_key='') == report
    (data / 'cases.json').write_text('[]')
    with pytest.raises(ValueError, match='source input changed'):
        await evidence.run(output, api_key='')
