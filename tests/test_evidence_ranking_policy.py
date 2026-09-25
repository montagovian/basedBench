"""Focused tests for the frozen evidence-ranking contract."""
from __future__ import annotations

import math

import pytest

from basedbench.pipeline.evidence_ranking_policy import (
    build_packs, comment_requests, pair_requests, word_budget,
)
from basedbench.pipeline.jev_decomposition_questions import validate_request


def case_with(*texts: str) -> dict:
    return {
        'case_id': 'private-case', 'group_id': 'private-group',
        'human_label': 'PRIVATE GOLD', 'reference_explanation': 'PRIVATE REFERENCE',
        'notes': 'PRIVATE NOTES', 'input': {'explanation': 'PRIVATE CANDIDATE'},
        'image_path': '/private/image.png',
        'observation': {'visible_text': 'A sign', 'visible_scene': 'A person points',
                        'uncertainties': ['Maybe a hat'], 'private_note': 'PRIVATE OBS NOTE'},
        'comments': [{'id': f'id-{i}', 'text': text, 'votes': 9000, 'human_note': 'PRIVATE COMMENT NOTE'}
                     for i, text in enumerate(texts)],
    }


def scores_for(case: dict, overrides: dict | None = None) -> dict:
    n = len(case['comments'])
    scores = {f'{key}_c{i}': 0.0 for i in range(n)
              for key in ('useful', 'decodes', 'riff', 'pointer', 'alternative')}
    scores.update({f'{key}_{i}_{j}': 0.0 for i in range(n) for j in range(i + 1, n)
                   for key in ('same', 'conflict')})
    scores.update(overrides or {})
    return scores


def test_questions_exact_and_blind() -> None:
    case = case_with('One decoding clue.', 'A different possible clue.')
    bodies = comment_requests(case) + pair_requests(case)
    ids = [qid for body in bodies for qid in body['questions']]
    assert len(ids) == 12
    assert set(ids) == ({f'{key}_c{i}' for i in range(2)
                         for key in ('useful', 'decodes', 'riff', 'pointer', 'alternative')}
                        | {'same_0_1', 'conflict_0_1'})
    assert all(question['type'] == 'noul' for body in bodies
               for question in body['questions'].values())
    assert all(validate_request(body)['question_count'] <= 96 for body in bodies)
    joined = repr(bodies)
    for private in ('PRIVATE', '/private/image.png', '9000', 'private-case'):
        assert private not in joined
    assert 'One decoding clue.' in joined
    assert case['comments'][0]['text'] == 'One decoding clue.'


def test_greedy_batches_keep_every_question() -> None:
    case = case_with(*('comment ' + str(i) for i in range(20)))
    comment_bodies = comment_requests(case)
    pair_bodies = pair_requests(case)
    assert [len(body['questions']) for body in comment_bodies] == [96, 4]
    assert len(pair_bodies) > 1
    assert sum(len(body['questions']) for body in pair_bodies) == 380
    assert len({qid for body in pair_bodies for qid in body['questions']}) == 380
    assert all(validate_request(body) for body in comment_bodies + pair_bodies)


def test_exact_budget_offsets_and_later_skip() -> None:
    case = case_with('One two three four five six.', 'small clue.', 'Longer three words here.')
    assert word_budget(case) == 6
    packs = build_packs(case, scores_for(case))
    for pack in packs.values():
        assert pack['budget_words'] == 6
        assert pack['word_count'] <= 6
        assert pack['word_count'] == sum(len(e['text'].split()) for e in pack['excerpts'])
        for excerpt in pack['excerpts']:
            source = next(c['text'] for c in case['comments'] if c['id'] == excerpt['comment_id'])
            assert source[excerpt['start']:excerpt['end']] == excerpt['text']
            assert excerpt['partial'] == (excerpt['end'] < len(source))
    assert packs['order']['selected_ids'] == ['id-0']


