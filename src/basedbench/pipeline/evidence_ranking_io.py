"""Private, durable Jev IO for the capped evidence-ranking experiment.

The request is checkpointed with its full reservation before dispatch. An
unsettled checkpoint is never dispatched again, including after a crash.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from basedbench.pipeline import jev_decomposition_questions as questions

JEV_URL = 'https://api.typesafe.ai/v1/systemone'
MODEL = 'jev-1.13.0'
RESERVE_USD = 64_000 * .042 / 1_000_000
DEFAULTS = {'budget_usd': 1, 'max_calls': 400, 'max_questions': 40_000}
FORBIDDEN = {'human_label', 'label', 'human_notes', 'notes', 'provenance',
             'gold', 'expected', 'reference_explanation', 'candidate_answer',
             'answer', 'prior_selection', 'prior_score'}


class BudgetStop(Exception):
    """The run has reached a hard cap or has an unresolved provider call."""


def _bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _artifact_bytes(value: Any) -> bytes:
    # Python's JSON decoder accepts non-finite provider values. Preserve that
    # exact invalid value in the private artifact so it can be revalidated.
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=True).encode('utf-8')


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    with temp.open('wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def _read(path: Path) -> dict:
    return json.loads(path.read_bytes())


def _positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _request_count(body: dict) -> int:
    if not isinstance(body, dict) or set(body) != {'model', 'state', 'questions'}:
        raise ValueError('Unexpected Jev request fields')
    if body['model'] != MODEL:
        raise ValueError('Unexpected Jev model')
    if not isinstance(body['state'], dict) or not isinstance(body['questions'], dict):
        raise ValueError('Invalid Jev state or questions')
    for qid, question in body['questions'].items():
        if (not isinstance(qid, str) or not qid or not isinstance(question, dict)
                or question.get('type') != 'noul' or set(question) != {'type', 'instructions'}):
            raise ValueError('Only typed Noul questions are allowed')
    def check(value: Any) -> None:
        if isinstance(value, dict):
            if FORBIDDEN & set(value):
                raise ValueError('Human labels, references or prior scores in Jev payload')
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    check(body)
    return questions.validate_request(body)['question_count']


def _cost(response: Any) -> float | None:
    if not isinstance(response, dict) or response.get('model') != MODEL:
        return None
    usage = response.get('usage')
    if not isinstance(usage, dict):
        return None
    incoming, outgoing = usage.get('input_tokens'), usage.get('output_tokens')
    if (type(incoming) is not int or not 0 <= incoming <= 64_000
            or type(outgoing) is not int or outgoing < 0):
        return None
    return incoming * .042 / 1_000_000


def _result(body: dict, response: dict) -> dict:
    """A bad answer abstains for the entire family; it never yields partial scores."""
    try:
        answers = response['answers']
        if not isinstance(answers, dict) or set(answers) != set(body['questions']):
            raise ValueError('answer_ids')
        scores = {}
        for qid in body['questions']:
            answer = answers[qid]
            if not isinstance(answer, dict) or answer.get('type') != 'noul':
                raise ValueError('answer_type')
            value = answer.get('noul')
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('answer_probability')
            scores[qid] = float(value)
        return {'status': 'completed', 'scores': scores, 'errors': []}
    except (KeyError, TypeError):
        return {'status': 'invalid', 'scores': {}, 'errors': ['answer_schema']}
    except ValueError as exc:
        return {'status': 'invalid', 'scores': {}, 'errors': [str(exc)]}


class Store:
    def __init__(self, root, plan, *, client=None, api_key=''):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if not isinstance(plan, dict) or not isinstance(plan.get('plan_id'), str) or not plan['plan_id']:
            raise ValueError('plan_id is required')
        self.limits = {key: plan.get(key, default) for key, default in DEFAULTS.items()}
        budget = self.limits['budget_usd']
        if (type(budget) not in (int, float) or not math.isfinite(budget)
                or not 0 < budget <= 1 or not all(_positive_int(self.limits[key])
                and self.limits[key] <= DEFAULTS[key] for key in ('max_calls', 'max_questions'))):
            raise ValueError('Invalid budget plan')
        self.identity = _hash(_bytes({'plan_id': plan['plan_id'], 'limits': self.limits}))
        self.client, self.api_key, self._own_client = client, api_key, False
        self.path = self.root / 'evidence-ranking-ledger.json'
        self.ledger = (_read(self.path) if self.path.exists() else
                       {'identity': self.identity, 'calls': {}, 'pending': {}, 'stop_reason': None})
        if self.ledger.get('identity') != self.identity:
            raise ValueError('Ledger belongs to a different plan')
        if not isinstance(self.ledger.get('calls'), dict) or not isinstance(self.ledger.get('pending'), dict):
            raise ValueError('Invalid ledger')
        self._validate_saved()
        if not self.path.exists():
            self._save()

    def _save(self) -> None:
        _atomic(self.path, _bytes(self.ledger))

    def _validate_saved(self) -> None:
        calls, pending = self.ledger['calls'], self.ledger['pending']
        if set(calls) & set(pending):
            raise ValueError('Call both settled and pending')
        request_dir, call_dir = self.root / 'evidence-ranking-requests', self.root / 'evidence-ranking-calls'
        request_keys = {path.stem for path in request_dir.glob('*.json')}
        call_keys = {path.stem for path in call_dir.glob('*.json')}
        if request_keys != set(calls) | set(pending) or not set(calls) <= call_keys or call_keys - set(calls) - set(pending):
            raise ValueError('Unaccounted call artifacts')
        for key, record in (*calls.items(), *pending.items()):
            req_raw = (request_dir / f'{key}.json').read_bytes()
            if _hash(req_raw) != key or record.get('request_hash') != key:
                raise ValueError('Request integrity failure')
            body = json.loads(req_raw)
            if _bytes(body) != req_raw:
                raise ValueError('Request canonicalization failure')
            count = _request_count(body)
            if (record.get('questions') != count or record.get('reserved_usd') != RESERVE_USD
                    or record.get('calls') != 1):
                raise ValueError('Reservation integrity failure')
            if key in calls:
                call_raw = (call_dir / f'{key}.json').read_bytes()
                if _hash(call_raw) != record.get('artifact_hash'):
                    raise ValueError('Response integrity failure')
                call = json.loads(call_raw)
                if _artifact_bytes(call) != call_raw or call.get('request_hash') != key:
                    raise ValueError('Response identity failure')
                if call.get('status') != 'settled' or not isinstance(call.get('response'), dict):
                    raise ValueError('Response settlement integrity failure')
                amount = _cost(call.get('response'))
                if (amount is None or record.get('settled_usd') != amount
                        or call.get('settled_usd') != amount
                        or call.get('result') != _result(body, call['response'])):
                    raise ValueError('Response settlement integrity failure')
            elif key in call_keys and record.get('artifact_hash') is not None:
                if _hash((call_dir / f'{key}.json').read_bytes()) != record['artifact_hash']:
                    raise ValueError('Pending response integrity failure')
        if (self._cost_total() > self.limits['budget_usd'] + 1e-12
                or self._count('calls') > self.limits['max_calls']
                or self._count('questions') > self.limits['max_questions']):
            raise ValueError('Saved ledger exceeds budget')
        if pending:
            self.ledger['stop_reason'] = self.ledger.get('stop_reason') or 'unresolved_pending_call'
            self._save()

    def _records(self):
        return (*self.ledger['calls'].values(), *self.ledger['pending'].values())

    def _cost_total(self) -> float:
        return sum(row.get('settled_usd', row['reserved_usd']) for row in self._records())

    def _count(self, field: str) -> int:
        return sum(row[field] for row in self._records())

    def _stop(self, reason: str):
        self.ledger['stop_reason'] = reason
        self._save()
        raise BudgetStop(reason)

    def call(self, body: dict) -> dict:
        count = _request_count(body)
        raw_request = _bytes(body)
        key = _hash(raw_request)
        if key in self.ledger['calls']:
            return _read(self.root / 'evidence-ranking-calls' / f'{key}.json')['result']
        if self.ledger['stop_reason']:
            raise BudgetStop(self.ledger['stop_reason'])
        if key in self.ledger['pending']:
            self._stop('unresolved_pending_call')
        if self.client is None and not self.api_key:
            raise ValueError('Jev credential or client required for uncached call')
        if self._cost_total() + RESERVE_USD > self.limits['budget_usd'] + 1e-12:
            self._stop('budget_cap')
        if self._count('calls') + 1 > self.limits['max_calls']:
            self._stop('call_cap')
        if self._count('questions') + count > self.limits['max_questions']:
            self._stop('question_cap')
        _atomic(self.root / 'evidence-ranking-requests' / f'{key}.json', raw_request)
        self.ledger['pending'][key] = {'request_hash': key, 'calls': 1,
                                        'questions': count, 'reserved_usd': RESERVE_USD}
        self._save()
        try:
            if self.client is None:
                import httpx
                self.client = httpx.Client(timeout=90, follow_redirects=False,
                                           headers={'Authorization': 'Bearer ' + self.api_key})
                self._own_client = True
            response = self.client.post(JEV_URL, json=body)
            code = getattr(response, 'status_code', 200)
            payload = response.json() if hasattr(response, 'json') else response
            if not 200 <= code < 300:
                payload = {'http_status': code, 'provider_body': payload}
        except Exception as exc:
            self._stop('transport_error')
        serializable = True
        try:
            raw_unverified = _artifact_bytes({'request_hash': key, 'status': 'unverified',
                                     'response': payload, 'error_category': 'unknown_usage_or_model'})
        except (TypeError, ValueError):
            serializable = False
            raw_unverified = _bytes({'request_hash': key, 'status': 'unverified',
                                     'error_category': 'response_serialization'})
        call_path = self.root / 'evidence-ranking-calls' / f'{key}.json'
        _atomic(call_path, raw_unverified)
        self.ledger['pending'][key]['artifact_hash'] = _hash(raw_unverified)
        self._save()
        if not serializable:
            self._stop('response_serialization')
        amount = _cost(payload)
        if amount is None:
            self._stop('unknown_usage_or_model')
        result = _result(body, payload)
        call_raw = _artifact_bytes({'request_hash': key, 'status': 'settled', 'response': payload,
                           'result': result, 'settled_usd': amount})
        _atomic(call_path, call_raw)
        record = self.ledger['pending'].pop(key)
        record['artifact_hash'] = _hash(call_raw)
        record['settled_usd'] = amount
        self.ledger['calls'][key] = record
        self._save()
        return result

    def report(self) -> dict:
        settled = list(self.ledger['calls'].values())
        invalid = sum(_read(self.root / 'evidence-ranking-calls' / f'{key}.json')['result']['status'] == 'invalid'
                      for key in self.ledger['calls'])
        return {'calls': self._count('calls'), 'questions': self._count('questions'),
                'settled_calls': len(settled), 'invalid_calls': invalid,
                'spent_usd': sum(row['settled_usd'] for row in settled),
                'spent_or_reserved_usd': self._cost_total(),
                'pending_calls': len(self.ledger['pending']),
                'stop_reason': self.ledger['stop_reason'], 'limits': dict(self.limits)}

    def close(self) -> None:
        if self._own_client and self.client is not None:
            self.client.close()
