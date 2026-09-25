"""Durable, capped provider IO for the finite Jev optimization experiment.

A pending call is never retried automatically. Raw payloads stay beneath the
private run root; the public report contains aggregates only.
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
JEV_RESERVE = 64_000 * .042 / 1_000_000
OPENAI_MODEL = 'gpt-6-sol'
OPENAI_OUTPUT = 4000
OPENAI_INPUT_OVERHEAD = 2048
DEFAULTS = {'budget_total_usd': 5, 'budget_search_usd': 4,
            'max_provider_calls': 4000, 'final_call_reserve': 800,
            'max_questions': 500000, 'final_question_reserve': 80000}


class BudgetStop(Exception):
    """A hard expenditure or unresolved-provider stop; no further calls may issue."""


def _bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def _read(path: Path) -> dict:
    return json.loads(path.read_bytes())


def _integer(value: Any, lo: int, hi: int | None = None) -> bool:
    return type(value) is int and value >= lo and (hi is None or value <= hi)


def _usage_price(provider: str, response: dict, reservation: float) -> float | None:
    if not isinstance(response, dict):
        return None
    usage = response.get('usage')
    if not isinstance(usage, dict):
        return None
    if provider == 'jev':
        if response.get('model') != questions.MODEL or not _integer(usage.get('input_tokens'), 0, 64000) or not _integer(usage.get('output_tokens'), 0):
            return None
        amount = usage['input_tokens'] * .042 / 1_000_000
    else:
        if (response.get('model') != OPENAI_MODEL or response.get('service_tier') != 'default'
                or not _integer(usage.get('input_tokens'), 0)
                or not _integer(usage.get('output_tokens'), 0, OPENAI_OUTPUT)):
            return None
        amount = (usage['input_tokens'] * 2.5 + usage['output_tokens'] * 10) / 1_000_000
    return amount if math.isfinite(amount) and amount <= reservation + 1e-12 else None


def _reflection_reserve(prompt: str) -> float:
    return ((len(prompt.encode('utf-8')) + OPENAI_INPUT_OVERHEAD) * 2.5
            + OPENAI_OUTPUT * 10) / 1_000_000


def _parse_reflection(response: dict) -> str:
    if not isinstance(response, dict) or response.get('status') != 'completed':
        raise ValueError('Incomplete reflection response')
    value = response.get('output_text')
    if not isinstance(value, str):
        pieces = []
        for item in response.get('output', []):
            for part in item.get('content', []):
                if part.get('type') == 'output_text' and isinstance(part.get('text'), str):
                    pieces.append(part['text'])
        value = ''.join(pieces)
    if not value:
        raise ValueError('Empty reflection response')
    return value


def _request_spec(provider: str, payload: Any) -> tuple[int, float]:
    if provider == 'jev':
        if not isinstance(payload, dict) or set(payload) != {'model', 'state', 'questions'}:
            raise ValueError('Unexpected Jev request fields')
        size = questions.validate_request(payload)
        forbidden = {'human_label', 'label', 'human_notes', 'notes', 'provenance', 'gold', 'expected'}
        def check(value):
            if isinstance(value, dict):
                if forbidden & set(value):
                    raise ValueError('Human labels or notes in Jev payload')
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)
        check(payload)
        return size['question_count'], JEV_RESERVE
    if provider == 'openai':
        if (not isinstance(payload, dict) or set(payload) != {'model', 'input', 'reasoning',
                'max_output_tokens', 'store', 'service_tier'} or payload['model'] != OPENAI_MODEL
                or payload['reasoning'] != {'effort': 'medium'} or payload['max_output_tokens'] != OPENAI_OUTPUT
                or payload['store'] is not False or payload['service_tier'] != 'default'
                or not isinstance(payload['input'], str)
                or len(payload['input'].encode('utf-8')) > 40_000):
            raise ValueError('Invalid reflection request')
        return 0, _reflection_reserve(payload['input'])
    raise ValueError('Unknown provider')


def _parse_result(provider: str, payload: dict, response: dict):
    return (questions.parse_response(payload, response) if provider == 'jev'
            else _parse_reflection(response))


class ProviderStore:
    def __init__(self, root, plan, *, openai_client=None, jev_client=None,
                 api_key='', jev_api_key=''):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.plan = plan
        self.limits = {k: plan.get(k, v) for k, v in DEFAULTS.items()}
        if (not all(type(self.limits[k]) in (int, float) and math.isfinite(self.limits[k]) and self.limits[k] > 0 for k in ('budget_total_usd', 'budget_search_usd'))
                or self.limits['budget_total_usd'] > 5 or self.limits['budget_search_usd'] > 4
                or self.limits['budget_search_usd'] > self.limits['budget_total_usd']
                or not all(_integer(self.limits[k], 0) for k in ('max_provider_calls', 'final_call_reserve', 'max_questions', 'final_question_reserve'))):
            raise ValueError('Invalid budget plan')
        plan_id = plan.get('plan_id') or plan.get('experiment_id') or _hash(_bytes(plan))
        self.identity = _hash(_bytes({'plan_id': plan_id, 'limits': self.limits}))
        self.openai, self.jev_client = openai_client, jev_client
        self.api_key, self.jev_api_key = api_key, jev_api_key
        self._own_openai = self._own_jev = False
        self.path = self.root / 'provider-ledger.json'
        self.ledger = _read(self.path) if self.path.exists() else {'identity': self.identity, 'calls': {}, 'pending': {}, 'stop_reason': None}
        if self.ledger.get('identity') != self.identity:
            raise ValueError('Provider ledger belongs to a different plan')
        if not isinstance(self.ledger.get('calls'), dict) or not isinstance(self.ledger.get('pending'), dict):
            raise ValueError('Invalid provider ledger')
        self._validate_saved()
        if not self.path.exists():
            self._save()

    def _save(self) -> None:
        _atomic(self.path, _bytes(self.ledger))

    def _validate_saved(self) -> None:
        calls, pending = self.ledger['calls'], self.ledger['pending']
        if set(calls) & set(pending):
            raise ValueError('Call both settled and pending')
        call_artifacts = {p.stem for p in (self.root / 'provider-calls').glob('*.json')}
        # A crash can occur after persisting the raw result but before the
        # ledger settlement. Keep that result private and the reserve pending.
        if not set(calls) <= call_artifacts or call_artifacts - set(calls) - set(pending):
            raise ValueError('Unaccounted provider call artifact')
        if {p.stem for p in (self.root / 'provider-requests').glob('*.json')} != set(calls) | set(pending):
            raise ValueError('Unaccounted provider request artifact')
        for key, record in calls.items():
            call_path = self.root / 'provider-calls' / (key + '.json')
            req_path = self.root / 'provider-requests' / (key + '.json')
            req_bytes = req_path.read_bytes()
            if (_hash(call_path.read_bytes()) != record.get('artifact_hash')
                    or _hash(req_bytes) != record.get('request_hash') or _hash(req_bytes) != key):
                raise ValueError('Provider cache integrity failure')
            request = _read(req_path)
            if _bytes(request) != req_bytes or set(request) != {'provider', 'payload'}:
                raise ValueError('Provider request identity mismatch')
            provider, payload = request['provider'], request['payload']
            count, reserve = _request_spec(provider, payload)
            call = _read(call_path)
            if (call.get('request_key') != key or call.get('provider') != provider
                    or record.get('provider') != provider or record.get('questions') != count
                    or record.get('calls') != 1 or record.get('phase') not in ('search', 'final')
                    or record.get('reserved_usd') != reserve):
                raise ValueError('Provider cache identity mismatch')
            if call.get('status') != 'completed':
                raise ValueError('Cached provider result is not settled')
            try:
                expected = _parse_result(provider, payload, call['response'])
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError('Cached provider response invalid') from exc
            amount = _usage_price(provider, call['response'], reserve)
            if (call.get('result') != expected or amount is None or
                    call.get('settled_usd') != amount or record.get('settled_usd') != amount):
                raise ValueError('Invalid provider settlement')
        for key, record in pending.items():
            req_path = self.root / 'provider-requests' / (key + '.json')
            req_bytes = req_path.read_bytes()
            if _hash(req_bytes) != record.get('request_hash') or _hash(req_bytes) != key:
                raise ValueError('Pending request integrity failure')
            request = _read(req_path)
            if _bytes(request) != req_bytes or set(request) != {'provider', 'payload'}:
                raise ValueError('Pending request identity mismatch')
            provider, payload = request['provider'], request['payload']
            count, reserve = _request_spec(provider, payload)
            if (record.get('provider') != provider or record.get('phase') not in ('search', 'final')
                    or record.get('calls') != 1 or record.get('questions') != count
                    or record.get('reserved_usd') != reserve):
                raise ValueError('Invalid pending reserve')
            if key in call_artifacts and record.get('artifact_hash') is not None:
                artifact = self.root / 'provider-calls' / (key + '.json')
                if _hash(artifact.read_bytes()) != record['artifact_hash']:
                    raise ValueError('Pending response integrity failure')
        if pending:
            self.ledger['stop_reason'] = 'unresolved_pending_call'
            self._save()
        if (not math.isfinite(self._total_cost()) or self._total_cost() < 0
                or self._total_cost() > self.limits['budget_total_usd'] + 1e-12
                or self._total_cost('search') > self.limits['budget_search_usd'] + 1e-12
                or self._count('calls') > self.limits['max_provider_calls']
                or self._count('questions') > self.limits['max_questions']):
            raise ValueError('Saved ledger exceeds total budget')

    def _total_cost(self, phase: str | None = None) -> float:
        rows = list(self.ledger['calls'].values()) + list(self.ledger['pending'].values())
        return sum(row.get('settled_usd', row.get('reserved_usd', 0)) for row in rows if phase is None or row['phase'] == phase)

    def _count(self, name: str, phase: str | None = None) -> int:
        rows = list(self.ledger['calls'].values()) + list(self.ledger['pending'].values())
        return sum(row[name] for row in rows if phase is None or row['phase'] == phase)

    def _stop(self, reason: str) -> None:
        self.ledger['stop_reason'] = reason
        self._save()
        raise BudgetStop(reason)

    def _execute(self, provider: str, payload: Any, phase: str, questions_count: int,
                 reservation: float, send, parse, *, available: bool):
        if phase not in ('search', 'final'):
            raise ValueError('phase must be search or final')
        request = {'provider': provider, 'payload': payload}
        request_bytes = _bytes(request)
        key = _hash(request_bytes)
        if key in self.ledger['calls']:
            call = _read(self.root / 'provider-calls' / (key + '.json'))
            if call['status'] != 'completed':
                self._stop('unresolved_provider_result')
            return call['result']
        if self.ledger['stop_reason']:
            raise BudgetStop(self.ledger['stop_reason'])
        if key in self.ledger['pending']:
            self._stop('unresolved_pending_call')
        if not available:
            raise ValueError('Provider credential or client required for uncached call')
        if self._total_cost() + reservation > self.limits['budget_total_usd'] + 1e-12:
            self._stop('total_budget_cap')
        if phase == 'search' and self._total_cost('search') + reservation > self.limits['budget_search_usd'] + 1e-12:
            self._stop('search_budget_cap')
        if self._count('calls') + 1 > self.limits['max_provider_calls'] - (self.limits['final_call_reserve'] if phase == 'search' else 0):
            self._stop('call_cap')
        if self._count('questions') + questions_count > self.limits['max_questions'] - (self.limits['final_question_reserve'] if phase == 'search' else 0):
            self._stop('question_cap')
        # A request and the pending ledger must both exist before a provider call.
        request_path = self.root / 'provider-requests' / (key + '.json')
        _atomic(request_path, request_bytes)
        self.ledger['pending'][key] = {'request_hash': _hash(request_bytes), 'provider': provider,
                                       'phase': phase, 'calls': 1, 'questions': questions_count,
                                       'reserved_usd': reservation}
        self._save()
        response = None
        try:
            response = send()
            result = parse(response)
            amount = _usage_price(provider, response, reservation)
            if amount is None:
                raise ValueError('Unverifiable provider usage, model, tier or reservation')
        except Exception as exc:
            # Keep the reservation and raw request; no automatic retry of an
            # ambiguous transport or malformed response.
            if response is not None:
                raw_call = {'request_key': key, 'provider': provider, 'status': 'unverified',
                            'response': response, 'error_type': type(exc).__name__}
                try:
                    raw_bytes = _bytes(raw_call)
                except (TypeError, ValueError):
                    raw_bytes = _bytes({'request_key': key, 'provider': provider,
                                        'status': 'unverified', 'response_serialization_failed': True,
                                        'error_type': type(exc).__name__})
                _atomic(self.root / 'provider-calls' / (key + '.json'), raw_bytes)
                self.ledger['pending'][key]['artifact_hash'] = _hash(raw_bytes)
            self.ledger['stop_reason'] = 'provider_or_settlement_error'
            self._save()
            raise BudgetStop('provider_or_settlement_error') from exc
        call = {'request_key': key, 'provider': provider, 'status': 'completed',
                'response': response, 'result': result, 'settled_usd': amount}
        call_bytes = _bytes(call)
        _atomic(self.root / 'provider-calls' / (key + '.json'), call_bytes)
        record = self.ledger['pending'].pop(key)
        record['settled_usd'] = amount
        record['artifact_hash'] = _hash(call_bytes)
        self.ledger['calls'][key] = record
        self._save()
        return result

    def jev(self, body: dict, phase: str) -> dict:
        count, reserve = _request_spec('jev', body)
        available = self.jev_client is not None or bool(self.jev_api_key)
        if self.jev_client is None:
            def send():
                import httpx
                self.jev_client = httpx.Client(timeout=90, follow_redirects=False,
                    headers={'Authorization': 'Bearer ' + self.jev_api_key})
                self._own_jev = True
                response = self.jev_client.post(JEV_URL, json=body)
                payload = response.json()
                return payload if 200 <= response.status_code < 300 else {'http_status': response.status_code, 'provider_body': payload}
        else:
            def send():
                response = self.jev_client.post(JEV_URL, json=body)
                payload = response.json() if hasattr(response, 'json') else response
                code = getattr(response, 'status_code', 200)
                return payload if 200 <= code < 300 else {'http_status': code, 'provider_body': payload}
        return self._execute('jev', body, phase, count, reserve,
                             send, lambda response: _parse_result('jev', body, response), available=available)

    def reflect(self, prompt: str, phase: str = 'search') -> str:
        if not isinstance(prompt, str) or len(prompt.encode('utf-8')) > 40_000:
            raise ValueError('Reflection prompt exceeds 40k UTF-8 bytes')
        body = {'model': OPENAI_MODEL, 'input': prompt, 'reasoning': {'effort': 'medium'},
                'max_output_tokens': OPENAI_OUTPUT, 'store': False, 'service_tier': 'default'}
        _, reserve = _request_spec('openai', body)
        available = self.openai is not None or bool(self.api_key)
        def send():
            if self.openai is None:
                import openai
                self.openai = openai.OpenAI(api_key=self.api_key, max_retries=0, timeout=180)
                self._own_openai = True
            response = self.openai.responses.create(**body)
            return response.model_dump(mode='json') if hasattr(response, 'model_dump') else response
        return self._execute('openai', body, phase, 0, reserve, send,
                             lambda response: _parse_result('openai', body, response), available=available)

    def report(self) -> dict:
        return {'calls': self._count('calls'), 'questions': self._count('questions'),
                'spent_or_reserved_usd': self._total_cost(),
                'search_spent_or_reserved_usd': self._total_cost('search'),
                'pending_calls': len(self.ledger['pending']),
                'stop_reason': self.ledger['stop_reason'], 'limits': dict(self.limits)}

    def close(self) -> None:
        if self._own_openai and self.openai is not None:
            self.openai.close()
        if self._own_jev and self.jev_client is not None:
            self.jev_client.close()
