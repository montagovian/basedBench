"""Frozen question compiler and deterministic evidence-pack selection for Jev review.

Only saved observations and exact comment text cross the provider boundary. Scores
rank evidence for a reader; they do not verify a claim or choose the true joke.
"""
from __future__ import annotations

import math
import re
from typing import Any

from basedbench.pipeline.jev_decomposition_questions import MODEL, validate_request

COMMENT_QUESTIONS = {
    'useful': 'Does this comment contribute a concrete referent, decoding step, relation, or useful source pointer for understanding the meme?',
    'decodes': 'Does this comment explain a specific setup, reference, implication, contrast, inversion, wordplay, or other step needed to get the meme’s joke?',
    'riff': 'Is this comment primarily making another joke or reacting, rather than explaining or pointing to the meme’s joke?',
    'pointer': 'Does this comment give a potentially useful source pointer for a reference, without treating that pointer as verified?',
    'alternative': 'Does this comment offer a materially different plausible reading of the meme?',
}
PAIR_QUESTIONS = {
    'same': 'Do these comments convey substantially the same decoding information about this meme?',
    'conflict': 'Do these comments make incompatible claims about how to understand this meme?',
}
_WORDS = re.compile(r'\S+')
_SENTENCE_END = re.compile(r'[.!?](?:[\"\'”’)]*)?(?=\s|$)')


def _comments(case: dict) -> list[dict[str, str]]:
    raw = case['comments']
    if not isinstance(raw, list) or len(raw) > 20:
        raise ValueError('Expected at most 20 comments')
    comments = []
    for comment in raw:
        if not isinstance(comment, dict) or not isinstance(comment.get('id'), str) or not isinstance(comment.get('text'), str):
            raise ValueError('Comments require string ID and text')
        comments.append({'id': comment['id'], 'text': comment['text']})
    if len({c['id'] for c in comments}) != len(comments):
        raise ValueError('Duplicate comment IDs')
    return comments


def _state(case: dict) -> dict:
    observation = case['observation']
    if (not isinstance(observation, dict)
            or not isinstance(observation.get('visible_text'), str)
            or not isinstance(observation.get('visible_scene'), str)
            or not isinstance(observation.get('uncertainties'), list)
            or any(not isinstance(v, str) for v in observation['uncertainties'])):
        raise ValueError('Invalid saved image observation')
    return {
        'observation': {key: observation[key] for key in ('visible_text', 'visible_scene', 'uncertainties')},
        'comments': _comments(case),
    }


def _batches(state: dict, questions: dict[str, dict]) -> list[dict]:
    """Greedily include every question, respecting all frozen request guards."""
    batches = []
    current: dict[str, dict] = {}
    for qid, question in questions.items():
        trial = {**current, qid: question}
        body = {'model': MODEL, 'state': state, 'questions': trial}
        try:
            validate_request(body)
        except ValueError as exc:
            if not current:
                raise ValueError(f'Question {qid} cannot fit Jev request limits') from exc
            batches.append({'model': MODEL, 'state': state, 'questions': current})
            current = {qid: question}
            validate_request({'model': MODEL, 'state': state, 'questions': current})
        else:
            current = trial
    if current:
        batches.append({'model': MODEL, 'state': state, 'questions': current})
    return batches


def comment_requests(case: dict) -> list[dict]:
    state = _state(case)
    questions = {}
    for index, comment in enumerate(state['comments']):
        for key, instruction in COMMENT_QUESTIONS.items():
            questions[f'{key}_c{index}'] = {
                'type': 'noul',
                'instructions': {'question': instruction, 'comment_id': comment['id'], 'comment_text': comment['text']},
            }
    return _batches(state, questions)


def pair_requests(case: dict) -> list[dict]:
    state = _state(case)
    questions = {}
    for left, first in enumerate(state['comments']):
        for right in range(left + 1, len(state['comments'])):
            second = state['comments'][right]
            for key, instruction in PAIR_QUESTIONS.items():
                questions[f'{key}_{left}_{right}'] = {
                    'type': 'noul',
                    'instructions': {
                        'question': instruction,
                        'first_comment_id': first['id'], 'first_comment_text': first['text'],
                        'second_comment_id': second['id'], 'second_comment_text': second['text'],
                    },
                }
    return _batches(state, questions)


