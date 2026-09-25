"""Schema correction preserves semantics, immutable prior calls and the shared cap."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from basedbench.pipeline import connection_eval as base, connection_schema_eval as corrected
from basedbench.pipeline.curation_corpus import file_hash
from tests.test_connection_eval import frozen, mapping, check, call, response


def keyed(value, field, identity):
    value = json.loads(json.dumps(value))
    value[field] = {r[identity]: {k: v for k, v in r.items() if k != identity} for r in value[field]}
    return value


def test_schema_requires_exact_comment_and_connection_keys(frozen):
    case, output, _ = frozen
    source = corrected.make_request(case, 'map', output)
    roles = source['text']['format']['schema']['properties']['comment_roles']
    assert set(roles['required']) == {'c1', 'c2', 'c3'} and not roles['additionalProperties']
    compared = corrected.make_request(case, 'check', output, mapping=mapping(), explanation='A candidate')
    coverage = compared['text']['format']['schema']['properties']['coverage']
    assert coverage['required'] == ['calendar'] and not coverage['additionalProperties']
    assert source['instructions'] == base.MAP and compared['instructions'] == base.CHECK


def test_keyed_parsing_retains_semantic_guards(frozen):
    case, _, _ = frozen
    assert corrected.parse(case, 'map', call(keyed(mapping(), 'comment_roles', 'comment_id'))) == mapping()
    valid = keyed(check(), 'coverage', 'key')
    assert corrected.parse(case, 'check', call(valid), mapping()) == check()
    valid['coverage']['calendar']['status'] = 'missing'
    assert corrected.parse(case, 'check', call(valid), mapping()).get('error')


@pytest.mark.asyncio
async def test_only_errors_continue_with_remaining_budget_and_zero_call_replay(frozen, tmp_path):
    _, prior, _ = frozen
    invalid = mapping()
    invalid['comment_roles'].pop()
    fake = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=response(invalid))))
    first = await base.run(prior, budget_usd=.25, client=fake)
    before = {str(p): file_hash(p) for p in prior.rglob('*') if p.is_file()}
    output = tmp_path / 'continuation'
    plan = corrected.prepare(prior, output)
    assert plan['budget_usd'] + first['accounted_usd'] == .25
    fake2 = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=[
        response(keyed(mapping(), 'comment_roles', 'comment_id')), response(keyed(check(), 'coverage', 'key'))])))
    report = await corrected.run(output, client=fake2)
    assert report['statuses'] == {'model_supported': 1} and report['combined_accounted_usd'] < .25
    assert before == {str(p): file_hash(p) for p in prior.rglob('*') if p.is_file()}
    offline = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=AssertionError('provider'))))
    assert await corrected.run(output, client=offline) == report
    assert not offline.responses.create.called


@pytest.mark.asyncio
async def test_successful_cases_are_not_repeated(frozen, tmp_path):
    _, prior, _ = frozen
    fake = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=[response(mapping()), response(check())])))
    await base.run(prior, budget_usd=.25, client=fake)
    with pytest.raises(ValueError, match='No technical-error'):
        corrected.prepare(prior, tmp_path / 'continuation')
