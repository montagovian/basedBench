"""Source isolation, meaningful validation, bounded repairs, and paid-call replay."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from basedbench.pipeline import connection_eval as ev
from basedbench.pipeline.curation_corpus import file_hash, write_json


def mapping():
    return {'image_setup': 'A clock uses BC.', 'shared_reading': 'The calendar gives away the traveler.',
            'connections': [{'key': 'calendar', 'visible_anchor': 'BC', 'decoding': 'The label comes from the future.', 'evidence_comment_ids': ['c1']}],
            'comment_roles': [{'comment_id': c, 'role': 'substantive_support', 'contribution': 'Explains the calendar anachronism.'} for c in ['c1', 'c2', 'c3']],
            'competing_readings': [], 'task': 'recoverable', 'status': 'supported', 'reason': 'Three substantive explanations.'}


def check(verdict='pass'):
    return {'coverage': [{'key': 'calendar', 'status': 'covered' if verdict == 'pass' else 'missing', 'reason': 'Connection coverage.'}],
            'unsupported_claims': [], 'map_corrections': [], 'verdict': verdict,
            'defects': [] if verdict == 'pass' else ['missing_core_connection'], 'reason': 'Calendar connection.',
            'evidence_comment_ids': ['c1', 'c2', 'c3'], 'citation_debris': False}


def draft():
    return {'status': 'proposed', 'explanation': 'The future calendar reveals another traveler.', 'reason': 'Supported decoding.', 'evidence_comment_ids': ['c1', 'c2', 'c3']}


def call(value):
    return {'status': 'completed', 'response': {'model': ev.checks.MODEL}, 'output_text': json.dumps(value)}


@pytest.fixture
def frozen(tmp_path):
    packet = tmp_path / 'packet'
    (packet / 'assets').mkdir(parents=True)
    image = tmp_path / 'source.png'
    Image.new('RGB', (20, 20), 'white').save(image)
    sha = file_hash(image)
    (packet / 'assets' / sha).write_bytes(image.read_bytes())
    case = {'case_id': 'case', 'post_id': 'post', 'group': 'SECRET_HYPOTHESIS', 'gold': 'SECRET_LABEL',
            'input': {'image_sha256': sha, 'explanation': 'ORIGINAL_PROPOSAL',
                      'comment_evidence': '\n'.join(f'ID: c{i} | Score: 1\nComment {i}' for i in [1, 2, 3])}}
    write_json(packet / 'cases.json', [case])
    output = tmp_path / 'run'
    plan = ev.prepare(packet, output)
    return case, output, plan


def test_map_is_answer_blind_and_verifier_is_critique_blind(frozen):
    case, output, _ = frozen
    for stage in ev.STAGES:
        body = ev.make_request(case, stage, output, mapping=mapping(), explanation='CANDIDATE', critique={'reason': 'PRIVATE_CRITIQUE'})
        data = json.dumps(body)
        assert 'SECRET_' not in data and 'ORIGINAL_PROPOSAL' not in data
        if stage == 'map':
            assert 'CANDIDATE' not in data and 'Calendar connection' not in data
        if stage != 'repair':
            assert 'PRIVATE_CRITIQUE' not in data


def test_reactions_and_core_conflicts_cannot_make_supported_map(frozen):
    case, _, _ = frozen
    for mutation in ('reaction', 'duplicate', 'missing', 'conflict'):
        value = mapping()
        if mutation == 'reaction':
            value['comment_roles'][2]['role'] = 'reaction'
        elif mutation == 'duplicate':
            value['comment_roles'][2]['comment_id'] = 'c1'
        elif mutation == 'missing':
            value['comment_roles'][2]['comment_id'] = 'unknown'
        else:
            value['competing_readings'] = [{'reading': 'Different core', 'evidence_comment_ids': ['c3'], 'resolution': 'unresolved_core', 'reason': 'Not shared.'}]
        assert ev.parse(case, 'map', call(value)).get('error')


def test_pass_cannot_skip_decoding_or_borrow_a_reaction(frozen):
    case, _, _ = frozen
    for mutation in ('missing', 'wrong', 'skip', 'reaction', 'unknown'):
        value, source = check(), mapping()
        if mutation in {'missing', 'wrong'}:
            value['coverage'][0]['status'] = mutation
        elif mutation == 'skip':
            value['coverage'] = []
        elif mutation == 'reaction':
            source['comment_roles'][2]['role'] = 'reaction'
        else:
            value['evidence_comment_ids'][2] = 'unknown'
        assert ev.parse(case, 'check', call(value), source).get('error')


def test_no_per_fact_three_comment_quota(frozen):
    case, _, _ = frozen
    assert not ev.parse(case, 'map', call(mapping())).get('error')
    assert not ev.parse(case, 'check', call(check()), mapping()).get('error')


def test_cleanup_keeps_non_citation_brackets_and_detects_leftovers():
    text = 'An answer [c1, c2, c3]. Keep [a square].'
    assert ev.clean_citations(text, ['c1', 'c2', 'c3']) == ('An answer. Keep [a square].', [])
    assert ev.clean_citations('Answer [c1, unknown].', ['c1'])[1] == ['c1']


@pytest.mark.asyncio
async def test_one_repair_verified_without_earlier_critique(frozen):
    case, _, _ = frozen
    calls = []
    async def invoke(stage, **kwargs):
        calls.append((stage, kwargs))
        return {'map': mapping(), 'check': check('fail'), 'repair': draft(), 'verify': check()}[stage]
    original = copy.deepcopy(case)
    result = await ev.evaluate(case, invoke)
    assert result['status'] == 'model_supported' and result['repaired']
    assert [s for s, _ in calls] == list(ev.STAGES)
    assert set(calls[-1][1]) == {'mapping', 'explanation'}
    assert case == original


@pytest.mark.asyncio
async def test_evidence_shortfall_does_not_force_repair(frozen):
    case, _, _ = frozen
    source, assessment = mapping(), check('fail')
    source['status'] = 'insufficient_support'
    assessment['defects'] = ['insufficient_evidence']
    invoke = AsyncMock(side_effect=[source, assessment])
    result = await ev.evaluate(case, invoke)
    assert result['status'] == 'unresolved' and invoke.await_count == 2


def response(value):
    usage = {'input_tokens': 100, 'output_tokens': 50}
    return SimpleNamespace(status='completed', output_text=json.dumps(value),
        usage=SimpleNamespace(model_dump=lambda **_: usage),
        model_dump=lambda **_: {'model': ev.checks.MODEL, 'status': 'completed', 'usage': usage})


@pytest.mark.asyncio
async def test_live_run_replays_with_zero_calls_and_unchanged_artifacts(frozen):
    _, output, _ = frozen
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=[response(mapping()), response(check())])))
    report = await ev.run(output, budget_usd=.25, client=client)
    before = {str(p): file_hash(p) for p in output.rglob('*') if p.is_file() and p.name != 'run.lock'}
    offline = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=AssertionError('provider call'))))
    replay = await ev.run(output, budget_usd=.25, client=offline)
    assert replay == report and report['completed_calls'] == 2
    assert not offline.responses.create.called
    assert before == {str(p): file_hash(p) for p in output.rglob('*') if p.is_file() and p.name != 'run.lock'}
    (output / 'calls' / 'case.check.json').write_text('{}')
    with pytest.raises(ValueError, match='Frozen artifact'):
        await ev.run(output, budget_usd=.25, client=offline)


@pytest.mark.asyncio
async def test_tiny_budget_makes_no_provider_calls(frozen, tmp_path):
    _, output, _ = frozen
    packet = tmp_path / 'packet'
    output = tmp_path / 'tiny'
    ev.prepare(packet, output, budget_usd=.000001)
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=AssertionError('provider call'))))
    report = await ev.run(output, budget_usd=.000001, client=client)
    assert report['completed_calls'] == 0 and not client.responses.create.called


def test_cap_cannot_be_increased(frozen, tmp_path):
    with pytest.raises(ValueError, match='0.25'):
        ev.prepare(tmp_path / 'packet', tmp_path / 'over', budget_usd=.26)
