"""Bounded, source-linked Jev policy compiler for the frozen GEPA comparison.

Only the four instructions and three thresholds are optimized. All state sent
to Jev is assembled from an explicit allowlist; labels and case IDs stay local.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from . import jev_decomposition_questions as q

MAX_UNITS = 64
MAX_CASE_QUESTIONS = 384
ROLES = ('core_decoding', 'context', 'riff', 'competing', 'irrelevant', 'unclear')
NEEDS = ('essential', 'helpful', 'unrelated', 'unclear')
COVERAGE = ('covered', 'missing', 'contradicted', 'not_applicable', 'unresolved')
VERDICTS = ('pass', 'fail', 'uncertain')
AGGREGATIONS = ('hybrid', 'evidence_only', 'broad_guarded')
INSTRUCTIONS = ('role_instruction', 'need_instruction', 'coverage_instruction', 'verdict_instruction')
THRESHOLDS = ('essential_threshold', 'coverage_threshold', 'failure_threshold')
KEYS = {'version', 'aggregation', *INSTRUCTIONS, *THRESHOLDS}

SEED_POLICY = {
    'version': 1,
    'role_instruction': ('Classify what this source unit contributes to understanding the specific meme joke. '
                         'Core decoding identifies the necessary referent, setup, contrast, implication, or wordplay; '
                         'context supports that reading; a riff extends it; competing gives an alternative reading.'),
    'need_instruction': ('Independently judge whether the fact or connection in this source unit is necessary to get '
                         'the same joke. Essential can be any clearly necessary unit, even when its role is context '
                         'or competing; do not infer need solely from its role or from the candidate answer.'),
    'coverage_instruction': ('Compare this exact source unit with the unchanged candidate answer. Covered means its '
                             'joke-relevant content is captured, missing means omitted, contradicted means the answer '
                             'asserts an incompatible reading, and unresolved means the available evidence is unclear.'),
    'verdict_instruction': ('Does the unchanged candidate explanation get the same joke? Judge the concrete setup, '
                            'referents, connection and intended implication. Comments show readers recovering the joke; '
                            'do not require a theory of humor or every incidental detail.'),
    'essential_threshold': 0.70,
    'coverage_threshold': 0.70,
    'failure_threshold': 0.80,
    'aggregation': 'hybrid',
}

_FORBIDDEN = re.compile(
    r'(?i)(?:\bcase[_ -]?id\b|\bcase[_ -]?[0-9a-f]{8,}\b|'
    # Source version IDs use a short post-like stem plus a long hexadecimal
    # digest. Reject the shape, not any one memorized case or post ID.
    r'(?<![a-z0-9])[a-z0-9]{5,12}-[a-f0-9]{12,64}(?![a-z0-9])|'
    r'\b(?:lookup\s+table|case\s+mapping|subprocess)\b|'
    r'\b(?:eval|exec|open)\s*\(|\bimport\s+\w+|__\w+__|os\.system|```|<script|'
    r'\b(?:if|when)\s+case\s+[0-9a-f]{6,})'
)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    """Do not silently accept a later duplicate key as the policy value."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate policy JSON key: {key}')
        result[key] = value
    return result


def parse_policy(value: str | dict) -> dict:
    """Parse a plain canonical JSON policy, rejecting lookup/code payloads.

    Ordinary quotes, brackets and punctuation in prose are allowed. The schema
    and direct lookup/code markers are checked rather than banning punctuation.
    """
    if isinstance(value, str):
        try:
            value = json.loads(value, object_pairs_hook=_unique_object)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError('Policy must be JSON') from exc
    if not isinstance(value, dict) or set(value) != KEYS or type(value.get('version')) is not int or value['version'] != 1:
        raise ValueError('Invalid policy schema')
    for key in INSTRUCTIONS:
        instruction = value[key]
        if not isinstance(instruction, str) or not 50 <= len(instruction) <= 2500 or _FORBIDDEN.search(instruction):
            raise ValueError(f'Invalid policy instruction: {key}')
    for key in THRESHOLDS:
        threshold = value[key]
        if type(threshold) not in (float, int) or not .4 <= threshold <= .95:
            raise ValueError(f'Invalid policy threshold: {key}')
    if value['aggregation'] not in AGGREGATIONS:
        raise ValueError('Invalid aggregation')
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False))


def policy_id(policy: str | dict) -> str:
    canonical = parse_policy(policy)
    raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def _observation(case: dict) -> dict:
    obs = case.get('observation')
    if not isinstance(obs, dict):
        raise ValueError('Missing saved observation')
    # Existing validator provides the exact observation allowlist and type check.
    return q.state_for(case, obs)['observation']


