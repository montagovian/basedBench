"""Isolate model capacity, enforce model-specific spending, and preserve replay."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from basedbench.pipeline import capacity_eval as ev
from basedbench.pipeline.curation_corpus import file_hash, write_json
from tests.test_focused_connection_eval import prepared as focused_prepared, FakeClient as FocusedClient, value


def prepared(tmp_path, monkeypatch):
    _, _, source, _ = focused_prepared(tmp_path, monkeypatch)
    asyncio.run(ev.focused.run(source, client=FocusedClient()))
    (tmp_path / 'docs/capacity-comparison-plan.md').write_text('Frozen capacity test plan')
    access = tmp_path / 'access.json'
    write_json(access, {'models': [{'id': m} for m in ev.MODELS.values()]})
    output = tmp_path / 'capacity'
    plan = ev.prepare(source, output, access)
    return source, output, plan


class Client:
    def __init__(self):
        self.responses = self
        self.calls = 0

    async def create(self, **body):
        self.calls += 1
        usage = {'input_tokens': 100, 'output_tokens': 100}
        return SimpleNamespace(status='completed', output_text=json.dumps(value(False)),
            usage=SimpleNamespace(model_dump=lambda **_: usage),
            model_dump=lambda **_: {'model': body['model'], 'status': 'completed', 'usage': usage})


def test_model_id_is_the_only_paired_request_change(tmp_path, monkeypatch):
    source, output, plan = prepared(tmp_path, monkeypatch)
    assert len(plan['jobs']) == 52 and plan['budget_usd'] == 10
    assert (source / 'cases.json').read_bytes() == (output / 'cases.json').read_bytes()
    c = json.loads((output / 'cases.json').read_text())[0]
    luna, sol = (ev.request(c, a, output) for a in ev.MODELS)
    assert sol == luna | {'model': 'gpt-6-sol'}
    assert luna == ev.focused.request(c, 'baseline', source)
    assert 'required_connections' not in sol['text']['format']['schema']['properties']
    assert sol['instructions'] == ev.calibrated.SIMPLE
    assert 'PRIVATE HUMAN LABEL NOTE' not in json.dumps(sol)
    assert 'original_quality' not in json.dumps(sol)


def test_sol_pricing_and_full_context_reservation():
    usage = {'input_tokens': 10000, 'output_tokens': 1000,
             'input_tokens_details': {'cached_tokens': 2000, 'cache_write_tokens': 3000}}
    assert ev.price(usage, 'gpt-6-sol') == pytest.approx(.0279)
    assert ev.price(usage, 'gpt-6-sol', conservative=True) == pytest.approx(.035)
    assert ev.price({'input_tokens': 300000, 'output_tokens': 1000}, 'gpt-6-sol') == pytest.approx(1.215)
    assert ev.price({'input_tokens': True, 'output_tokens': 0}, 'gpt-6-sol') is None
    assert ev.price({'input_tokens': 1, 'output_tokens': 0, 'input_tokens_details': {'cached_tokens': 2}}, 'gpt-6-sol') is None
    assert ev.bound({'model': 'gpt-6-sol', 'max_output_tokens': 4000}) == pytest.approx(5.31)
    assert ev.bound({'model': 'gpt-6-luna', 'max_output_tokens': 4000}) == pytest.approx(.2655)


def test_budget_serializes_sol_and_unknown_usage_stops_every_model(tmp_path):
    (tmp_path / 'calls').mkdir()
    plan = {'experiment_id': 'id', 'budget_usd': 10,
            'request_bounds_usd': {'a.sol': 5.31, 'b.sol': 5.31, 'c.luna': .2655},
            'jobs': [{'key': 'a.sol', 'model': 'gpt-6-sol'}, {'key': 'b.sol', 'model': 'gpt-6-sol'},
                     {'key': 'c.luna', 'model': 'gpt-6-luna'}]}
    b = ev.Budget(plan, tmp_path)
    assert b.reserve('a', 'sol') == 5.31
    assert b.reserve('b', 'sol') is None
    assert b.reserve('c', 'luna') == .2655
    b.settle('a', 'sol', {'usage': {'input_tokens': 100, 'output_tokens': 100}})
    assert b.charges['a.sol'] == pytest.approx(.00125)
    assert b.reserve('b', 'sol') == 5.31
    unknown = {'experiment_id': 'id', 'post_id': 'b', 'arm': 'sol', 'usage': None}
    b.settle('b', 'sol', unknown)
    assert b.unknown and b.reserve('a', 'sol') is None and b.reserve('c', 'luna') is None
    write_json(tmp_path / 'calls/b.sol.json', unknown)
    restored = ev.Budget(plan, tmp_path)
    assert restored.unknown and restored.charges['b.sol'] == 5.31
    assert restored.reserve('c', 'luna') is None


def test_returned_model_and_source_support_are_validated(tmp_path, monkeypatch):
    _, output, _ = prepared(tmp_path, monkeypatch)
    c = json.loads((output / 'cases.json').read_text())[0]
    call = {'status': 'completed', 'response': {'model': 'gpt-6-sol'}, 'output_text': json.dumps(value(False))}
    v = ev.parse(c, 'sol', call)
    assert v['answer_quality'] == 'pass' and v['verdict'] == 'uncertain'
    assert 'error' in ev.parse(c, 'luna', call)
    bad = value(False) | {'evidence_status': 'supported'}
    assert 'error' in ev.parse(c, 'sol', call | {'output_text': json.dumps(bad)})


def test_completed_capacity_run_replays_at_zero_cost_with_model_specific_totals(tmp_path, monkeypatch):
    _, output, _ = prepared(tmp_path, monkeypatch)
    client = Client()
    report = asyncio.run(ev.run(output, client=client))
    assert client.calls == report['calls'] == 52 and report['technical_errors'] == 0
    assert report['cost_by_arm']['sol'] == pytest.approx(20 * report['cost_by_arm']['luna'])
    assert not report['quantitative_screen_pass']
    hashes = {str(p): file_hash(p) for p in output.rglob('*') if p.is_file()}
    class NoNetwork:
        def __getattr__(self, name):
            raise AssertionError('Replay touched provider: ' + name)
    assert asyncio.run(ev.run(output, client=NoNetwork())) == report
    assert hashes == {str(p): file_hash(p) for p in output.rglob('*') if p.is_file()}
