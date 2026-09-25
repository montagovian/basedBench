"""Fixed Jev question compiler and whole-comment reading-list policy.

Requests contain saved visual observations and source comments only. The scores
are local ordering heuristics, never source verification or human labels.
"""
from __future__ import annotations

import math
import re
from typing import Any

from basedbench.pipeline.evidence_ranking_policy import _batches, _comments, _state


FEATURE_QUESTIONS = {
    'relevant': ('Does this comment provide a concrete clue to decoding this particular meme, '
                 'directly useful background, or an actionable source pointer? Broad topical similarity alone is insufficient.'),
    'explains': ('Does this comment explain a specific setup, reference, implication, contrast, '
                 'inversion, wordplay, or connection needed to get this meme’s intended joke?'),
    'complete': ('Together with the visible meme, does this comment supply the setup and connection '
                 'a reader needs to get the intended joke? A generic template name or unelaborated pointer is incomplete.'),
    'context': 'Does this comment supply background directly useful for decoding this particular meme?',
    'pointer': ('Does this comment offer an actionable source pointer for a reference in this meme? '
                'Do not treat the pointer as a verified source or a complete explanation by itself.'),
    'reaction': ('Is this comment primarily a reaction rather than a decoding clue? If it also contains '
                 'substantive explanation, do not classify it as primarily reaction.'),
    'riff': ('Is this comment primarily making another joke rather than explaining this meme’s intended joke? '
             'If it also contains substantive explanation, do not classify it as primarily a riff.'),
}
FIRST_QUESTION = ('Is the first comment a better first comment to read than the second for recovering '
                  'this particular meme’s intended joke? Prefer specific, self-contained decoding over '
                  'vague pointers, topical background, reactions, or riffs. Do not reward length, '
                  'popularity, or repetition by itself. Overlapping useful explanations remain useful.')
_WORDS = re.compile(r'\S+')


def comment_requests(case: dict) -> list[dict]:
    """Compile seven pointwise binary questions per comment."""
    state = _state(case)
    questions = {}
    for index, comment in enumerate(state['comments']):
        for feature, question in FEATURE_QUESTIONS.items():
            questions[f'{feature}_c{index}'] = {
                'type': 'noul',
                'instructions': {'question': question, 'comment_id': comment['id'],
                                 'comment_text': comment['text']},
            }
    return _batches(state, questions)


def pair_requests(case: dict) -> list[dict]:
    """Compile both directions for every unordered pair before filtering."""
    state = _state(case)
    comments = state['comments']
    questions = {}
    for first_index, first in enumerate(comments):
        for second_index, second in enumerate(comments):
            if first_index == second_index:
                continue
            questions[f'first_{first_index}_{second_index}'] = {
                'type': 'noul',
                'instructions': {
                    'question': FIRST_QUESTION,
                    'first_comment_id': first['id'], 'first_comment_text': first['text'],
                    'second_comment_id': second['id'], 'second_comment_text': second['text'],
                },
            }
    return _batches(state, questions)


def _probability(value: Any, key: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f'Invalid probability for {key}')
    return float(value)


def _score_table(comments: list[dict], scores: dict) -> tuple[list[dict], list[dict]]:
    if not isinstance(scores, dict):
        raise ValueError('Scores must be a mapping')
    size = len(comments)
    expected = {f'{feature}_c{i}' for i in range(size) for feature in FEATURE_QUESTIONS}
    expected.update(f'first_{i}_{j}' for i in range(size) for j in range(size) if i != j)
    if set(scores) != expected:
        raise ValueError('Scores must contain exactly the expected question IDs')
    numeric = {key: _probability(value, key) for key, value in scores.items()}
    table = []
    for i, comment in enumerate(comments):
        row = {'comment_id': comment['id'], 'index': i}
        row.update({feature: numeric[f'{feature}_c{i}'] for feature in FEATURE_QUESTIONS})
        noise = max(row['reaction'], row['riff'])
        row['noise'] = noise
        row['retained'] = bool(_WORDS.search(comment['text'])) and row['relevant'] >= .60 and noise < .70
        row['priority'] = (.45 * row['complete'] + .35 * row['explains']
                           + .20 * row['relevant'] - .10 * noise)
        table.append(row)
    pairs = []
    for i in range(size):
        for j in range(i + 1, size):
            forward = numeric[f'first_{i}_{j}']
            reverse = numeric[f'first_{j}_{i}']
            pairs.append({
                'first_id': comments[i]['id'], 'second_id': comments[j]['id'],
                'first_index': i, 'second_index': j,
                'first_i_j': forward, 'first_j_i': reverse,
                'pair_score': (forward + 1 - reverse) / 2,
                'directional_disagreement': abs(forward + reverse - 1),
            })
    return table, pairs