def source_units(case: dict) -> list[dict]:
    """Partition comment text at newlines and sentence ends with exact offsets.

    Whitespace-only fragments have no proposition to classify. Every returned
    slice reproduces the original text at its recorded Python character offsets.
    """
    comments = case.get('comments')
    if not isinstance(comments, list):
        raise ValueError('Comments must be a list')
    units: list[dict] = []
    seen = set()
    for comment in comments:
        if not isinstance(comment, dict) or not isinstance(comment.get('id'), str) or not isinstance(comment.get('text'), str):
            raise ValueError('Malformed comment')
        cid, body = comment['id'], comment['text']
        if cid in seen:
            raise ValueError('Duplicate comment ID')
        seen.add(cid)
        boundaries = {0, len(body)}
        boundaries.update(m.end() for m in re.finditer(r'\n', body))
        boundaries.update(m.end() for m in re.finditer(r'[.!?][\"\'’”)]*(?=\s|$)', body))
        sorted_boundaries = sorted(boundaries)
        for start, end in zip(sorted_boundaries, sorted_boundaries[1:]):
            if body[start:end].strip():
                units.append({'id': f'u{len(units)}', 'comment_id': cid,
                              'start': start, 'end': end, 'text': body[start:end]})
                if len(units) > MAX_UNITS:
                    raise ValueError('Case held: more than 64 source units')
    return units


def _case_state(case: dict, *, candidate: bool) -> dict:
    comments = case['comments']
    state = {'observation': _observation(case),
             'comments': [{'id': c['id'], 'text': c['text']} for c in comments]}
    if candidate:
        answer = case['input']['explanation']
        if not isinstance(answer, str):
            raise ValueError('Candidate must be text')
        state['candidate'] = answer
    return state


def _choice(instruction: dict, labels: tuple[str, ...]) -> dict:
    return {'type': 'choice', 'instructions': instruction,
            'criteria': {label: label.replace('_', ' ') for label in labels}}


def _batches(state: dict, questions: dict) -> list[dict]:
    if len(questions) > MAX_CASE_QUESTIONS:
        raise ValueError('Case held: more than 384 questions')
    batches, current = [], {}
    for qid, question in questions.items():
        trial = {**current, qid: question}
        body = {'model': q.MODEL, 'state': state, 'questions': trial}
        try:
            q.validate_request(body)
        except ValueError as exc:
            if not current:
                raise ValueError(f'Case held: question {qid} exceeds request limit') from exc
            batches.append({'model': q.MODEL, 'state': state, 'questions': current})
            current = {qid: question}
            try:
                q.validate_request({'model': q.MODEL, 'state': state, 'questions': current})
            except ValueError as single_exc:
                raise ValueError(f'Case held: question {qid} exceeds request limit') from single_exc
        else:
            current = trial
    if current:
        batches.append({'model': q.MODEL, 'state': state, 'questions': current})
    return batches


def _expected_answers(answers: dict, keys: set[str]) -> None:
    if not isinstance(answers, dict) or set(answers) != keys:
        raise ValueError('Parsed answer IDs do not match expected units')


def _parsed_choice(answer: dict, labels: tuple[str, ...]) -> dict:
    if not isinstance(answer, dict) or set(answer) != {'choice', 'probabilities', 'confidence'}:
        raise ValueError('Expected parsed typed Choice')
    probabilities = answer['probabilities']
    if not isinstance(probabilities, dict) or set(probabilities) != set(labels):
        raise ValueError('Incorrect Choice labels')
    vals = list(probabilities.values())
    if any(type(v) not in (int, float) or not 0 <= v <= 1 for v in vals):
        raise ValueError('Invalid Choice probability')
    if not .985 <= sum(vals) <= 1.015 or answer['choice'] not in labels or probabilities[answer['choice']] < max(vals)-1e-9:
        raise ValueError('Inconsistent Choice')
    if type(answer['confidence']) not in (int, float) or not 0 <= answer['confidence'] <= 1:
        raise ValueError('Invalid Choice confidence')
    return answer


def role_requests(case: dict, policy: dict) -> list[dict]:
    policy = parse_policy(policy)
    units = source_units(case)
    state = _case_state(case, candidate=False)
    questions = {}
    for unit in units:
        anchor = {key: unit[key] for key in ('id', 'comment_id', 'start', 'end', 'text')}
        questions[f"role_{unit['id']}"] = _choice({'question': policy['role_instruction'], 'unit': anchor}, ROLES)
        questions[f"need_{unit['id']}"] = _choice({'question': policy['need_instruction'], 'unit': anchor}, NEEDS)
    return _batches(state, questions)


def coverage_requests(case: dict, policy: dict, roles: dict) -> list[dict]:
    policy = parse_policy(policy)
    units = source_units(case)
    _expected_answers(roles, {f'{prefix}_{u["id"]}' for u in units for prefix in ('role', 'need')})
    for unit in units:
        _parsed_choice(roles[f"role_{unit['id']}"], ROLES)
        _parsed_choice(roles[f"need_{unit['id']}"], NEEDS)
    state = _case_state(case, candidate=True)
    questions = {}
    for unit in units:
        anchor = {key: unit[key] for key in ('id', 'comment_id', 'start', 'end', 'text')}
        questions[f"coverage_{unit['id']}"] = _choice(
            {'question': policy['coverage_instruction'], 'unit': anchor,
             'role': roles[f"role_{unit['id']}"]['choice'],
             'need': roles[f"need_{unit['id']}"]['choice']}, COVERAGE)
    return _batches(state, questions)


