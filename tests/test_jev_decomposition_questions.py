import copy
import math

import pytest

from basedbench.pipeline import jev_decomposition_questions as q


def case(comments=None, answer='A setup; a punchline.'):
    return {'input': {'explanation': answer, 'comment_evidence': 'OLD PRIVATE EVIDENCE',
                      'historical_label': 'repair'},
            'comments': comments if comments is not None else [{'id': 'first', 'text': 'It is a reversal.'}],
            'human': {'quality': 'repair', 'notes': 'SECRET HUMAN NOTE'},
            'old_calls': {'body': 'SECRET OLD CALL'}, 'provenance': 'SECRET SOURCE'}


def spans(answer='A setup; a punchline.'):
    return [{'id': 's0', 'text': 'A setup', 'start': 0, 'end': 7},
            {'id': 's1', 'text': ' a punchline.', 'start': 8, 'end': len(answer)}]


def response(body, overrides=None):
    answers = {}
    for key, spec in body['questions'].items():
        answers[key] = ({'type': 'noul', 'noul': 0.5} if spec['type'] == 'noul' else
                        {'type': 'choice', 'choice': next(iter(spec['criteria'])),
                         'probabilities': {k: 1.0 if k == next(iter(spec['criteria'])) else 0.0
                                           for k in spec['criteria']}, 'confidence': 0.77})
    answers.update(overrides or {})
    return {'model': q.MODEL, 'answers': answers}


def test_48_concrete_features_and_native_requests():
    state = q.state_for(case())
    body = q.atomic_request(state)
    assert len(q.FEATURE_IDS) == 48
    assert len(body['questions']) == 49
    assert body['model'] == 'jev-1.13.0'
    assert all(body['questions'][fid]['type'] == 'noul' for fid in q.FEATURE_IDS)
    assert body['questions']['adequacy']['type'] == 'choice'
    assert set(body['questions']['adequacy']['criteria']) == {'pass', 'fail', 'uncertain'}
    assert len(q.broad_request(state)['questions']) == 1
    assert q.validate_request(body)['question_count'] == 49


def test_state_allowlist_and_focused_original_ids():
    c = case([{'id': 'a', 'text': 'A', 'label': 'SECRET'}, {'id': 'b', 'text': 'B', 'notes': 'SECRET'}])
    state = q.state_for(c, {'visible_text': 'sign', 'visible_scene': 'cat',
                           'uncertainties': ['blur'], 'human': 'SECRET'}, ['b'])
    assert state == {'candidate': 'A setup; a punchline.', 'comments': [{'id': 'b', 'text': 'B'}],
                     'observation': {'visible_text': 'sign', 'visible_scene': 'cat', 'uncertainties': ['blur']}}
    assert 'SECRET' not in str(state)
    with pytest.raises(ValueError):
        q.state_for(c, comment_ids=['missing'])
    with pytest.raises(ValueError):
        q.state_for(c, observation={'visible_text': 'x', 'visible_scene': 'y', 'uncertainties': 'wrong'})


def test_matrix_pairs_batches_and_exact_spans():
    state = q.state_for(case([{'id': f'c{i}', 'text': f'Explanation {i}'} for i in range(40)]))
    batches = q.matrix_requests(state, spans())
    assert len(batches) >= 3
    assert sum(len(b['questions']) for b in batches) == 40 * (4 + 2)
    assert len({key for b in batches for key in b['questions']}) == 240
    assert all(len(b['questions']) <= 96 for b in batches)
    assert all(q.validate_request(b)['body_bytes'] + q.BODY_RESERVE_BYTES <= q.MAX_BODY_BYTES for b in batches)
    assert batches[0]['questions']['s0_c0']['instructions']['span_text'] == 'A setup'
    assert batches[0]['questions']['s0_c0']['instructions']['comment_id'] == 'c0'
    with pytest.raises(ValueError):
        q.matrix_requests(state, [{'id': 'bad', 'text': 'Changed', 'start': 0, 'end': 7}])
    assert q.matrix_requests(q.state_for(case([])), spans()) == []


def test_context_bound_is_conservative_and_never_truncates():
    huge = q.state_for(case([{'id': 'a', 'text': 'x' * 31_000}]))
    with pytest.raises(ValueError, match='context bound'):
        q.atomic_request(huge)
    with pytest.raises(ValueError, match='context bound'):
        q.matrix_requests(huge, spans())


