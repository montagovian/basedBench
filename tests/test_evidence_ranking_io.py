"""Offline checks for the bounded, replayable evidence-ranking Jev ledger."""
import hashlib
import json

import pytest

from basedbench.pipeline.evidence_ranking_io import BudgetStop, RESERVE_USD, Store


def body(qid='useful_c0'):
    return {'model': 'jev-1.13.0', 'state': {'observation': {'visible_scene': 'a scene'},
            'comments': [{'id': 'c0', 'text': 'the clue'}]},
            'questions': {qid: {'type': 'noul', 'instructions': 'Does this decode the joke?'}}}


class Jev:
    def __init__(self, *, answer=.75, usage=True, model='jev-1.13.0'):
        self.calls = []
        self.answer, self.usage, self.model = answer, usage, model

    def post(self, url, json):
        assert url == 'https://api.typesafe.ai/v1/systemone'
        self.calls.append(json)
        qid = next(iter(json['questions']))
        response = {'model': self.model, 'answers': {qid: {'type': 'noul', 'noul': self.answer}}}
        if self.usage:
            response['usage'] = {'input_tokens': 100, 'output_tokens': 3}
        return response


def test_replay_is_credential_free_and_zero_cost(tmp_path):
    client = Jev()
    store = Store(tmp_path, {'plan_id': 'rank'}, client=client)
    expected = {'status': 'completed', 'scores': {'useful_c0': .75}, 'errors': []}
    assert store.call(body()) == expected
    assert len(client.calls) == 1
    report = store.report()
    assert report['spent_usd'] == pytest.approx(100 * .042 / 1_000_000)
    assert report['spent_or_reserved_usd'] == report['spent_usd']
    replay = Store(tmp_path, {'plan_id': 'rank'})
    assert replay.call(body()) == expected
    assert replay.report() == report


def test_invalid_answer_settles_known_cost_and_allows_later_call(tmp_path):
    client = Jev(answer=2)
    store = Store(tmp_path, {'plan_id': 'rank'}, client=client)
    bad = store.call(body())
    assert bad['status'] == 'invalid' and bad['scores'] == {}
    assert bad['errors'] == ['answer_probability']
    client.answer = .2
    good = store.call(body('decodes_c0'))
    assert good['scores'] == {'decodes_c0': .2}
    assert store.report()['invalid_calls'] == 1
    assert store.report()['pending_calls'] == 0
    replay = Store(tmp_path, {'plan_id': 'rank'})
    assert replay.call(body()) == bad


@pytest.mark.parametrize('answer', [True, float('nan'), -0.1, 1.1, '0.8'])
def test_invalid_probabilities_abstain_without_partial_scores(tmp_path, answer):
    store = Store(tmp_path, {'plan_id': 'rank'}, client=Jev(answer=answer))
    assert store.call(body())['status'] == 'invalid'


def test_exact_reservation_and_call_question_caps(tmp_path):
    client = Jev()
    store = Store(tmp_path, {'plan_id': 'rank', 'budget_usd': RESERVE_USD,
                             'max_calls': 2, 'max_questions': 2}, client=client)
    store.call(body())
    with pytest.raises(BudgetStop, match='budget_cap'):
        store.call(body('decodes_c0'))
    assert len(client.calls) == 1
    assert store.report()['calls'] == 1
    store2 = Store(tmp_path / 'calls', {'plan_id': 'rank', 'max_calls': 1}, client=Jev())
    store2.call(body())
    with pytest.raises(BudgetStop, match='call_cap'):
        store2.call(body('decodes_c0'))
    store3 = Store(tmp_path / 'questions', {'plan_id': 'rank', 'max_questions': 1}, client=Jev())
    store3.call(body())
    with pytest.raises(BudgetStop, match='question_cap'):
        store3.call(body('decodes_c0'))


