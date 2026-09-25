"""Fixed comment-selection questions and whole-source reading lists."""
from __future__ import annotations

import math

import pytest

from basedbench.pipeline.comment_selection_policy import build_lists, comment_requests, pair_requests
from basedbench.pipeline.jev_decomposition_questions import validate_request


FEATURES = ('relevant', 'explains', 'complete', 'context', 'pointer', 'reaction', 'riff')


def case_with(*texts: str) -> dict:
    return {
        'case_id': 'SECRET CASE', 'reference_explanation': 'SECRET GOLD',
        'human_notes': 'SECRET NOTES', 'image_path': '/SECRET/IMAGE',
        'observation': {'visible_text': 'visible letters', 'visible_scene': 'visible scene',
                        'uncertainties': ['uncertain'], 'private_note': 'SECRET OBSERVATION'},
        'comments': [{'id': f'id-{i}', 'text': text, 'votes': 99999,
                      'private_note': 'SECRET COMMENT'} for i, text in enumerate(texts)],
    }


def baseline(case: dict, order: list[int] | None = None) -> dict:
    order = list(range(len(case['comments']))) if order is None else order
    return {'status': 'completed', 'ranking': [
        {'index': i, 'comment_id': case['comments'][i]['id'], 'utility': len(order) - pos}
        for pos, i in enumerate(order)]}


def scores_for(case: dict, overrides: dict | None = None) -> dict:
    n = len(case['comments'])
    scores = {f'{feature}_c{i}': (1.0 if feature == 'relevant' else 0.0)
              for i in range(n) for feature in FEATURES}
    scores.update({f'first_{i}_{j}': .5 for i in range(n) for j in range(n) if i != j})
    scores.update(overrides or {})
    return scores


def test_questions_are_exact_blind_and_within_request_limits() -> None:
    case = case_with('A decoding clue.', 'A useful overlapping explanation.')
    bodies = comment_requests(case) + pair_requests(case)
    ids = [qid for body in bodies for qid in body['questions']]
    assert set(ids) == ({f'{feature}_c{i}' for i in range(2) for feature in FEATURES}
                        | {'first_0_1', 'first_1_0'})
    assert len(ids) == 16
    assert all(question['type'] == 'noul' for body in bodies
               for question in body['questions'].values())
    assert all(validate_request(body)['question_count'] <= 96 for body in bodies)
    joined = repr(bodies)
    assert 'A decoding clue.' in joined and 'visible letters' in joined
    assert all(secret not in joined for secret in ('SECRET', '99999'))
    assert 'first comment' in joined and 'intended joke' in joined


def test_questions_compile_every_direction_before_filtering() -> None:
    case = case_with(*(f'comment {i}' for i in range(20)))
    pointwise = comment_requests(case)
    pairwise = pair_requests(case)
    assert sum(len(body['questions']) for body in pointwise) == 140
    assert sum(len(body['questions']) for body in pairwise) == 380
    assert len({qid for body in pairwise for qid in body['questions']}) == 380
    assert all(validate_request(body) for body in pointwise + pairwise)


def test_baseline_uses_full_v1_rank_order_and_whole_text() -> None:
    case = case_with('One two three', '  ', 'A ' * 300, 'same joke explained', 'Another explanation')
    lists = build_lists(case, baseline(case, [4, 2, 0, 3, 1]))
    pack = lists['baseline']
    assert pack['retained_ids'] == ['id-4', 'id-2', 'id-0', 'id-3']
    assert pack['selected_ids'] == ['id-4', 'id-2', 'id-0']
    assert pack['excluded_ids'] == ['id-1']
    assert pack['excerpts'][1] == {'comment_id': 'id-2', 'text': case['comments'][2]['text'],
                                   'start': 0, 'end': len(case['comments'][2]['text']), 'partial': False}
    assert [e['comment_id'] for e in pack['extra_excerpts']] == ['id-3']
    assert pack['word_count'] == 2 + 300 + 3
    assert pack['total_word_count'] == pack['word_count'] + 3
    assert lists['pointwise']['status'] == lists['pairwise']['status'] == 'unavailable'


