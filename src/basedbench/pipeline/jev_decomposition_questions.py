"""Frozen, typed Jev questions for whether an unchanged answer gets a meme's joke.

Question IDs and decision thresholds are part of the experiment definition. A
Noul is one local proposition; code composes them without asking for a theory of
humor or treating source support as an admission rule.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from typing import Any

MODEL = 'jev-1.13.0'
MAX_QUESTIONS = 96
MAX_STATE_AND_QUESTION_BYTES = 30_000
MAX_BODY_BYTES = 62_000
BODY_RESERVE_BYTES = 2_048

# Six independent questions in each of eight concrete error/adequacy families.
FEATURES = {
    'setup': (
        ('identifies_scene', 'Does the candidate identify the situation depicted or described in the meme?'),
        ('identifies_actors', 'Does the candidate identify the people or characters needed to understand the joke?'),
        ('identifies_roles', 'Does the candidate assign the relevant people or characters their intended roles?'),
        ('identifies_event', 'Does the candidate identify the event or action that sets up the joke?'),
        ('identifies_format', 'Does the candidate recognize a meme template when that template changes the meaning?'),
        ('identifies_text', 'Does the candidate use the meme’s visible or quoted wording where it matters?'),
    ),
    'referents': (
        ('resolves_pronoun', 'Does the candidate resolve a pronoun or indirect reference needed for the joke?'),
        ('resolves_name', 'Does the candidate identify a named person or character needed for the joke?'),
        ('resolves_media', 'Does the candidate identify a referenced film, game, show, song, or book needed for the joke?'),
        ('resolves_phrase', 'Does the candidate identify a quoted phrase or catchphrase needed for the joke?'),
        ('resolves_event', 'Does the candidate identify a referenced real or fictional event needed for the joke?'),
        ('resolves_symbol', 'Does the candidate identify a symbol, object, or visual cue needed for the joke?'),
    ),
    'decoding': (
        ('recognizes_wordplay', 'Does the candidate recognize wordplay when the joke depends on it?'),
        ('recognizes_double_meaning', 'Does the candidate recognize a double meaning when the joke depends on it?'),
        ('recognizes_visual_equivalence', 'Does the candidate recognize a visual resemblance or substitution when it drives the joke?'),
        ('recognizes_analogy', 'Does the candidate recognize the comparison the meme asks viewers to make?'),
        ('recognizes_inversion', 'Does the candidate recognize a reversal of the expected situation when present?'),
        ('recognizes_callback', 'Does the candidate recognize an earlier referenced line or event when the joke calls back to it?'),
    ),
    'connection': (
        ('connects_setup_punchline', 'Does the candidate connect the setup to the intended punchline?'),
        ('connects_text_image', 'Does the candidate connect image content to the meme wording when both matter?'),
        ('connects_reference_context', 'Does the candidate connect a cultural reference to this specific meme?'),
        ('connects_contrast', 'Does the candidate state the specific contrast the meme asks viewers to notice?'),
        ('connects_irony', 'Does the candidate state the ironic implication when irony is the joke?'),
        ('connects_consequence', 'Does the candidate state the implied consequence or outcome when that is the punchline?'),
    ),
    'contradiction': (
        ('wrong_actor', 'Does the candidate assign a key action or line to the wrong person or character?'),
        ('wrong_event', 'Does the candidate identify a different event as the basis of the joke?'),
        ('wrong_reference', 'Does the candidate substitute an unrelated cultural reference for a key one?'),
        ('wrong_direction', 'Does the candidate reverse who or what the joke is about?'),
        ('wrong_visual', 'Does the candidate misdescribe a visual detail needed for the joke?'),
        ('wrong_mechanism', 'Does the candidate explain a different contrast, inversion, or wordplay than the one in the meme?'),
    ),
    'specificity': (
        ('specific_setup', 'Does the candidate give a concrete setup rather than only naming a broad topic?'),
        ('specific_punchline', 'Does the candidate identify a concrete punchline or implication?'),
        ('specific_reference_role', 'Does the candidate say what a key reference contributes to this joke?'),
        ('specific_visual_role', 'Does the candidate say what a key visual detail contributes to this joke?'),
        ('specific_relation', 'Does the candidate explain the relation between the two things being compared?'),
        ('specific_target', 'Does the candidate identify the target of the joke when it has one?'),
    ),
    'unsupported': (
        ('invented_person', 'Does the candidate add a person or character absent from the available meme evidence?'),
        ('invented_event', 'Does the candidate assert an event absent from the available meme evidence?'),
        ('invented_quote', 'Does the candidate attribute a quote absent from the available meme evidence?'),
        ('invented_motive', 'Does the candidate assert a motive the available meme evidence does not establish?'),
        ('invented_visual', 'Does the candidate describe a visual detail absent from the available observation?'),
        ('speculative_backstory', 'Does the candidate depend on an unstated backstory to make its interpretation work?'),
    ),
    'ambiguity': (
        ('mentions_alternative', 'Does the candidate explicitly acknowledge another plausible reading of this meme?'),
        ('commits_to_reading', 'Does the candidate state a particular reading of the joke rather than only possibilities?'),
        ('leaves_key_reference_unresolved', 'Does the candidate leave a reference essential to the joke unresolved?'),
        ('leaves_punchline_unresolved', 'Does the candidate leave the central implication or punchline unresolved?'),
        ('confuses_literal_joke', 'Does the candidate stop at a literal description when the meme implies more?'),
        ('answers_different_question', 'Does the candidate explain the meme’s topic without explaining its intended joke?'),
    ),
}
FEATURE_IDS = tuple(fid for group in FEATURES.values() for fid, _ in group)
if len(FEATURE_IDS) != 48 or len(set(FEATURE_IDS)) != 48:
    raise ValueError('Atomic feature bank must contain 48 unique IDs')
POSITIVE_IDS = tuple(fid for family in ('setup', 'referents', 'decoding', 'connection', 'specificity') for fid, _ in FEATURES[family])
NEGATIVE_IDS = tuple(fid for family in ('contradiction', 'unsupported') for fid, _ in FEATURES[family])

BROAD = {
    'type': 'choice',
    'instructions': ('Does the unchanged candidate explanation get the same joke as this meme? '
                     'Judge its concrete setup, referents and intended implication. '
                     'Comments are evidence of readers’ interpretation; an image observation is fallible. '
                     'Do not require a theory of humor, every historical detail, or a source quota.'),
    'criteria': {
        # The key is a verdict label, never a credential.
        'pass': 'The answer identifies the central joke: relevant setup or reference and the intended connection or punchline.',  # nosec B105
        'fail': 'The answer misses or changes the central joke, including a wrong referent, contrast, implication, or only a literal/topic description.',
        'uncertain': 'The supplied evidence leaves a material ambiguity about whether the candidate gets the same joke.',
    },
}
MATRIX_PREDICATES = {
    'explanation': 'Does this comment substantively explain the joke rather than merely react to it?',
    'contradiction': 'Does this comment contradict a material part of the candidate’s interpretation?',
    'omission': 'Does this comment reveal a necessary decoding or punchline absent from the candidate?',
    'alternative': 'Does this comment give a materially different plausible reading of the joke?',
}
RELATION_CRITERIA = {
    'support': 'The comment directly supports this particular candidate span.',
    'contradiction': 'The comment directly contradicts this particular candidate span.',
    'no_relation': 'The comment does not establish either support or contradiction for this span.',
}


def _json_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8'))


def state_for(case: dict, observation: dict | None = None, comment_ids: list[str] | None = None) -> dict:
    """Build an explicit allowlist; never serialize a case or human metadata."""
    candidate = case['input']['explanation']
    if not isinstance(candidate, str):
        raise ValueError('Candidate must be text')
    raw_comments = case['comments']
    if not isinstance(raw_comments, list):
        raise ValueError('Comments must be a list')
    ids = [c['id'] for c in raw_comments]
    if len(ids) != len(set(ids)) or any(not isinstance(i, str) for i in ids):
        raise ValueError('Comment IDs must be unique strings')
    if comment_ids is not None:
        if len(comment_ids) != len(set(comment_ids)) or any(i not in ids for i in comment_ids):
            raise ValueError('Unknown or duplicate selected comment ID')
        keep = set(comment_ids)
        raw_comments = [c for c in raw_comments if c['id'] in keep]
    comments = []
    for comment in raw_comments:
        if not isinstance(comment['text'], str):
            raise ValueError('Comment text must be a string')
        comments.append({'id': comment['id'], 'text': comment['text']})
    state = {'candidate': candidate, 'comments': comments}
    if observation is not None:
        if not isinstance(observation, dict) or not isinstance(observation.get('visible_text'), str) or not isinstance(observation.get('visible_scene'), str) or not isinstance(observation.get('uncertainties'), list) or any(not isinstance(x, str) for x in observation['uncertainties']):
            raise ValueError('Invalid observation')
        state['observation'] = {key: observation[key] for key in ('visible_text', 'visible_scene', 'uncertainties')}
    return state


def validate_request(body: dict) -> dict:
    """Conservative deterministic context bound; return measured sizes for ledger."""
    if body.get('model') != MODEL or not isinstance(body.get('questions'), dict) or not body['questions']:
        raise ValueError('Invalid Jev request')
    if len(body['questions']) > MAX_QUESTIONS:
        raise ValueError('Too many questions')
    question_sizes = [_json_bytes(question) for question in body['questions'].values()]
    state_size = _json_bytes(body['state'])
    total_size = _json_bytes(body)
    if state_size + max(question_sizes) + BODY_RESERVE_BYTES > MAX_STATE_AND_QUESTION_BYTES:
        raise ValueError('State plus longest question exceeds conservative context bound')
    if total_size + BODY_RESERVE_BYTES > MAX_BODY_BYTES:
        raise ValueError('Request exceeds conservative total byte bound')
    return {'state_bytes': state_size, 'longest_question_bytes': max(question_sizes), 'body_bytes': total_size,
            'question_count': len(question_sizes)}


def _request(state: dict, questions: dict) -> dict:
    body = {'model': MODEL, 'state': state, 'questions': questions}
    validate_request(body)
    return body


def broad_request(state: dict) -> dict:
    return _request(state, {'adequacy': BROAD})


def atomic_request(state: dict) -> dict:
    questions = {fid: {'type': 'noul', 'instructions': instruction} for group in FEATURES.values() for fid, instruction in group}
    questions['adequacy'] = BROAD
    return _request(state, questions)


def matrix_requests(state: dict, spans: list[dict]) -> list[dict]:
    """Full-comment matrix in bounded batches; spans retain original offsets."""
    if not isinstance(spans, list):
        raise ValueError('Spans must be a list')
    candidate = state['candidate']
    for span in spans:
        if (not isinstance(span.get('id'), str) or not isinstance(span.get('text'), str)
                or type(span.get('start')) is not int or type(span.get('end')) is not int
                or not 0 <= span['start'] < span['end'] <= len(candidate)
                or candidate[span['start']:span['end']] != span['text']):
            raise ValueError('Span offsets must reproduce unchanged candidate text')
    if len({s['id'] for s in spans}) != len(spans):
        raise ValueError('Duplicate span ID')
    questions: dict[str, dict] = {}
    for ci, comment in enumerate(state['comments']):
        for predicate, instruction in MATRIX_PREDICATES.items():
            questions[f'c{ci}_{predicate}'] = {'type': 'noul', 'instructions': {'question': instruction,
                'comment_id': comment['id'], 'comment_text': comment['text']}}
        for si, span in enumerate(spans):
            questions[f's{si}_c{ci}'] = {'type': 'choice',
                'instructions': {'question': 'What is this comment’s relation to this exact candidate span?',
                                 'span_id': span['id'], 'span_text': span['text'], 'comment_id': comment['id'],
                                 'comment_text': comment['text']}, 'criteria': RELATION_CRITERIA}
    if not questions:
        return []
    batches: list[dict] = []
    current: dict[str, dict] = {}
    for qid, question in questions.items():
        trial = {**current, qid: question}
        try:
            _request(state, trial)
        except ValueError:
            if not current:
                raise ValueError(f'Matrix question {qid} cannot fit conservative context bound')
            batches.append(_request(state, current))
            current = {qid: question}
            _request(state, current)
        else:
            current = trial
    if current:
        batches.append(_request(state, current))
    return batches


def _unit(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('Expected finite probability in [0,1]')
    return float(value)


def parse_response(body: dict, response: dict) -> dict[str, dict]:
    """Reject partial, mistyped and inconsistent provider answers."""
    validate_request(body)
    if response.get('model') != MODEL or not isinstance(response.get('answers'), dict):
        raise ValueError('Wrong response model or missing answers')
    answers = response['answers']
    if set(answers) != set(body['questions']):
        raise ValueError('Answer IDs do not exactly match question IDs')
    parsed = {}
    for qid, question in body['questions'].items():
        answer = answers[qid]
        if not isinstance(answer, dict) or answer.get('type') != question['type']:
            raise ValueError(f'Wrong answer type: {qid}')
        if question['type'] == 'noul':
            parsed[qid] = {'value': _unit(answer.get('noul'))}
        elif question['type'] == 'choice':
            probabilities = answer.get('probabilities')
            criteria = question['criteria']
            if not isinstance(probabilities, dict) or set(probabilities) != set(criteria):
                raise ValueError(f'Wrong choice labels: {qid}')
            p = {key: _unit(probabilities[key]) for key in criteria}
            rounded = all(math.isclose(value * 100, round(value * 100), abs_tol=1e-8) for value in p.values())
            if not math.isclose(sum(p.values()), 1, abs_tol=.015000001 if rounded else 1e-4):
                raise ValueError(f'Invalid probability sum: {qid}')
            choice = answer.get('choice')
            if choice not in p or p[choice] < max(p.values()) - 1e-9:
                raise ValueError(f'Choice inconsistent with probabilities: {qid}')
            parsed[qid] = {'choice': choice, 'probabilities': p, 'confidence': _unit(answer.get('confidence'))}
        else:
            raise ValueError(f'Unsupported question type: {qid}')
    return parsed


def _noul(parsed: dict, qid: str) -> float:
    return _unit(parsed[qid]['value'])


def atomic_decision(parsed_atomic: dict) -> str:
    """Frozen conservative rule; no source-support or comment-count quota."""
    if not all(fid in parsed_atomic for fid in FEATURE_IDS) or 'adequacy' not in parsed_atomic:
        raise ValueError('Incomplete atomic feature vector')
    broad = parsed_atomic['adequacy']['probabilities']
    central = (_noul(parsed_atomic, 'connects_setup_punchline'),
               _noul(parsed_atomic, 'specific_punchline'),
               _noul(parsed_atomic, 'connects_contrast'))
    hard_error = max(_noul(parsed_atomic, fid) for fid in ('wrong_reference', 'wrong_direction', 'wrong_mechanism', 'leaves_punchline_unresolved', 'answers_different_question'))
    if broad['fail'] >= .8 or hard_error >= .85:
        return 'fail'
    if broad['pass'] >= .8 and max(central) >= .7 and hard_error <= .2:
        return 'pass'
    return 'uncertain'


def _matrix_scores(parsed_matrix: dict) -> tuple[dict[int, dict], dict[tuple[int, int], dict]]:
    comments: dict[int, dict] = defaultdict(dict)
    pairs = {}
    for key, answer in parsed_matrix.items():
        if key.startswith('c') and '_' in key:
            index, predicate = key[1:].split('_', 1)
            if index.isdigit() and predicate in MATRIX_PREDICATES:
                comments[int(index)][predicate] = _noul(parsed_matrix, key)
        elif key.startswith('s') and '_c' in key:
            span, comment = key[1:].split('_c', 1)
            if span.isdigit() and comment.isdigit():
                pairs[int(span), int(comment)] = answer['probabilities']
    return comments, pairs


def select_comments(state: dict, parsed_matrix: dict) -> tuple[list[str], dict]:
    """Reserve conflicting/omission/alternative evidence before filling support."""
    comments, pairs = _matrix_scores(parsed_matrix)
    n = len(state['comments'])
    if any(i >= n for i in comments) or any(ci >= n for _, ci in pairs):
        raise ValueError('Matrix contains unknown comment index')
    scores = []
    for ci, comment in enumerate(state['comments']):
        c = comments.get(ci, {})
        related = [p for (si, j), p in pairs.items() if j == ci]
        score = {
            'support': max([p['support'] for p in related] + [0]),
            'contradiction': max([p['contradiction'] for p in related] + [c.get('contradiction', 0)]),
            'omission': c.get('omission', 0),
            'alternative': c.get('alternative', 0),
            'substantive': c.get('explanation', 0),
        }
        scores.append({'id': comment['id'], 'index': ci, **score})
    selected: list[int] = []
    reasons: dict[str, str] = {}
    def reserve(category: str, limit: int) -> None:
        ranked = sorted(range(n), key=lambda i: (-scores[i][category], i))
        for i in ranked:
            if len([reason for reason in reasons.values() if reason == category]) >= limit:
                break
            if scores[i][category] < .5 or i in selected or len(selected) >= 10:
                continue
            selected.append(i)
            reasons[scores[i]['id']] = category
    for category, limit in (('contradiction', 2), ('omission', 2), ('alternative', 2), ('support', 2)):
        reserve(category, limit)
    ranked = sorted(range(n), key=lambda i: (-max(scores[i][c] for c in ('support', 'contradiction', 'omission', 'alternative', 'substantive')), i))
    for i in ranked:
        if len(selected) >= 10:
            break
        if i not in selected and max(scores[i][c] for c in ('support', 'contradiction', 'omission', 'alternative', 'substantive')) >= .5:
            selected.append(i)
            reasons[scores[i]['id']] = 'highest_remaining'
    ids = [state['comments'][i]['id'] for i in selected]
    return ids, {'scores': scores, 'reasons': reasons, 'selected_ids': ids}


MATRIX_SUMMARY_IDS = (
    'comment_count', 'span_count', 'pair_count', 'substantive_max', 'substantive_mean',
    'contradiction_max', 'contradiction_mean', 'omission_max', 'omission_mean',
    'alternative_max', 'alternative_mean', 'pair_support_max', 'pair_support_mean',
    'pair_contradiction_max', 'pair_contradiction_mean', 'pair_no_relation_mean',
    'spans_with_support', 'spans_with_contradiction', 'comments_with_support',
    'comments_with_contradiction',
)


def summarize_matrix(parsed_matrix: dict) -> dict[str, float]:
    """Stable numerical diagnostics; source support stays separate from adequacy."""
    comments, pairs = _matrix_scores(parsed_matrix)
    def maximum(values: list[float]) -> float:
        return max(values, default=0.0)
    def mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0
    result: dict[str, float] = {'comment_count': float(len(comments)),
        'span_count': float(max((si for si, _ in pairs), default=-1) + 1), 'pair_count': float(len(pairs))}
    for predicate, label in (('explanation', 'substantive'), ('contradiction', 'contradiction'),
                             ('omission', 'omission'), ('alternative', 'alternative')):
        values = [c[predicate] for c in comments.values() if predicate in c]
        result[f'{label}_max'] = maximum(values)
        result[f'{label}_mean'] = mean(values)
    for category in ('support', 'contradiction', 'no_relation'):
        values = [p[category] for p in pairs.values()]
        if category != 'no_relation':
            result[f'pair_{category}_max'] = maximum(values)
        result[f'pair_{category}_mean'] = mean(values)
    for category in ('support', 'contradiction'):
        result[f'spans_with_{category}'] = float(len({si for (si, _), p in pairs.items() if p[category] >= .5}))
        result[f'comments_with_{category}'] = float(len({ci for (_, ci), p in pairs.items() if p[category] >= .5}))
    if set(result) != set(MATRIX_SUMMARY_IDS):
        raise ValueError('Matrix summary schema drifted')
    return result
