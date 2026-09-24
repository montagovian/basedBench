"""Offline contract checks for the bounded provider ledger."""
import json
import hashlib
from types import SimpleNamespace

import pytest

from basedbench.pipeline.jev_optimization_io import BudgetStop, ProviderStore


def body():
    return {'model': 'jev-1.13.0', 'state': {'comments': []},
            'questions': {'q': {'type': 'noul', 'instructions': 'Is the joke decoded?'}}}


class Jev:
    def __init__(self, usage=True):
        self.count = 0
        self.usage = usage

    def post(self, url, json):
        self.count += 1
        assert url == 'https://api.typesafe.ai/v1/systemone'
        result = {'model': json['model'], 'answers': {'q': {'type': 'noul', 'noul': .75}}}
        if self.usage:
            result['usage'] = {'input_tokens': 100, 'output_tokens': 3}
        return result


class OpenAI:
    def __init__(self, usage=True):
        self.calls = []
        self.usage = usage
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = {'model': kwargs['model'], 'service_tier': 'default',
                  'status': 'completed', 'output_text': 'proposal'}
        if self.usage:
            result['usage'] = {'input_tokens': 100, 'output_tokens': 10}
        return result


def test_jev_cache_is_credential_free_and_durable(tmp_path):
    provider = Jev()
    store = ProviderStore(tmp_path, {'experiment_id': 'e'}, jev_client=provider)
    assert store.jev(body(), 'search') == {'q': {'value': .75}}
    assert provider.count == 1
    replay = ProviderStore(tmp_path, {'experiment_id': 'e'})
    assert replay.jev(body(), 'search') == {'q': {'value': .75}}
    assert replay.report()['calls'] == 1


def test_tampered_call_or_request_is_rejected(tmp_path):
    store = ProviderStore(tmp_path, {}, jev_client=Jev())
    store.jev(body(), 'search')
    call_path = next((tmp_path / 'provider-calls').glob('*.json'))
    call_path.write_text(call_path.read_text().replace('0.75', '0.25'))
    with pytest.raises(ValueError, match='integrity'):
        ProviderStore(tmp_path, {})
    original = store.ledger['calls']
    assert original


def test_exact_budget_and_call_caps(tmp_path):
    plan = {'budget_total_usd': 5, 'budget_search_usd': 4,
            'max_provider_calls': 1, 'final_call_reserve': 0,
            'max_questions': 1, 'final_question_reserve': 0}
    store = ProviderStore(tmp_path, plan, jev_client=Jev())
    store.jev(body(), 'search')
    different = body()
    different['state']['comments'] = [{'id': 'one', 'text': 'new'}]
    with pytest.raises(BudgetStop, match='call_cap'):
        store.jev(different, 'final')
    assert store.report()['calls'] == 1


def test_exact_reservation_budget_boundary(tmp_path):
    reserve = 64000 * .042 / 1_000_000
    class FullUsage(Jev):
        def post(self, url, json):
            result = super().post(url, json)
            result['usage']['input_tokens'] = 64000
            return result
    store = ProviderStore(tmp_path, {'budget_total_usd': reserve, 'budget_search_usd': reserve,
        'max_provider_calls': 2, 'final_call_reserve': 0, 'max_questions': 2,
        'final_question_reserve': 0}, jev_client=FullUsage())
    store.jev(body(), 'search')
    assert store.report()['spent_or_reserved_usd'] == pytest.approx(reserve)
    different = body()
    different['state']['comments'] = [{'id': 'one', 'text': 'new'}]
    with pytest.raises(BudgetStop, match='total_budget_cap'):
        store.jev(different, 'final')


def test_pending_reopens_as_stop_without_retry(tmp_path):
    store = ProviderStore(tmp_path, {}, jev_client=Jev(usage=False))
    with pytest.raises(BudgetStop, match='provider_or_settlement_error'):
        store.jev(body(), 'search')
    assert store.report()['pending_calls'] == 1
    replay = ProviderStore(tmp_path, {}, jev_client=Jev())
    with pytest.raises(BudgetStop):
        replay.jev(body(), 'search')
    assert replay.report()['pending_calls'] == 1


def test_interrupted_settlement_keeps_raw_call_pending(tmp_path):
    store = ProviderStore(tmp_path, {}, jev_client=Jev(usage=False))
    with pytest.raises(BudgetStop):
        store.jev(body(), 'search')
    key = next(iter(store.ledger['pending']))
    # Simulate a crash after writing raw bytes, before checkpointing their hash.
    ledger_path = tmp_path / 'provider-ledger.json'
    ledger = json.loads(ledger_path.read_text())
    del ledger['pending'][key]['artifact_hash']
    ledger_path.write_text(json.dumps(ledger))
    artifact = tmp_path / 'provider-calls' / (key + '.json')
    artifact.parent.mkdir(exist_ok=True)
    artifact.write_text('{"unverified":"raw response"}')
    replay = ProviderStore(tmp_path, {}, jev_client=Jev())
    assert replay.report()['pending_calls'] == 1
    with pytest.raises(BudgetStop):
        replay.jev(body(), 'search')


def test_reflection_request_cost_and_40k_limit(tmp_path):
    provider = OpenAI()
    store = ProviderStore(tmp_path, {}, openai_client=provider)
    assert store.reflect('training feedback') == 'proposal'
    assert provider.calls == [{'model': 'gpt-6-sol', 'input': 'training feedback',
        'reasoning': {'effort': 'medium'}, 'max_output_tokens': 4000,
        'store': False, 'service_tier': 'default'}]
    assert store.report()['spent_or_reserved_usd'] == pytest.approx(.00035)
    with pytest.raises(ValueError, match='40k'):
        store.reflect('é' * 20001)