@pytest.mark.parametrize('bad', [
    {'status': 'unavailable', 'ranking': []},
    {'status': 'completed', 'ranking': []},
    {'status': 'completed', 'ranking': [{'comment_id': 'id-0', 'index': 1},
                                      {'comment_id': 'id-1', 'index': 1}]},
    {'status': 'completed', 'ranking': [{'comment_id': 'id-0', 'index': 0},
                                      {'comment_id': 'wrong', 'index': 1}]},
])
def test_baseline_requires_exact_id_index_coverage(bad: dict) -> None:
    with pytest.raises(ValueError, match='Baseline'):
        build_lists(case_with('one', 'two'), bad)


def test_empty_singleton_and_abstention() -> None:
    empty = case_with()
    assert comment_requests(empty) == pair_requests(empty) == []
    assert all(pack['retained_ids'] == [] for pack in build_lists(empty, baseline(empty), {}).values())
    singleton = case_with('One good explanation.')
    output = build_lists(singleton, baseline(singleton), scores_for(singleton))
    assert output['pairwise']['ranking'][0]['borda'] == .5
    assert output['pairwise']['selected_ids'] == ['id-0']
    unavailable = build_lists(singleton, baseline(singleton), None)
    assert unavailable['baseline']['status'] == 'completed'
    assert unavailable['pointwise']['reason'] == 'model_abstention'
    assert unavailable['pairwise']['selected_ids'] == []


def test_filter_preserves_overlapping_useful_explanations_without_padding() -> None:
    case = case_with('Same joke, clear explanation.', 'Another clear explanation of same joke.',
                     'A vague topical reaction.', 'Noisy riff.', '  ')
    scores = scores_for(case, {'complete_c0': 1, 'explains_c0': 1,
                               'complete_c1': 1, 'explains_c1': 1,
                               'relevant_c2': .59, 'riff_c3': .70})
    output = build_lists(case, baseline(case), scores)
    for arm in ('pointwise', 'pairwise'):
        pack = output[arm]
        assert pack['retained_ids'] == ['id-0', 'id-1']
        assert pack['selected_ids'] == ['id-0', 'id-1']
        assert pack['excluded_ids'] == ['id-2', 'id-3', 'id-4']
        assert pack['extra_excerpts'] == []
        assert len(pack['ranking']) == 5  # raw features for excluded comments remain inspectable


def test_reversal_borda_and_tie_breaks() -> None:
    case = case_with('A', 'B', 'C')
    scores = scores_for(case, {
        'first_0_1': 0, 'first_1_0': 1,
        'first_0_2': 0, 'first_2_0': 1,
        'first_1_2': 1, 'first_2_1': 0,
    })
    output = build_lists(case, baseline(case), scores)
    assert output['pointwise']['retained_ids'] == ['id-0', 'id-1', 'id-2']
    assert output['pairwise']['retained_ids'] == ['id-1', 'id-2', 'id-0']
    pair = output['pairwise']['pairs'][0]
    assert pair['pair_score'] == 0 and pair['directional_disagreement'] == 0
    tied = scores_for(case, {'complete_c2': 1})
    assert build_lists(case, baseline(case), tied)['pairwise']['retained_ids'] == ['id-2', 'id-0', 'id-1']
    tied['first_0_1'] = 1
    tied['first_1_0'] = 1
    pair = build_lists(case, baseline(case), tied)['pairwise']['pairs'][0]
    assert pair['pair_score'] == .5 and pair['directional_disagreement'] == 1


@pytest.mark.parametrize('override', [
    {'relevant_c0': math.nan}, {'first_0_1': math.inf},
    {'complete_c1': -0.01}, {'first_1_0': 1.01}, {'riff_c0': True},
])
def test_invalid_probabilities_rejected(override: dict) -> None:
    case = case_with('one', 'two')
    with pytest.raises(ValueError, match='Invalid probability'):
        build_lists(case, baseline(case), scores_for(case, override))


def test_exact_keys_required_and_inputs_immutable() -> None:
    case = case_with('one', 'two')
    scores = scores_for(case)
    before = (repr(case), repr(scores))
    build_lists(case, baseline(case), scores)
    assert (repr(case), repr(scores)) == before
    for altered in ({key: value for key, value in scores.items() if key != 'first_1_0'},
                    {**scores, 'extra': .2}):
        with pytest.raises(ValueError, match='exactly'):
            build_lists(case, baseline(case), altered)
