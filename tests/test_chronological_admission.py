"""Frozen chronological admission: stage semantics, accounting and replay."""
import asyncio
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

from PIL import Image
import pytest

from basedbench.pipeline import chronological_admission as admission
from basedbench.pipeline.curation_corpus import digest, file_hash, write_json


def response(payload, *, model=admission.MODEL, usage=None, tier='default'):
    usage = {'input_tokens': 100, 'output_tokens': 100} if usage is None else usage
    body = {'model': model, 'status': 'completed', 'usage': usage, 'service_tier': tier}
    return SimpleNamespace(status='completed', output_text=json.dumps(payload),
                           usage=SimpleNamespace(model_dump=lambda **_: usage),
                           model_dump=lambda **_: body)


def client(*payloads):
    return SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=[response(p) for p in payloads])))


def content_pass():
    return {'findings': [], 'context_sufficient': True, 'context_gap': None, 'rationale': 'No excluded content.'}


def draft():
    return {'status': 'proposed', 'explanation': 'A shared wordplay.', 'reason': 'The source reading.',
            'evidence_comment_ids': ['c1', 'c2', 'c3']}


def check():
    return {'image_setup': 'The depicted setup.', 'joke_connection': 'The intended wordplay.',
            'claim_support': [{'claim': 'The core inference', 'support': 'shared_comments',
                               'evidence_comment_ids': ['c1', 'c2', 'c3']}],
            'missing_core_details': [], 'verdict': 'pass', 'reason': 'A concrete explanation.',
            'defects': [], 'evidence_comment_ids': ['c1', 'c2', 'c3']}


def suitability():
    return {'setup': 'Visible setup', 'required_inference': 'A particular pun.',
            'verdict': 'pass', 'failure_code': None, 'reason': 'Concrete reason.'}


def source(tmp_path, *, count=1):
    inventory, duplicates, output = [tmp_path / name for name in ('inventory', 'duplicates', 'admission')]
    inventory.mkdir(); duplicates.mkdir()
    picture = inventory / 'image.png'
    Image.new('RGB', (64, 64), 'white').save(picture)
    sha = file_hash(picture)
    candidates = []
    inputs = []
    for index in range(count):
        pid = f'p{index}'
        candidates.append({'post_id': pid, 'subreddit': 'ExplainTheJoke', 'source_date': '2026-06-27',
            'image': {'status': 'available', 'path': 'image.png', 'sha256': sha},
            'comment_retrieval': {'scope': 'top-level', 'comments': [
                {'comment_id': f'c{i}', 'body': 'Same reading.', 'score': i} for i in (1, 2, 3)]}})
        inputs.append({'post_id': pid, 'pool': 'fresh', 'image': {'sha256': sha}})
    write_json(inventory / 'candidates.json', candidates)
    iplan = {'files': {'candidates.json': file_hash(inventory / 'candidates.json'), 'image.png': sha}}
    iplan['inventory_id'] = digest(iplan)
    write_json(inventory / 'plan.json', iplan)
    write_json(inventory / 'manifest.json', {'inventory_id': iplan['inventory_id'],
        'files': {'candidates.json': file_hash(inventory / 'candidates.json'), 'image.png': sha}})
    write_json(duplicates / 'inputs.json', inputs)
    dplan = {'inventory_id': iplan['inventory_id'], 'files': {'inputs.json': file_hash(duplicates / 'inputs.json')},
             'code': admission.chronological_duplicates._code_hashes()}
    dplan['audit_id'] = digest(dplan)
    write_json(duplicates / 'plan.json', dplan)
    write_json(duplicates / 'report.json', {'audit_id': dplan['audit_id'],
        'dispositions': [{'post_id': c['post_id']} for c in candidates], 'edges': []})
    write_json(duplicates / 'results-manifest.json', {'report.json': file_hash(duplicates / 'report.json')})
    return inventory, duplicates, output


