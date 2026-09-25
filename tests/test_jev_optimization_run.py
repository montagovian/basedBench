"""Installed-GEPA and full offline search/final/replay contract checks."""
import copy
import json
from types import SimpleNamespace

import pytest

from basedbench.pipeline import jev_optimization_run as run
from basedbench.pipeline import jev_optimization_policy as policy
from basedbench.pipeline import jev_optimization_protocol as protocol
from basedbench.pipeline.jev_optimization_io import ProviderStore, BudgetStop


def fixture_cases():
    cases = {}
    for partition in ('train', 'val', 'test'):
        for gold in ('ready', 'repair'):
            cid = partition + '-' + gold
            cases[cid] = {'case_id': cid, 'group_id': cid, 'gold': gold,
                'input': {'explanation': partition + (' complete inversion' if gold == 'ready' else ' incomplete topic')},
                'comments': [{'id': 'c', 'text': 'The expected decoding is a reversal of the usual direction.'}],
                'observation': {'visible_text': 'An inversion', 'visible_scene': 'Two speakers exchange roles.', 'uncertainties': []},
                'baseline': {'broad': 'pass', 'combined': 'pass', 'calibrated': 'pass'},
                'notes': 'PRIVATE HUMAN NOTE'}
    plan = {'plan_id': 'offline', **protocol.BUDGETS,
            'folds': [{'fold': 0, **{p + '_ids': [p + '-ready', p + '-repair'] for p in ('train', 'val', 'test')}}]}
    return plan, cases


class FakeJev:
    def __init__(self, reflector):
        self.reflector = reflector
        self.calls = []

    def post(self, url, json):
        self.calls.append(json)
        state = json['state']
        if str(state.get('candidate', '')).startswith('test'):
            assert len(self.reflector.prompts) == 2  # All search finished first.
        answers = {}
        for qid, question in json['questions'].items():
            labels = question['criteria']
            choice = next(iter(labels))
            if qid == 'adequacy':
                improved = 'Check the exact inversion.' in question['instructions']['question']
                choice = 'fail' if improved and 'incomplete' in state['candidate'] else 'pass'
            answers[qid] = {'type': 'choice', 'choice': choice, 'confidence': 1.,
                            'probabilities': {label: float(label == choice) for label in labels}}
        return {'model': json['model'], 'answers': answers,
                'usage': {'input_tokens': 100, 'output_tokens': 0}}


class FakeOpenAI:
    def __init__(self):
        self.prompts = []
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        self.prompts.append(kwargs['input'])
        prompt = kwargs['input']
        for forbidden in ('PRIVATE HUMAN NOTE', 'val complete', 'val incomplete', 'test complete', 'test incomplete'):
            assert forbidden not in prompt
        assert 'train complete' in prompt and 'train incomplete' in prompt
        proposed = copy.deepcopy(policy.SEED_POLICY)
        proposed['verdict_instruction'] += ' Check the exact inversion.'
        return {'model': kwargs['model'], 'service_tier': 'default', 'status': 'completed',
                'output_text': '```json\n' + json.dumps(proposed) + '\n```',
                'usage': {'input_tokens': 100, 'output_tokens': 200}}


def test_installed_gepa_search_and_final_replay_without_credentials(tmp_path, monkeypatch):
    plan, cases = fixture_cases()
    reflection = FakeOpenAI()
    jev = FakeJev(reflection)
    monkeypatch.setattr(protocol, 'load', lambda root: (plan, cases))
    monkeypatch.setattr(run, 'check_execution', lambda root: {'max_proposals_per_fold': 2,
        'max_metric_calls_per_fold': 50, 'reflection_minibatch_size': 2})
    monkeypatch.setattr(protocol, 'summarize', lambda cases, records: {
        'decisions': [{k: r[k] for k in ('case_id', 'method', 'prediction')} for r in records]})
    monkeypatch.setattr(run, 'ProviderStore', lambda root, plan, **kwargs:
                        ProviderStore(root, plan, openai_client=reflection, jev_client=jev))
    report = run.run(tmp_path)
    assert report['status'] == 'complete'
    by_key = {(r['method'], r['case_id']): r['prediction'] for r in report['decisions']}
    assert by_key['seed', 'test-repair'] == 'pass'
    assert by_key['optimized', 'test-repair'] == 'fail'
    assert by_key['optimized', 'test-ready'] == 'pass'
    assert len(reflection.prompts) == 2
    assert 'PRIVATE HUMAN NOTE' not in json.dumps(jev.calls)
    # Real credential-free store: replay must resolve only verified cached calls.
    monkeypatch.setattr(run, 'ProviderStore', ProviderStore)
    checked = run.replay(tmp_path)
    assert checked['status'] == 'verified_replay' and checked['final_decisions'] == 4
    cached = next((tmp_path / 'evaluations').glob('*.json'))
    cached.write_text(cached.read_text().replace('pass', 'fail'))
    with pytest.raises(ValueError, match='cache changed'):
        run.replay(tmp_path)