def test_missing_credential_precedes_reservation(tmp_path):
    store = Store(tmp_path, {'plan_id': 'rank'})
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match='credential or client'):
        store.call(body())
    assert store.path.read_bytes() == before
    assert not (tmp_path / 'evidence-ranking-requests').exists()


def test_unknown_usage_stays_pending_without_retry(tmp_path):
    client = Jev(usage=False)
    store = Store(tmp_path, {'plan_id': 'rank'}, client=client)
    with pytest.raises(BudgetStop, match='unknown_usage_or_model'):
        store.call(body())
    assert store.report()['pending_calls'] == 1
    assert store.report()['spent_or_reserved_usd'] == RESERVE_USD
    raw = next((tmp_path / 'evidence-ranking-calls').glob('*.json'))
    assert json.loads(raw.read_text())['response']['answers']
    replay = Store(tmp_path, {'plan_id': 'rank'}, client=client)
    with pytest.raises(BudgetStop):
        replay.call(body())
    assert len(client.calls) == 1


def test_crash_window_with_raw_response_remains_pending(tmp_path):
    store = Store(tmp_path, {'plan_id': 'rank'}, client=Jev(usage=False))
    with pytest.raises(BudgetStop):
        store.call(body())
    key = next(iter(store.ledger['pending']))
    ledger = json.loads(store.path.read_text())
    ledger['pending'][key].pop('artifact_hash')
    store.path.write_text(json.dumps(ledger))
    replay = Store(tmp_path, {'plan_id': 'rank'}, client=Jev())
    assert replay.report()['pending_calls'] == 1
    with pytest.raises(BudgetStop):
        replay.call(body())


def test_rehashed_response_tamper_fails_reparse(tmp_path):
    store = Store(tmp_path, {'plan_id': 'rank'}, client=Jev())
    store.call(body())
    key = next(iter(store.ledger['calls']))
    path = tmp_path / 'evidence-ranking-calls' / f'{key}.json'
    call = json.loads(path.read_text())
    call['response']['answers']['useful_c0']['noul'] = .2
    path.write_text(json.dumps(call, sort_keys=True, ensure_ascii=False, separators=(',', ':')))
    ledger = json.loads(store.path.read_text())
    ledger['calls'][key]['artifact_hash'] = hashlib.sha256(path.read_bytes()).hexdigest()
    store.path.write_text(json.dumps(ledger))
    with pytest.raises(ValueError, match='settlement'):
        Store(tmp_path, {'plan_id': 'rank'})


def test_rehashed_request_tamper_fails_identity(tmp_path):
    store = Store(tmp_path, {'plan_id': 'rank'}, client=Jev())
    store.call(body())
    key = next(iter(store.ledger['calls']))
    path = tmp_path / 'evidence-ranking-requests' / f'{key}.json'
    request = json.loads(path.read_text())
    request['state']['comments'][0]['text'] = 'changed'
    path.write_text(json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(',', ':')))
    ledger = json.loads(store.path.read_text())
    ledger['calls'][key]['request_hash'] = hashlib.sha256(path.read_bytes()).hexdigest()
    store.path.write_text(json.dumps(ledger))
    with pytest.raises(ValueError, match='Request integrity'):
        Store(tmp_path, {'plan_id': 'rank'})


@pytest.mark.parametrize('key', ['human_label', 'reference_explanation', 'candidate_answer', 'prior_score'])
def test_private_answer_fields_rejected_before_provider(tmp_path, key):
    client = Jev()
    store = Store(tmp_path, {'plan_id': 'rank'}, client=client)
    request = body()
    request['state'][key] = 'secret'
    with pytest.raises(ValueError):
        store.call(request)
    assert not client.calls
    assert store.report()['calls'] == 0


def test_changed_plan_rejected(tmp_path):
    Store(tmp_path, {'plan_id': 'rank'})
    with pytest.raises(ValueError, match='different plan'):
        Store(tmp_path, {'plan_id': 'other'})
