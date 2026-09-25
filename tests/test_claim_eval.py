"""Source identity, derived decisions, blind verification and bounded paid replay."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from basedbench.pipeline import claim_eval as ev
from basedbench.pipeline.curation_corpus import file_hash
from tests.test_connection_eval import frozen, response, call


def assessment(answer='ORIGINAL_PROPOSAL'):
    return {'shared_reading': 'The future calendar gives the traveler away.',
        'required_connections': [{'visible_anchor': 'BC', 'decoding': 'A future calendar label.',
                                 'answer_span': answer, 'coverage': 'covered'}],
        'material_claims': [{'answer_span': answer, 'status': 'supported', 'reason': 'Conveys the connection.'}],
        'intent': {'answer_spans': [], 'status': 'no_attribution', 'reason': 'No authorial claim.'},
        'comments': {f'c{i}': {'excerpt': f'Comment {i}', 'role': 'supports_shared_reading',
                    'contribution': 'Explains the calendar.'} for i in range(1, 4)},
        'unresolved_core_conflict': False, 'conflict_reason': ''}


def baseline():
    return {'image_setup': 'A calendar.', 'joke_connection': 'The future calendar.',
        'claim_support': [{'claim': 'The calendar is anachronistic.', 'support': 'image', 'evidence_comment_ids': []}],
        'missing_core_details': [], 'verdict': 'pass', 'reason': 'It explains the joke.',
        'defects': [], 'evidence_comment_ids': ['c1', 'c2', 'c3']}


def test_quotes_cannot_be_borrowed_from_another_source(frozen):
    case, _, _ = frozen
    for mutation in ('comment', 'answer', 'intent', 'missing_comment', 'missing_span'):
        value = assessment()
        if mutation == 'comment':
            value['comments']['c1']['excerpt'] = 'Comment 2'
        elif mutation == 'answer':
            value['material_claims'][0]['answer_span'] = 'The answer should have said this.'
        elif mutation == 'intent':
            value['intent'] = {'answer_spans': ['An invented attribution'], 'status': 'unsupported', 'reason': 'Not literal.'}
        elif mutation == 'missing_comment':
            value['comments'].pop('c1')
        else:
            value['required_connections'][0]['answer_span'] = None
        assert ev.parse(case, 'check', call(value), 'ORIGINAL_PROPOSAL').get('error')


def test_neutral_map_does_not_override_literal_intent_and_support_findings(frozen):
    case, _, _ = frozen
    value = assessment()
    value['intent'] = {'answer_spans': ['ORIGINAL_PROPOSAL'], 'status': 'disputed', 'reason': 'The answer attributes disputed intent.'}
    result = ev.parse(case, 'check', call(value), 'ORIGINAL_PROPOSAL')
    assert result['verdict'] == 'fail' and result['repairable']
    assert result['defects'] == ['unsupported_intent']
    value['comments']['c3']['role'] = 'extra_joke'
    result = ev.parse(case, 'check', call(value), 'ORIGINAL_PROPOSAL')
    assert not result['repairable'] and result['evidence_defects'] == ['insufficient_substantive_support']
    value['intent'] = assessment()['intent']
    assert ev.parse(case, 'check', call(value), 'ORIGINAL_PROPOSAL')['verdict'] == 'uncertain'


def test_missing_decoding_or_core_conflict_cannot_pass(frozen):
    case, _, _ = frozen
    value = assessment()
    value['required_connections'][0].update(coverage='missing', answer_span=None)
    assert ev.parse(case, 'check', call(value), 'ORIGINAL_PROPOSAL')['verdict'] == 'fail'
    value = assessment()
    value['unresolved_core_conflict'] = True
    assert ev.parse(case, 'check', call(value), 'ORIGINAL_PROPOSAL')['verdict'] == 'uncertain'


def test_keyed_schema_and_fresh_verifier_input(frozen):
    case, output, _ = frozen
    request = ev.make_request(case, 'verify', output, explanation='REPAIRED', critique={'reason': 'SECRET_CRITIQUE'})
    raw = json.dumps(request)
    assert all(s not in raw for s in ['SECRET_', 'ORIGINAL_PROPOSAL', 'source_first_map', 'fallible_findings'])
    evidence = json.loads(request['input'][0]['content'][0]['text'])
    assert set(evidence) == {'candidate_answer', 'comment_evidence'}
    schema = request['text']['format']['schema']['properties']['comments']
    assert set(schema['required']) == {'c1', 'c2', 'c3'} and not schema['additionalProperties']
    assert ev.make_request(case, 'baseline', output)['instructions'] == ev.answers.CHECK


@pytest.mark.asyncio
async def test_one_repair_with_fresh_verification(frozen):
    case, _, _ = frozen
    original = copy.deepcopy(case)
    failed = ev.derive(assessment())
    failed.update(verdict='fail', repairable=True)
    proposal = {'status': 'proposed', 'explanation': 'A repair', 'reason': 'Grounded.', 'evidence_comment_ids': ['c1', 'c2', 'c3']}
    calls = []
    async def invoke(stage, **kwargs):
        calls.append((stage, kwargs))
        return {'baseline': baseline(), 'check': failed, 'repair': proposal, 'verify': ev.derive(assessment('A repair'))}[stage]
    result = await ev.evaluate(case, invoke)
    assert result['status'] == 'model_supported' and result['repaired']
    assert [s for s, _ in calls] == list(ev.STAGES)
    assert calls[-1][1] == {'explanation': 'A repair'} and case == original


@pytest.mark.asyncio
async def test_paid_replay_and_budget_stop(frozen, tmp_path):
    case, _, _ = frozen
    packet = tmp_path / 'packet'
    output = tmp_path / 'direct'
    ev.prepare(packet, output, case_ids=['case'])
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=[response(baseline()), response(assessment())])))
    report = await ev.run(output, client=client)
    assert report['completed_calls'] == 2 and report['statuses'] == {'model_supported': 1}
    before = {str(p): file_hash(p) for p in output.rglob('*') if p.is_file() and p.name != 'run.lock'}
    offline = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=AssertionError('provider call'))))
    assert await ev.run(output, client=offline) == report
    assert not offline.responses.create.called
    assert before == {str(p): file_hash(p) for p in output.rglob('*') if p.is_file() and p.name != 'run.lock'}
    tiny = tmp_path / 'tiny-direct'
    ev.prepare(packet, tiny, case_ids=['case'], budget_usd=.000001)
    assert (await ev.run(tiny, client=offline))['completed_calls'] == 0
    assert not offline.responses.create.called
    (output / 'calls' / 'case.check.json').write_text('{}')
    with pytest.raises(ValueError, match='Frozen artifact'):
        await ev.run(output, client=offline)


def test_no_cap_increase_or_overall_model_verdict(frozen, tmp_path):
    with pytest.raises(ValueError, match='0.25'):
        ev.prepare(tmp_path / 'packet', tmp_path / 'over', case_ids=['case'], budget_usd=.26)
    case, _, _ = frozen
    value = assessment() | {'verdict': 'pass'}
    assert ev.parse(case, 'check', call(value), 'ORIGINAL_PROPOSAL').get('error')