def word_budget(case: dict) -> int:
    total = sum(len(_WORDS.findall(comment['text'])) for comment in _comments(case))
    return min(250, max(1, (total + 1) // 2))


def _pack(comments: list[dict], indices: list[int], budget: int) -> dict:
    excerpts = []
    used = 0
    first_nonempty = next((index for index in indices if _WORDS.search(comments[index]['text'])), None)
    for index in indices:
        comment = comments[index]
        source = comment['text']
        matches = list(_WORDS.finditer(source))
        if not matches:
            continue
        remaining = budget - used
        if remaining <= 0:
            break
        if len(matches) <= remaining:
            end = len(source)
            count = len(matches)
        elif index == first_nonempty:
            # Prefer the longest sequence of whole sentences. If the first
            # sentence exceeds the budget, preserve exactly the first words.
            ends = [m.end() for m in _SENTENCE_END.finditer(source)
                    if len(_WORDS.findall(source[:m.end()])) <= remaining]
            end = max(ends, default=matches[remaining - 1].end())
            count = len(_WORDS.findall(source[:end]))
        else:
            continue
        excerpts.append({'comment_id': comment['id'], 'start': 0, 'end': end,
                         'text': source[:end], 'partial': end < len(source)})
        used += count
    return {'excerpts': excerpts, 'word_count': used, 'budget_words': budget,
            'selected_ids': [excerpt['comment_id'] for excerpt in excerpts]}


def _probability(value: Any, key: str) -> float:
    if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f'Invalid probability for {key}')
    return float(value)


def _score_table(comments: list[dict], scores: dict) -> tuple[list[dict], dict[tuple[int, int], dict]]:
    if not isinstance(scores, dict):
        raise ValueError('Scores must be a mapping')
    expected = {f'{key}_c{i}' for i in range(len(comments)) for key in COMMENT_QUESTIONS}
    expected |= {f'{key}_{i}_{j}' for i in range(len(comments)) for j in range(i + 1, len(comments)) for key in PAIR_QUESTIONS}
    if set(scores) != expected:
        raise ValueError('Scores must contain exactly the expected question IDs')
    numeric = {key: _probability(value, key) for key, value in scores.items()}
    table = []
    for index, comment in enumerate(comments):
        item = {'comment_id': comment['id'], 'index': index}
        for key in COMMENT_QUESTIONS:
            item[key] = numeric[f'{key}_c{index}']
        item['utility'] = (.60 * item['useful'] + .25 * item['decodes']
                           + .15 * item['pointer'] - .35 * item['riff'])
        table.append(item)
    pairs = {(i, j): {'same_claim': numeric[f'same_{i}_{j}'],
                      'conflicting': numeric[f'conflict_{i}_{j}']}
             for i in range(len(comments)) for j in range(i + 1, len(comments))}
    return table, pairs


def _collate(table: list[dict], pairs: dict, ranked: list[int]) -> tuple[list[int], list[dict]]:
    groups: list[list[int]] = []
    for index in ranked:
        for group in groups:
            if all(pairs[min(index, member), max(index, member)]['same_claim'] >= .8
                   and pairs[min(index, member), max(index, member)]['conflicting'] < .65
                   for member in group):
                group.append(index)
                break
        else:
            groups.append([index])
    representatives = [group[0] for group in groups]
    ordered = []
    while representatives:
        def novelty(index: int) -> float:
            maximum = max((pairs[min(index, chosen), max(index, chosen)]['same_claim']
                           for chosen in ordered), default=0.0)
            return table[index]['utility'] - .25 * maximum
        chosen = min(representatives, key=lambda i: (-novelty(i), i))
        representatives.remove(chosen)
        ordered.append(chosen)
    inspection = [{'representative_id': table[group[0]]['comment_id'],
                   'member_ids': [table[i]['comment_id'] for i in group],
                   'duplicate_ids': [table[i]['comment_id'] for i in group[1:]]}
                  for group in groups]
    return ordered, inspection


def build_packs(case: dict, scores: dict | None = None) -> dict[str, dict]:
    """Build equal-budget source excerpts; None denotes family-level abstention."""
    comments = _comments(case)
    budget = word_budget(case)
    order = {'status': 'completed', **_pack(comments, list(range(len(comments))), budget)}
    if scores is None:
        unavailable = {'status': 'unavailable', 'reason': 'model_abstention',
                       'excerpts': [], 'word_count': 0, 'budget_words': budget,
                       'selected_ids': []}
        return {'order': order, 'rank': unavailable.copy(), 'collate': unavailable.copy()}
    table, pairs = _score_table(comments, scores)
    ranked = sorted(range(len(comments)), key=lambda i: (-table[i]['utility'], i))
    rank = {'status': 'completed', **_pack(comments, ranked, budget),
            'ranking': [table[i] for i in ranked]}
    collated, groups = _collate(table, pairs, ranked)
    sections = {
        'source_pointers': [table[i]['comment_id'] for i in collated if table[i]['pointer'] >= .6],
        'alternative_readings': [table[i]['comment_id'] for i in collated if table[i]['alternative'] >= .6],
    }
    pair_details = [{'first_id': comments[i]['id'], 'second_id': comments[j]['id'], **values}
                    for (i, j), values in sorted(pairs.items())]
    collate = {'status': 'completed', **_pack(comments, collated, budget),
               'ranking': [table[i] for i in collated], 'groups': groups,
               'pairs': pair_details, 'sections': sections}
    return {'order': order, 'rank': rank, 'collate': collate}