def test_later_unfitting_comment_is_skipped_without_truncation() -> None:
    case = case_with('First clue', 'Second longer clue here', 'Last')
    assert word_budget(case) == 4
    pack = build_packs(case)['order']
    assert pack['selected_ids'] == ['id-0', 'id-2']
    assert pack['word_count'] == 3
    assert all(not excerpt['partial'] for excerpt in pack['excerpts'])


def test_first_comment_sentence_prefix_and_word_fallback() -> None:
    sentence = case_with('One two. Three four. Five six seven eight nine ten.')
    pack = build_packs(sentence)['order']
    assert word_budget(sentence) == 5
    assert pack['excerpts'][0]['text'] == 'One two. Three four.'
    assert pack['excerpts'][0]['partial'] is True
    fallback = case_with('One two three four five six seven eight nine ten')
    excerpt = build_packs(fallback)['order']['excerpts'][0]
    assert excerpt['text'] == 'One two three four five'
    assert excerpt['end'] == len(excerpt['text'])


def test_complete_link_nontransitivity_and_conflict_preservation() -> None:
    case = case_with('Alpha', 'Paraphrase', 'Different')
    scores = scores_for(case, {
        'useful_c0': 1, 'useful_c1': .9, 'useful_c2': .8,
        'same_0_1': .95, 'same_1_2': .95, 'same_0_2': .1,
        'conflict_0_2': .9,
    })
    pack = build_packs(case, scores)['collate']
    assert pack['selected_ids'] == ['id-0', 'id-2']
    assert pack['groups'] == [
        {'representative_id': 'id-0', 'member_ids': ['id-0', 'id-1'], 'duplicate_ids': ['id-1']},
        {'representative_id': 'id-2', 'member_ids': ['id-2'], 'duplicate_ids': []},
    ]
    assert any(p['first_id'] == 'id-0' and p['second_id'] == 'id-2'
               and p['conflicting'] == .9 for p in pack['pairs'])


def test_conflicting_pair_never_merges_even_when_same_is_high() -> None:
    case = case_with('First clue', 'Second clue')
    scores = scores_for(case, {'same_0_1': 1, 'conflict_0_1': .65})
    assert len(build_packs(case, scores)['collate']['groups']) == 2


def test_rank_utility_novelty_and_inspection_sections() -> None:
    case = case_with('first clue', 'second clue', 'source pointer')
    scores = scores_for(case, {
        'useful_c0': 1, 'useful_c1': .8, 'useful_c2': .7,
        'same_0_1': .7, 'same_0_2': 0,
        'pointer_c2': .9, 'alternative_c1': .8,
    })
    packs = build_packs(case, scores)
    assert packs['rank']['ranking'][0]['utility'] == pytest.approx(.6)
    assert packs['collate']['ranking'][0]['comment_id'] == 'id-0'
    assert packs['collate']['sections'] == {
        'source_pointers': ['id-2'], 'alternative_readings': ['id-1']}


def test_model_abstention_and_bad_scores() -> None:
    case = case_with('One clue', 'Another clue')
    packs = build_packs(case)
    assert packs['order']['status'] == 'completed'
    for arm in ('rank', 'collate'):
        assert packs[arm] == {'status': 'unavailable', 'reason': 'model_abstention',
                              'excerpts': [], 'word_count': 0, 'budget_words': 2,
                              'selected_ids': []}
    with pytest.raises(ValueError, match='exactly'):
        build_packs(case, {'useful_c0': .5})
    with pytest.raises(ValueError, match='Invalid probability'):
        build_packs(case, scores_for(case, {'useful_c0': math.nan}))


def test_tie_breaks_use_original_index_and_inputs_are_immutable() -> None:
    case = case_with('one', 'two', 'three', 'four')
    scores = scores_for(case)
    before = repr(case), repr(scores)
    packs = build_packs(case, scores)
    assert [row['index'] for row in packs['rank']['ranking']] == [0, 1, 2, 3]
    assert (repr(case), repr(scores)) == before