@pytest.mark.asyncio
async def test_accept_and_completed_replay_needs_no_client_or_key(tmp_path):
    inventory, duplicates, out = source(tmp_path)
    plan = admission.prepare_inventory(inventory, duplicates, out)
    api = client(content_pass(), draft(), check(), suitability())
    report = await admission.run(out, budget_usd=10, client=api)
    assert plan['model'] == 'gpt-6-luna'
    assert report['counts'] == {'accept': 1}
    assert report['cost']['completed_provider_calls'] == 4
    assert report['cost']['accounted_usd'] < 10
    assert all(c.kwargs['model'] == admission.MODEL for c in api.responses.create.call_args_list)
    assert await admission.run(out, budget_usd=10, api_key='') == report
    assert api.responses.create.call_count == 4


@pytest.mark.asyncio
async def test_cap_is_shared_by_all_cases_and_no_call_occurs_if_unreservable(tmp_path):
    inventory, duplicates, out = source(tmp_path, count=2)
    admission.prepare_inventory(inventory, duplicates, out, budget_usd=.000001)
    api = client()
    report = await admission.run(out, budget_usd=.000001, client=api)
    assert report['counts'] == {'defer': 2}
    assert report['cost']['accounted_usd'] == 0
    assert api.responses.create.call_count == 0
    with pytest.raises(ValueError, match='cap'):
        await admission.run(out, budget_usd=10, client=api)


def test_unreservable_run_needs_no_api_key(tmp_path):
    inventory, duplicates, out = source(tmp_path)
    admission.prepare_inventory(inventory, duplicates, out, budget_usd=.000001)
    report = asyncio.run(admission.run(out, budget_usd=.000001))
    assert report['complete'] and report['cost']['completed_provider_calls'] == 0


@pytest.mark.asyncio
async def test_interrupted_request_is_reserved_and_not_repeated(tmp_path):
    inventory, duplicates, out = source(tmp_path)
    plan = admission.prepare_inventory(inventory, duplicates, out)
    api = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=asyncio.CancelledError())))
    with pytest.raises(asyncio.CancelledError):
        await admission.run(out, budget_usd=10, client=api)
    assert (out / 'calls/p0.content.pending').exists()
    report = await admission.run(out, budget_usd=10, client=api)
    assert api.responses.create.call_count == 1
    assert report['cost']['unknown_usage_calls'] == 1
    assert report['cost']['accounted_usd'] == plan['request_bounds_usd']['p0.content']
    assert not (out / 'calls/p0.content.pending').exists()


@pytest.mark.asyncio
async def test_wrong_model_and_citation_are_technical_deferrals(tmp_path):
    inventory, duplicates, out = source(tmp_path)
    admission.prepare_inventory(inventory, duplicates, out)
    api = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=response(content_pass(), model='gpt-5.6-luna'))))
    report = await admission.run(out, budget_usd=10, client=api)
    assert report['counts'] == {'defer': 1} and report['technical_errors'] == 1
    assert api.responses.create.call_count == 1
    case = json.loads((out / 'cases.json').read_text())[0]
    assert admission.parse(case, 'generated_check', {'status': 'completed', 'response': {'model': admission.MODEL},
        'output_text': json.dumps({**check(), 'evidence_comment_ids': ['fabricated']})}).get('error')


@pytest.mark.asyncio
async def test_failed_quota_response_halts_later_candidates_and_resume(tmp_path):
    inventory, duplicates, out = source(tmp_path, count=2)
    admission.prepare_inventory(inventory, duplicates, out)
    failed = SimpleNamespace(status='failed', output_text='', usage=None,
        model_dump=lambda **_: {'model': admission.MODEL, 'status': 'failed',
                                'error': {'code': 'insufficient_quota', 'message': 'Quota exhausted'}})
    api = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=failed)))
    report = await admission.run(out, budget_usd=10, client=api)
    assert report['counts'] == {'defer': 2}
    assert report['cost']['unknown_usage_calls'] == 1
    assert api.responses.create.call_count == 1
    assert await admission.run(out, budget_usd=10, client=api) == report
    assert api.responses.create.call_count == 1