def test_parse_checks_identity_type_probabilities_argmax_confidence():
    body = q.broad_request(q.state_for(case()))
    parsed = q.parse_response(body, response(body))
    assert parsed['adequacy'] == {'choice': 'pass', 'probabilities': {'pass': 1, 'fail': 0, 'uncertain': 0}, 'confidence': .77}
    rounded = response(body, {'adequacy': {'type': 'choice', 'choice': 'pass',
                                           'probabilities': {'pass': .34, 'fail': .33, 'uncertain': .34}, 'confidence': .4}})
    assert q.parse_response(body, rounded)['adequacy']['confidence'] == .4
    bads = []
    bad = response(body); bad['model'] = 'jev-latest'; bads.append(bad)
    bad = response(body); bad['answers']['extra'] = {}; bads.append(bad)
    bad = response(body); bad['answers']['adequacy']['type'] = 'noul'; bads.append(bad)
    bad = response(body); bad['answers']['adequacy']['probabilities']['pass'] = math.nan; bads.append(bad)
    bad = response(body); bad['answers']['adequacy']['probabilities'] = {'pass': .2, 'fail': .7, 'uncertain': .1}; bads.append(bad)
    bad = response(body); bad['answers']['adequacy']['confidence'] = None; bads.append(bad)
    bad = response(body); bad['answers']['adequacy']['probabilities'] = {'pass': .4, 'fail': .4, 'uncertain': .4}; bads.append(bad)
    for payload in bads:
        with pytest.raises(ValueError):
            q.parse_response(body, payload)
    atomic = q.atomic_request(q.state_for(case()))
    malformed = response(atomic)
    malformed['answers'][q.FEATURE_IDS[0]]['noul'] = -1
    with pytest.raises(ValueError):
        q.parse_response(atomic, malformed)


def test_frozen_atomic_rule_distinguishes_positive_negative_uncertain():
    body = q.atomic_request(q.state_for(case()))
    parsed = q.parse_response(body, response(body))
    assert q.atomic_decision(parsed) == 'uncertain'
    good = copy.deepcopy(parsed)
    good['adequacy']['probabilities'] = {'pass': .9, 'fail': .05, 'uncertain': .05}
    good['connects_setup_punchline']['value'] = .9
    for fid in ('wrong_reference', 'wrong_direction', 'wrong_mechanism', 'leaves_punchline_unresolved', 'answers_different_question'):
        good[fid]['value'] = .1
    assert q.atomic_decision(good) == 'pass'
    bad = copy.deepcopy(good)
    bad['wrong_mechanism']['value'] = .9
    assert q.atomic_decision(bad) == 'fail'
    bad = copy.deepcopy(good)
    bad['adequacy']['probabilities'] = {'pass': .02, 'fail': .9, 'uncertain': .08}
    assert q.atomic_decision(bad) == 'fail'


def test_focus_reserves_conflicts_omissions_alternatives_and_keeps_ids():
    comments = [{'id': f'id-{i}', 'text': f'text {i}'} for i in range(12)]
    state = q.state_for(case(comments))
    matrix = {}
    for i in range(12):
        matrix[f'c{i}_explanation'] = {'value': .9 if i >= 3 else .1}
        matrix[f'c{i}_contradiction'] = {'value': .95 if i == 0 else .02}
        matrix[f'c{i}_omission'] = {'value': .96 if i == 1 else .02}
        matrix[f'c{i}_alternative'] = {'value': .94 if i == 2 else .02}
        matrix[f's0_c{i}'] = {'choice': 'no_relation', 'confidence': .5,
                              'probabilities': {'support': .05, 'contradiction': .05, 'no_relation': .9}}
    ids, meta = q.select_comments(state, matrix)
    assert len(ids) == 10
    assert {'id-0', 'id-1', 'id-2'} <= set(ids)
    assert meta['reasons']['id-0'] == 'contradiction'
    assert meta['reasons']['id-1'] == 'omission'
    assert meta['reasons']['id-2'] == 'alternative'
    assert q.state_for(case(comments), comment_ids=ids)['comments'][0] == {'id': 'id-0', 'text': 'text 0'}
    numeric = q.summarize_matrix(matrix)
    assert set(numeric) == set(q.MATRIX_SUMMARY_IDS)
    assert all(type(v) is float and math.isfinite(v) for v in numeric.values())
    assert numeric['pair_count'] == 12 and numeric['comments_with_support'] == 0
    assert q.summarize_matrix({})['pair_count'] == 0
    assert q.select_comments(q.state_for(case([])), {})[0] == []
    no_evidence = {f'c{i}_{predicate}': {'value': .01}
                   for i in range(12) for predicate in q.MATRIX_PREDICATES}
    no_evidence.update({f's0_c{i}': {'probabilities': {'support': .01, 'contradiction': .01,
                                                       'no_relation': .98}}
                        for i in range(12)})
    assert q.select_comments(state, no_evidence)[0] == []