def test_real_evaluation_cap_reserves_final_and_bad_policy_never_dispatches(tmp_path):
    plan, cases = fixture_cases()
    plan.update(max_case_evaluations=1, final_evaluation_reserve=1)
    class NoCalls:
        def jev(self, *args):
            pytest.fail('Provider must not be called')
    evaluations = run.Evaluations(tmp_path, plan, cases, NoCalls())
    example = {'case_id': 'train-ready', 'partition': 'train', 'weight': 1}
    with pytest.raises(BudgetStop, match='ceiling'):
        evaluations.evaluate(policy.SEED_POLICY, example)
    with pytest.raises(ValueError, match='schema'):
        evaluations.evaluate({'bad': 'policy'}, example)
    assert not (tmp_path / 'evaluations.json').exists()


def test_gepa_cannot_swallow_invalid_reflection_and_continue_paid_calls(tmp_path, monkeypatch):
    plan, cases = fixture_cases()
    reflection = FakeOpenAI()
    original = reflection.create
    def invalid(**kwargs):
        result = original(**kwargs)
        result['output_text'] = '```json\n{"invalid": true}\n```'
        return result
    reflection.responses.create = invalid
    jev = FakeJev(reflection)
    monkeypatch.setattr(protocol, 'load', lambda root: (plan, cases))
    monkeypatch.setattr(run, 'check_execution', lambda root: {'max_proposals_per_fold': 2,
        'max_metric_calls_per_fold': 50, 'reflection_minibatch_size': 2})
    monkeypatch.setattr(run, 'ProviderStore', lambda root, plan, **kwargs:
                        ProviderStore(root, plan, openai_client=reflection, jev_client=jev))
    with pytest.raises(BudgetStop, match='Reflection aborted'):
        run.run(tmp_path)
    assert len(reflection.prompts) == 1
    assert not (tmp_path / 'complete.json').exists()
    assert not (tmp_path / 'search/0/frozen.json').exists()
    assert json.loads((tmp_path / 'partial.json').read_text())['status'] == 'partial'


def test_balanced_sampler_is_training_only_and_prefers_paired_family():
    from gepa.core.data_loader import ListDataLoader
    plan, cases = fixture_cases()
    cases['train-ready']['group_id'] = cases['train-repair']['group_id']
    train, val, _ = protocol.example_sets(plan, cases, 0)
    sampler = run.BalancedTrainingSampler(train, cases, 4001)
    loader = ListDataLoader(train)
    picked = loader.fetch(sampler.next_minibatch_ids(loader, None))
    assert {e['case_id'] for e in picked} == {'train-ready', 'train-repair'}
    with pytest.raises(ValueError, match='different examples'):
        sampler.next_minibatch_ids(ListDataLoader(val), None)


def test_selection_preserves_ready_retention_before_repair_score():
    plan, cases = fixture_cases()
    _, val, _ = protocol.example_sets(plan, cases, 0)
    candidates = [dict(policy.SEED_POLICY, essential_threshold=v) for v in (.7, .8, .9)]
    class Decisions:
        def evaluate(self, candidate, example):
            if candidate['essential_threshold'] == .8:
                return {'prediction': 'fail'}  # Catches repair by rejecting everything.
            if candidate['essential_threshold'] == .9:
                return {'prediction': 'pass' if example['case_id'].endswith('ready') else 'fail'}
            return {'prediction': 'pass'}
    winner, trace = run.select_candidate(candidates, val, cases, Decisions())
    assert winner == candidates[2] and trace['selected_index'] == 2
