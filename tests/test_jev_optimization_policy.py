import copy
import json

import pytest

from basedbench.pipeline import jev_decomposition_questions as q
from basedbench.pipeline import jev_optimization_policy as p


def case(comments=None, answer='The caption reverses who is in control.'):
    return {'case_id': 'SECRET CASE ID', 'human': {'quality': 'repair', 'notes': 'SECRET NOTE'},
            'input': {'explanation': answer, 'comment_evidence': 'SECRET RAW EVIDENCE',
                      'historical_label': 'repair'},
            'comments': comments if comments is not None else
            [{'id': 'c1', 'text': 'First setup.  Second punchline!\nA callback?'}],
            'observation': {'visible_text': 'caption', 'visible_scene': 'two people',
                            'uncertainties': ['left edge blurred'], 'private_note': 'SECRET OBS NOTE'}}


def parsed(batches, *, choice=None):
    out = {}
    for body in batches:
        answers = {}
        for key, question in body['questions'].items():
            labels = tuple(question['criteria'])
            label = choice(key, labels) if choice else labels[0]
            answers[key] = {'type': 'choice', 'choice': label,
                            'probabilities': {name: float(name == label) for name in labels},
                            'confidence': .9}
        out.update(q.parse_response(body, {'model': q.MODEL, 'answers': answers}))
    return out


def outputs(row, policy=p.SEED_POLICY, *, role_choice=None, coverage_choice=None,
            verdict_choice='pass'):
    roles = parsed(p.role_requests(row, policy), choice=role_choice)
    coverage = parsed(p.coverage_requests(row, policy, roles), choice=coverage_choice)
    verdict = parsed([p.verdict_request(row, policy, roles, coverage)],
                     choice=lambda _key, _labels: verdict_choice)
    return roles, coverage, verdict


def test_policy_schema_identity_and_safe_prose():
    policy = p.parse_policy(json.dumps(p.SEED_POLICY))
    assert policy == p.SEED_POLICY
    assert p.policy_id(policy) == p.policy_id(json.dumps(policy, sort_keys=True))
    good = copy.deepcopy(policy)
    good['role_instruction'] += ' Ordinary punctuation: [this], (that); why?'
    p.parse_policy(good)
    for change in ({'version': True}, {'extra': 1}, {'essential_threshold': float('nan')},
                   {'role_instruction': 'x' * 49},
                   {'role_instruction': 'If case_id equals a saved ID, return pass. ' + 'x' * 60},
                   {'role_instruction': 'For ab12345-1234567890abcdef, mark pass. ' + 'x' * 60},
                   {'role_instruction': 'Run eval(x) before choosing. ' + 'x' * 60}):
        bad = {**policy, **change}
        with pytest.raises(ValueError):
            p.parse_policy(bad)
    # JSON duplicates must not let a proposal hide one policy behind another.
    duplicate = json.dumps(policy).replace('"version": 1', '"version": 1, "version": 1')
    with pytest.raises(ValueError, match='Duplicate'):
        p.parse_policy(duplicate)


def test_offsets_and_candidate_blind_role_state():
    row = case([{'id': 'c1', 'text': 'First setup.  Second punchline!\nA callback?'},
                {'id': 'c2', 'text': '\nAn irony.  More context.'}])
    units = p.source_units(row)
    assert [u['id'] for u in units] == [f'u{i}' for i in range(len(units))]
    assert all(next(c['text'] for c in row['comments'] if c['id'] == u['comment_id'])
               [u['start']:u['end']] == u['text'] for u in units)
    assert any(u['text'].endswith('!') for u in units)
    assert any(u['comment_id'] == 'c2' for u in units)
    bodies = p.role_requests(row, p.SEED_POLICY)
    assert bodies == p.role_requests({**row, 'input': {**row['input'],
        'explanation': 'An entirely different candidate answer.'}}, p.SEED_POLICY)
    serialized = json.dumps(bodies)
    for private in ('SECRET', row['input']['explanation'], 'case_id', 'historical_label'):
        assert private not in serialized
    assert set(k for b in bodies for k in b['questions']) == {
        f'{prefix}_{u["id"]}' for u in units for prefix in ('role', 'need')}
    assert all(q.validate_request(b)['question_count'] <= q.MAX_QUESTIONS for b in bodies)