def test_unknown_reflection_usage_stops_and_reserves(tmp_path):
    store = ProviderStore(tmp_path, {}, openai_client=OpenAI(usage=False))
    with pytest.raises(BudgetStop):
        store.reflect('hello')
    assert store.report()['pending_calls'] == 1
    assert store.report()['spent_or_reserved_usd'] > .04
    raw = next((tmp_path / 'provider-calls').glob('*.json'))
    assert json.loads(raw.read_text())['status'] == 'unverified'
    assert json.loads(raw.read_text())['response']['output_text'] == 'proposal'


def test_jev_rejects_human_metadata_before_provider(tmp_path):
    provider = Jev()
    store = ProviderStore(tmp_path, {}, jev_client=provider)
    request = body()
    request['state']['human_label'] = 'fail'
    with pytest.raises(ValueError, match='Human labels'):
        store.jev(request, 'search')
    assert provider.count == 0
    assert list((tmp_path / 'provider-requests').glob('*.json')) == [] if (tmp_path / 'provider-requests').exists() else True


def test_report_omits_raw_payload(tmp_path):
    store = ProviderStore(tmp_path, {}, openai_client=OpenAI())
    store.reflect('private training feedback')
    assert 'private training feedback' not in json.dumps(store.report())


def test_search_reserves_final_calls_and_questions(tmp_path):
    plan = {'max_provider_calls': 2, 'final_call_reserve': 1,
            'max_questions': 2, 'final_question_reserve': 1}
    store = ProviderStore(tmp_path, plan, jev_client=Jev())
    store.jev(body(), 'search')
    second = body()
    second['state']['comments'] = [{'id': 'two', 'text': 'different'}]
    with pytest.raises(BudgetStop, match='call_cap'):
        store.jev(second, 'search')
    assert store.report()['calls'] == 1


def test_invalid_provider_schema_stops_with_pending_reservation(tmp_path):
    class BadJev(Jev):
        def post(self, url, json):
            result = super().post(url, json)
            result['answers']['q']['noul'] = 2
            return result
    store = ProviderStore(tmp_path, {}, jev_client=BadJev())
    with pytest.raises(BudgetStop, match='provider_or_settlement_error'):
        store.jev(body(), 'search')
    assert store.report()['pending_calls'] == 1
    raw = next((tmp_path / 'provider-calls').glob('*.json'))
    assert json.loads(raw.read_text())['response']['answers']['q']['noul'] == 2


def test_missing_credential_cache_miss_does_not_reserve(tmp_path):
    store = ProviderStore(tmp_path, {'plan_id': 'p'})
    before = (tmp_path / 'provider-ledger.json').read_bytes()
    with pytest.raises(ValueError, match='credential or client'):
        store.jev(body(), 'search')
    with pytest.raises(ValueError, match='credential or client'):
        store.reflect('uncached')
    assert (tmp_path / 'provider-ledger.json').read_bytes() == before
    assert not (tmp_path / 'provider-requests').exists()


def test_cache_response_reparsed_even_with_rehashed_artifact(tmp_path):
    store = ProviderStore(tmp_path, {'plan_id': 'p'}, jev_client=Jev())
    store.jev(body(), 'search')
    key = next(iter(store.ledger['calls']))
    call_path = tmp_path / 'provider-calls' / (key + '.json')
    call = json.loads(call_path.read_text())
    call['response']['answers']['q']['noul'] = .2
    call_path.write_text(json.dumps(call, sort_keys=True, ensure_ascii=False, separators=(',', ':')))
    ledger_path = tmp_path / 'provider-ledger.json'
    ledger = json.loads(ledger_path.read_text())
    ledger['calls'][key]['artifact_hash'] = hashlib.sha256(call_path.read_bytes()).hexdigest()
    ledger_path.write_text(json.dumps(ledger))
    with pytest.raises(ValueError, match='settlement'):
        ProviderStore(tmp_path, {'plan_id': 'p'})


def test_cache_request_key_recomputed(tmp_path):
    store = ProviderStore(tmp_path, {'plan_id': 'p'}, jev_client=Jev())
    store.jev(body(), 'search')
    key = next(iter(store.ledger['calls']))
    req_path = tmp_path / 'provider-requests' / (key + '.json')
    request = json.loads(req_path.read_text())
    request['payload']['state']['comments'] = [{'id': 'x', 'text': 'tampered'}]
    req_path.write_text(json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(',', ':')))
    ledger_path = tmp_path / 'provider-ledger.json'
    ledger = json.loads(ledger_path.read_text())
    ledger['calls'][key]['request_hash'] = hashlib.sha256(req_path.read_bytes()).hexdigest()
    ledger_path.write_text(json.dumps(ledger))
    with pytest.raises(ValueError, match='integrity'):
        ProviderStore(tmp_path, {'plan_id': 'p'})


@pytest.mark.parametrize('total,search', [(float('nan'), 4), (6, 4), (5, float('inf'))])
def test_plan_rejects_nonfinite_or_overapproved_budget(tmp_path, total, search):
    with pytest.raises(ValueError, match='budget plan'):
        ProviderStore(tmp_path, {'budget_total_usd': total, 'budget_search_usd': search})