def verdict_request(case: dict, policy: dict, roles: dict, coverage: dict) -> dict:
    policy = parse_policy(policy)
    units = source_units(case)
    _expected_answers(roles, {f'{prefix}_{u["id"]}' for u in units for prefix in ('role', 'need')})
    _expected_answers(coverage, {f'coverage_{u["id"]}' for u in units})
    trace = []
    for unit in units:
        role = _parsed_choice(roles[f"role_{unit['id']}"], ROLES)
        need = _parsed_choice(roles[f"need_{unit['id']}"], NEEDS)
        covered = _parsed_choice(coverage[f"coverage_{unit['id']}"], COVERAGE)
        # The full comment is already in state. Offsets recover the exact unit;
        # pass the choices and decision-relevant probabilities once. The full
        # parsed distributions remain in the local decide() trace for replay.
        trace.append({'unit': {key: unit[key] for key in ('id', 'comment_id', 'start', 'end')},
                      'role': role['choice'], 'need': need['choice'],
                      'coverage': covered['choice'],
                      'p_essential': need['probabilities']['essential'],
                      'p_covered': covered['probabilities']['covered'],
                      'p_missing': covered['probabilities']['missing'],
                      'p_contradicted': covered['probabilities']['contradicted']})
    state = _case_state(case, candidate=True)
    state['trace'] = trace
    question = _choice({'question': policy['verdict_instruction']}, VERDICTS)
    body = {'model': q.MODEL, 'state': state, 'questions': {'adequacy': question}}
    try:
        q.validate_request(body)
    except ValueError as exc:
        raise ValueError('Case held: verdict exceeds request limit') from exc
    if 2 * len(units) + len(units) + 1 > MAX_CASE_QUESTIONS:
        raise ValueError('Case held: more than 384 questions')
    return body


def decide(case: dict, policy: dict, roles: dict, coverage: dict, verdict: dict) -> dict:
    """Combine native adequacy and source coverage without a source quota.

    Strong essential missing/contradicted evidence fails hybrid/evidence_only;
    hybrid pass needs native pass and every essential unit covered. Unresolved
    essential content is uncertain. Native fail always fails hybrid and
    broad_guarded. Broad_guarded passes native pass absent a strong essential
    failure. Evidence_only uses essential coverage; no essential yields uncertain.
    Need probability alone establishes essentiality, even for a non-core role.
    """
    policy = parse_policy(policy)
    units = source_units(case)
    _expected_answers(roles, {f'{prefix}_{u["id"]}' for u in units for prefix in ('role', 'need')})
    _expected_answers(coverage, {f'coverage_{u["id"]}' for u in units})
    _expected_answers(verdict, {'adequacy'})
    native = _parsed_choice(verdict['adequacy'], VERDICTS)
    trace_units, essential = [], []
    for unit in units:
        role = _parsed_choice(roles[f"role_{unit['id']}"], ROLES)
        need = _parsed_choice(roles[f"need_{unit['id']}"], NEEDS)
        cv = _parsed_choice(coverage[f"coverage_{unit['id']}"], COVERAGE)
        is_essential = need['probabilities']['essential'] >= policy['essential_threshold']
        row = {'unit': unit, 'role': role, 'need': need, 'coverage': cv, 'essential': is_essential}
        trace_units.append(row)
        if is_essential:
            essential.append(row)
    strong_failure = any(max(row['coverage']['probabilities'][key] for key in ('missing', 'contradicted'))
                         >= policy['failure_threshold'] for row in essential)
    all_covered = bool(essential) and all(row['coverage']['probabilities']['covered'] >=
                                          policy['coverage_threshold'] for row in essential)
    mode = policy['aggregation']
    if mode in ('hybrid', 'broad_guarded') and native['choice'] == 'fail':
        prediction, reason = 'fail', 'native_fail'
    elif strong_failure:
        prediction, reason = 'fail', 'strong_essential_failure'
    elif mode == 'broad_guarded':
        prediction, reason = (native['choice'], 'native_pass' if native['choice'] == 'pass' else 'native_uncertain')
    elif mode == 'evidence_only':
        prediction, reason = (('pass', 'all_essential_covered') if all_covered else
                              ('uncertain', 'no_essential' if not essential else 'essential_unresolved'))
    elif native['choice'] == 'pass' and all_covered:
        prediction, reason = 'pass', 'native_and_essential_covered'
    else:
        prediction, reason = 'uncertain', 'no_essential' if not essential else 'essential_unresolved'
    return {'prediction': prediction, 'trace': {'units': trace_units, 'adequacy': native,
            'aggregation': mode, 'reason_codes': [reason], 'essential_count': len(essential)}}
