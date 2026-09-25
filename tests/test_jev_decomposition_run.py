"""Budget, dependent request integrity and no-network replay of the Jev runner."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

from basedbench.pipeline import jev_decomposition_run as run
from basedbench.pipeline.curation_corpus import file_hash, write_json


def fixture(tmp_path, budget=1):
    root = tmp_path / 'run'
    dataset = root / 'dataset'
    (dataset / 'assets').mkdir(parents=True)
    path = dataset / 'assets/image.png'
    Image.new('RGB', (12, 12), 'white').save(path)
    text = 'Cans stands for Canadians.'
    case = {'case_id': 'case-a', 'post_id': 'post-a', 'group_id': 'family-a',
        'human': {'quality': 'repair', 'events': [{'notes': 'PRIVATE_GOLD_NOTE'}]},
        'input': {'explanation': text, 'comment_evidence': 'Canadians become cans.',
            'image_sha256': file_hash(path)}, 'image_path': str(path), 'image_error': None,
        'comments': [{'id': 'c0', 'text': 'Canadians become cans.'}],
        'spans': [{'id': 's0', 'text': text, 'start': 0, 'end': len(text)}]}
    write_json(dataset / 'cases.json', [case])
    write_json(dataset / 'manifest.json', {'files': {str(p.relative_to(dataset)): file_hash(p)
        for p in (dataset / 'cases.json', path)}})
    run.prepare(root, budget_usd=budget)
    return root


class Obj:
    def __init__(self, data):
        self.data = data
    def model_dump(self, **kwargs):
        return self.data


class OpenAIStub:
    def __init__(self):
        self.requests = []
        self.responses = self
    async def create(self, **body):
        self.requests.append(body)
        assert 'PRIVATE_GOLD_NOTE' not in json.dumps(body)
        assert 'Cans stands for Canadians' not in json.dumps(body)
        usage = {'input_tokens': 100, 'output_tokens': 100,
                 'input_tokens_details': {'cache_write_tokens': 0, 'cached_tokens': 0}}
        obs = {'visible_text': 'how Finns see Canadians', 'visible_scene': 'Two cans.', 'uncertainties': []}
        payload = {'model': 'gpt-6-luna', 'service_tier': 'default', 'status': 'completed', 'usage': usage}
        response = Obj(payload)
        response.status, response.usage, response.output_text = 'completed', Obj(usage), json.dumps(obs)
        return response


class JevStub:
    def __init__(self, *, fail=False, bad_model=False):
        self.requests = []
        self.fail, self.bad_model = fail, bad_model
    async def post(self, path, json):
        assert path == '/v1/systemone'
        self.requests.append(json)
        assert 'PRIVATE_GOLD_NOTE' not in str(json)
        if self.fail:
            raise RuntimeError('uncertain transport delivery')
        answers = {}
        for qid, q in json['questions'].items():
            if q['type'] == 'noul':
                answers[qid] = {'type': 'noul', 'noul': .1}
            else:
                labels = list(q['criteria'])
                answers[qid] = {'type': 'choice', 'choice': labels[0], 'confidence': .9,
                    'probabilities': {key: .9 if i == 0 else .1 / (len(labels) - 1) for i, key in enumerate(labels)}}
        payload = {'model': 'unexpected-model' if self.bad_model else 'jev-1.13.0',
            'answers': answers, 'usage': {'input_tokens': 200, 'output_tokens': 0}}
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)


def test_complete_replay_makes_zero_calls_and_preserves_manifest(tmp_path):
    root = fixture(tmp_path)
    jev, helper = JevStub(), OpenAIStub()
    report = asyncio.run(run.run(root, jev_client=jev, openai_client=helper))
    assert report['complete'] and report['unknown_usage_calls'] == 0
    assert len(helper.requests) == 1 and len(jev.requests) == 15
    assert report['calls'] == 16
    assert report['accounted_usd'] < 1
    assert len(report['repeat_deltas']) == 2 and len(report['batch_single_deltas']) == 8
    sha = file_hash(root / 'records-manifest.json')
    replay = asyncio.run(run.run(root))
    assert replay == report
    assert file_hash(root / 'records-manifest.json') == sha
    assert not list((root / 'calls').glob('*.pending'))


def test_cap_stops_before_any_dispatch(tmp_path):
    root = fixture(tmp_path, budget=.000001)
    jev, helper = JevStub(), OpenAIStub()
    report = asyncio.run(run.run(root, jev_client=jev, openai_client=helper))
    assert not jev.requests and not helper.requests
    assert report['calls'] == 0 and report['stop_reason'] == 'budget_cap'
    assert not report['complete']


@pytest.mark.parametrize('bad_model', [False, True])
def test_unknown_cost_keeps_reserve_halts_and_never_retries(tmp_path, bad_model):
    root = fixture(tmp_path)
    jev, helper = JevStub(fail=not bad_model, bad_model=bad_model), OpenAIStub()
    report = asyncio.run(run.run(root, jev_client=jev, openai_client=helper))
    assert len(jev.requests) == 1 and not helper.requests
    assert report['accounted_usd'] == run.JEV_RESERVE
    assert report['unknown_usage_calls'] == 1
    assert report['stop_reason'] == 'unknown_usage_or_reservation_violation'
    assert asyncio.run(run.run(root)) == report


def test_call_tamper_refused_before_network(tmp_path):
    root = fixture(tmp_path)
    asyncio.run(run.run(root, jev_client=JevStub(), openai_client=OpenAIStub()))
    call_path = next((root / 'calls').glob('*.json'))
    payload = json.loads(call_path.read_text())
    payload['latency_ms'] = -100
    write_json(call_path, payload)
    with pytest.raises(ValueError, match='Unverified'):
        asyncio.run(run.run(root))


def test_unresolved_marker_blocks_new_calls(tmp_path):
    root = fixture(tmp_path)
    plan = json.loads((root / 'plan.json').read_text())
    write_json(root / 'ledger.json', {'experiment_id': plan['experiment_id'],
        'calls': {}, 'pending': {'case-a.broad_text': run.JEV_RESERVE}})
    (root / 'calls/case-a.broad_text.pending').write_text(plan['experiment_id'])
    jev = JevStub()
    report = asyncio.run(run.run(root, jev_client=jev))
    assert not jev.requests
    assert report['stop_reason'] == 'unresolved_pending_call'
    assert report['accounted_usd'] == run.JEV_RESERVE
    assert report['pending_calls'] == 1


def test_interrupted_response_settlement_reports_reserved_hold(tmp_path):
    root = fixture(tmp_path)
    asyncio.run(run.run(root, jev_client=JevStub(), openai_client=OpenAIStub()))
    ledger = json.loads((root / 'ledger.json').read_text())
    key = 'case-a.broad_text'
    del ledger['calls'][key]
    ledger['pending'][key] = run.JEV_RESERVE
    write_json(root / 'ledger.json', ledger)
    (root / 'calls' / (key + '.pending')).write_text(ledger['experiment_id'])
    saved_hash = file_hash(root / 'calls' / (key + '.json'))
    jev = JevStub()
    report = asyncio.run(run.run(root, jev_client=jev))
    assert not jev.requests
    assert report['pending_calls'] == 1 and report['unknown_usage_calls'] == 1
    assert not report['complete']
    assert report['stop_reason'] == 'unresolved_pending_call'
    assert file_hash(root / 'calls' / (key + '.json')) == saved_hash
    records = json.loads((root / 'records.json').read_text())
    assert records[0]['arms']['broad_text']['state'] == 'technical_error'