def _baseline_indices(comments: list[dict], baseline_pack: dict) -> list[int]:
    if not isinstance(baseline_pack, dict) or baseline_pack.get('status') != 'completed':
        raise ValueError('Baseline rank pack must be completed')
    ranking = baseline_pack.get('ranking')
    if not isinstance(ranking, list) or len(ranking) != len(comments):
        raise ValueError('Baseline ranking must cover every comment exactly once')
    indices = []
    for row in ranking:
        if not isinstance(row, dict) or type(row.get('index')) is not int:
            raise ValueError('Baseline ranking requires exact ID/index coverage')
        i = row['index']
        if not 0 <= i < len(comments) or row.get('comment_id') != comments[i]['id']:
            raise ValueError('Baseline ranking requires exact ID/index coverage')
        indices.append(i)
    if set(indices) != set(range(len(comments))):
        raise ValueError('Baseline ranking requires exact ID/index coverage')
    return indices


def _list(comments: list[dict], indices: list[int], *, ranking: list[dict],
          pairs: list[dict] | None = None) -> dict:
    retained = [i for i in indices if _WORDS.search(comments[i]['text'])]
    first_three = retained[:3]

    def excerpt(i: int) -> dict:
        text = comments[i]['text']
        return {'comment_id': comments[i]['id'], 'text': text, 'start': 0,
                'end': len(text), 'partial': False}

    retained_set = set(retained)
    result = {
        'status': 'completed',
        'excerpts': [excerpt(i) for i in first_three],
        'extra_excerpts': [excerpt(i) for i in retained[3:]],
        'selected_ids': [comments[i]['id'] for i in first_three],
        'retained_ids': [comments[i]['id'] for i in retained],
        'excluded_ids': [comment['id'] for i, comment in enumerate(comments) if i not in retained_set],
        'word_count': sum(len(_WORDS.findall(comments[i]['text'])) for i in first_three),
        'total_word_count': sum(len(_WORDS.findall(comments[i]['text'])) for i in retained),
        'ranking': ranking,
        'pairs': pairs or [],
    }
    return result


def _unavailable() -> dict:
    return {'status': 'unavailable', 'reason': 'model_abstention', 'excerpts': [],
            'extra_excerpts': [], 'selected_ids': [], 'retained_ids': [],
            'excluded_ids': [], 'word_count': 0, 'total_word_count': 0,
            'ranking': [], 'pairs': []}


def build_lists(case: dict, baseline_pack: dict, scores: dict | None = None) -> dict[str, dict]:
    """Create full baseline and, when scores exist, the two filtered reading lists."""
    comments = _comments(case)
    baseline_order = _baseline_indices(comments, baseline_pack)
    baseline = _list(comments, baseline_order, ranking=list(baseline_pack['ranking']))
    if scores is None:
        return {'baseline': baseline, 'pointwise': _unavailable(), 'pairwise': _unavailable()}

    table, pairs = _score_table(comments, scores)
    retained = [i for i, row in enumerate(table) if row['retained']]
    pointwise_order = sorted(retained, key=lambda i: (-table[i]['priority'], i))
    pair_scores = {(pair['first_index'], pair['second_index']): pair['pair_score'] for pair in pairs}
    for i in retained:
        if len(retained) == 1:
            table[i]['borda'] = .5
        else:
            table[i]['borda'] = sum(
                pair_scores[(i, j)] if i < j else 1 - pair_scores[(j, i)]
                for j in retained if j != i
            ) / (len(retained) - 1)
    pairwise_order = sorted(retained, key=lambda i: (-table[i]['borda'], -table[i]['priority'], i))
    excluded = [i for i in range(len(comments)) if i not in set(retained)]
    return {
        'baseline': baseline,
        'pointwise': _list(comments, pointwise_order,
                           ranking=[table[i].copy() for i in pointwise_order + excluded], pairs=pairs),
        'pairwise': _list(comments, pairwise_order,
                          ranking=[table[i].copy() for i in pairwise_order + excluded], pairs=pairs),
    }