def test_coverage_every_unit_and_strict_parser():
    row = case()
    roles, coverage, verdict = outputs(row)
    assert len(coverage) == len(p.source_units(row))
    bodies = p.coverage_requests(row, p.SEED_POLICY, roles)
    assert all(b['state']['candidate'] == row['input']['explanation'] for b in bodies)
    assert 'SECRET' not in json.dumps(bodies)
    assert p.verdict_request(row, p.SEED_POLICY, roles, coverage)['questions']['adequacy']['type'] == 'choice'
    final_state = p.verdict_request(row, p.SEED_POLICY, roles, coverage)['state']
    first = final_state['trace'][0]
    assert set(first) == {'unit', 'role', 'need', 'coverage', 'p_essential',
                          'p_covered', 'p_missing', 'p_contradicted'}
    anchor = first['unit']
    original = next(c['text'] for c in row['comments'] if c['id'] == anchor['comment_id'])
    assert original[anchor['start']:anchor['end']] == p.source_units(row)[0]['text']
    assert 'probabilities' in p.decide(row, p.SEED_POLICY, roles, coverage, verdict)['trace']['units'][0]['need']
    bad = {'model': q.MODEL, 'answers': {key: {'type': 'choice', 'choice': 'covered',
           'probabilities': {'covered': .8, 'missing': .8, 'contradicted': 0,
                             'not_applicable': 0, 'unresolved': 0}, 'confidence': .8}
           for key in bodies[0]['questions']}}
    with pytest.raises(ValueError, match='sum'):
        q.parse_response(bodies[0], bad)
    with pytest.raises(ValueError, match='IDs'):
        p.decide(row, p.SEED_POLICY, {}, coverage, verdict)


@pytest.mark.parametrize('aggregation', p.AGGREGATIONS)
def test_strong_essential_failure_overrides_pass(aggregation):
    row = case([{'id': 'c1', 'text': 'The crucial inversion.'}])
    policy = {**p.SEED_POLICY, 'aggregation': aggregation}
    roles, coverage, verdict = outputs(row, policy, coverage_choice=lambda *_: 'missing')
    assert p.decide(row, policy, roles, coverage, verdict)['prediction'] == 'fail'


def test_aggregation_native_and_essential_edges():
    row = case([{'id': 'c1', 'text': 'The crucial inversion.'}])
    roles, coverage, verdict = outputs(row, role_choice=lambda k, labels:
        'context' if k.startswith('role_') else 'essential')
    assert p.decide(row, p.SEED_POLICY, roles, coverage, verdict)['prediction'] == 'pass'
    # A clearly necessary context unit counts; role=core is not an extra gate.
    assert p.decide(row, p.SEED_POLICY, roles, coverage, verdict)['trace']['essential_count'] == 1
    failing = parsed([p.verdict_request(row, p.SEED_POLICY, roles, coverage)],
                     choice=lambda *_: 'fail')
    assert p.decide(row, p.SEED_POLICY, roles, coverage, failing)['prediction'] == 'fail'
    evidence = {**p.SEED_POLICY, 'aggregation': 'evidence_only'}
    assert p.decide(row, evidence, roles, coverage, failing)['prediction'] == 'pass'
    no_need = parsed(p.role_requests(row, evidence), choice=lambda k, labels:
        'context' if k.startswith('role_') else 'unrelated')
    assert p.decide(row, evidence, no_need, coverage, verdict)['prediction'] == 'uncertain'
    unresolved = parsed(p.coverage_requests(row, evidence, roles), choice=lambda *_: 'unresolved')
    assert p.decide(row, evidence, roles, unresolved, verdict)['prediction'] == 'uncertain'
    broad = {**p.SEED_POLICY, 'aggregation': 'broad_guarded'}
    assert p.decide(row, broad, roles, unresolved, verdict)['prediction'] == 'pass'


def test_greedy_question_limit_and_oversize_hold():
    row = case([{'id': f'c{i}', 'text': 'A detail.'} for i in range(64)])
    batches = p.role_requests(row, p.SEED_POLICY)
    assert len(batches) >= 2
    assert sum(len(b['questions']) for b in batches) == 128
    assert all(q.validate_request(b) for b in batches)
    roles = parsed(batches)
    coverage = parsed(p.coverage_requests(row, p.SEED_POLICY, roles))
    assert q.validate_request(p.verdict_request(row, p.SEED_POLICY, roles, coverage))
    with pytest.raises(ValueError, match='64 source units'):
        p.source_units(case([{'id': f'c{i}', 'text': 'A detail.'} for i in range(65)]))
    with pytest.raises(ValueError, match='held'):
        p.role_requests(case([{'id': 'big', 'text': 'X' * 31_000}]), p.SEED_POLICY)