def test_usage_validation_retains_full_reservation(tmp_path):
    inventory, duplicates, out = source(tmp_path)
    plan = admission.prepare_inventory(inventory, duplicates, out)
    budget = admission.Budget(plan, out)
    budget.settle('p0', 'content', {'usage': {'input_tokens': -5, 'output_tokens': 1}})
    assert budget.charges['p0.content'] == plan['request_bounds_usd']['p0.content']
    budget.settle('p0', 'content', {'usage': {'input_tokens': True, 'output_tokens': 1}})
    assert budget.charges['p0.content'] == plan['request_bounds_usd']['p0.content']
    budget.settle('p0', 'content', {'usage': {'input_tokens': 1, 'output_tokens': 1,
                                            'input_tokens_details': ['malformed']}})
    assert budget.charges['p0.content'] == plan['request_bounds_usd']['p0.content']
    budget.settle('p0', 'content', {'usage': {'input_tokens': 1, 'output_tokens': 1},
                                   'response': {'service_tier': 'priority'}})
    assert budget.violated


def test_empty_collection_needs_no_model(tmp_path):
    inventory, duplicates, out = source(tmp_path, count=0)
    admission.prepare_inventory(inventory, duplicates, out)
    report = asyncio.run(admission.run(out, budget_usd=10))
    assert report['complete'] and report['outcomes'] == [] and report['cost']['accounted_usd'] == 0


def test_actual_duplicate_artifact_contract_empty_collection(tmp_path):
    """Exercise both additive adapters without a model or encoder download."""
    inventory = tmp_path / 'inventory'
    inventory.mkdir()
    write_json(inventory / 'baseline.json', {'posts': [], 'release_ids': []})
    write_json(inventory / 'candidates.json', [])
    write_json(inventory / 'selection.json', [])
    iplan = {'version': admission.chronological_inventory.VERSION,
             'baseline_sha256': digest({'posts': [], 'release_ids': []}),
             'code_sha256': admission.chronological_inventory.code_hashes()}
    iplan['inventory_id'] = digest(iplan)
    write_json(inventory / 'plan.json', iplan)
    write_json(inventory / 'manifest.json', {'inventory_id': iplan['inventory_id'],
        'files': {p.name: file_hash(p) for p in inventory.iterdir() if p.name != 'manifest.json'}})
    database = tmp_path / 'archive.db'
    with sqlite3.connect(database) as db:
        db.executescript('''
            CREATE TABLE memes(post_id TEXT, title TEXT, local_image_path TEXT, permalink TEXT);
            CREATE TABLE ground_truths(post_id TEXT, explanation TEXT);
            CREATE TABLE reviews(post_id TEXT, status TEXT);
        ''')
    known = tmp_path / 'known.json'
    write_json(known, [])
    duplicates = tmp_path / 'duplicates'
    admission.chronological_duplicates.prepare(database, inventory, duplicates, known)
    admission.chronological_duplicates.run(duplicates, tmp_path / 'uncached-models')
    output = tmp_path / 'admission'
    plan = admission.prepare_inventory(inventory, duplicates, output)
    assert plan['scope']['duplicate_audit_id'] == json.loads((duplicates / 'plan.json').read_text())['audit_id']
    report = asyncio.run(admission.run(output, budget_usd=10))
    assert report['complete'] and report['cost']['completed_provider_calls'] == 0


def test_duplicate_manifest_and_coverage_are_required(tmp_path):
    inventory, duplicates, out = source(tmp_path)
    (duplicates / 'results-manifest.json').unlink()
    with pytest.raises(FileNotFoundError):
        admission.prepare_inventory(inventory, duplicates, out)
    write_json(duplicates / 'results-manifest.json', {'report.json': file_hash(duplicates / 'report.json')})
    report = json.loads((duplicates / 'report.json').read_text())
    report['dispositions'].append(report['dispositions'][0])
    write_json(duplicates / 'report.json', report)
    write_json(duplicates / 'results-manifest.json', {'report.json': file_hash(duplicates / 'report.json')})
    with pytest.raises(ValueError, match='cover every'):
        admission.prepare_inventory(inventory, duplicates, out)
