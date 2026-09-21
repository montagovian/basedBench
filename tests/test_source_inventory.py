"""Inventory must expose missing coverage, preserve evidence and stay bounded."""
import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from basedbench.pipeline import source_inventory as inv
from basedbench.pipeline.curation_corpus import digest
from basedbench.reddit.pullpush import PULLPUSH_BASE, PullpushClient


def plan(**updates):
    return {'start': inv.iso(1000), 'end_exclusive': inv.iso(5000),
            'max_pages_per_subreddit': 10, 'min_score': 10, 'min_comments': 3,
            'candidate_ceiling': 3, 'selection_seed': 'test', **updates}


def post(pid, ts=3000, **updates):
    return {'id': pid, 'subreddit': 'test', 'created_utc': ts, 'score': 50,
            'num_comments': 20, 'url': 'https://i.redd.it/example.jpg', **updates}


@pytest.mark.asyncio
async def test_pagination_overlaps_boundary_and_deduplicates():
    first = [post(f'p{i}', 4000 - i) for i in range(100)]
    fetch = AsyncMock(side_effect=[{'data': first}, {'data': [first[-1], post('edge', 3901), post('older', 3900)]}])
    result = await inv.discover(plan(), 'test', fetch)
    assert fetch.call_args_list[1].args[1]['before'] == 3902
    assert len(result['posts']) == 102
    assert result['excluded']['pagination_overlap'] == 1
    assert result['source_exhausted']
    assert result['archive_completeness'] == 'unknown'


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['page_cap', 'timestamp_stalled', 'request_error', 'invalid_page'])
async def test_incomplete_discovery_never_claims_empty_or_complete(kind):
    page = {'data': [post(f'p{i}', 3000) for i in range(100)]}
    p = plan(max_pages_per_subreddit=1 if kind == 'page_cap' else 10)
    if kind == 'request_error':
        fetch = AsyncMock(side_effect=inv.RequestFailure('HTTP 429'))
    elif kind == 'invalid_page':
        fetch = AsyncMock(return_value={'data': [post('outside', 900)]})
    else:
        fetch = AsyncMock(return_value=page)
    result = await inv.discover(p, 'test', fetch)
    assert result['stop_reason'] == kind
    assert not result['source_exhausted']
    if kind == 'timestamp_stalled':
        assert fetch.call_count == 2
        assert len(result['posts']) == 100


@pytest.mark.parametrize('payload', [{}, {'data': None}, {'data': [], 'error': 'offline'}, {'data': ['bad']}])
def test_malformed_response_is_not_empty(payload):
    with pytest.raises(inv.RequestFailure):
        inv.parse_page(payload)


@pytest.mark.asyncio
async def test_inclusive_start_exclusive_end_and_policy_metadata():
    fetch = AsyncMock(return_value={'data': [post('edge', 1000, over_18=True),
                                          post('low', score=1), post('text', is_self=True)]})
    result = await inv.discover(plan(), 'test', fetch)
    assert fetch.call_args.args[1]['after'] == 999
    assert result['posts'][0]['over_18'] is True
    assert result['excluded'] == {'low_score': 1, 'no_direct_image': 1}


def test_selection_is_bounded_deterministic_balanced_and_excludes_baseline():
    discoveries = [{'posts': [{'post_id': f'{s}{i}'} for i in range(10)]} for s in 'abc']
    baseline = {'posts': [{'post_id': 'a1'}], 'release_ids': ['a1']}
    p = plan(candidate_ceiling=7)
    selected = inv.select_candidates(discoveries, baseline, p)
    shuffled = copy.deepcopy(discoveries)
    for d in shuffled:
        d['posts'].reverse()
    assert selected == inv.select_candidates(shuffled, baseline, p)
    assert len(selected) == len({p['post_id'] for p in selected}) == 7
    assert all(p['post_id'] != 'a1' and not p['in_existing_corpus'] for p in selected)
    assert [sum(p['post_id'].startswith(s) for p in selected) for s in 'abc'] == [3, 2, 2]


def comment_payload():
    return [{'data': {'children': [{'data': {'id': 'abc', 'num_comments': 500}}]}},
            {'data': {'children': [
                {'kind': 't1', 'data': {'id': 'ok', 'author': 'someone', 'body': 'Explanation', 'score': 50}},
                {'kind': 't1', 'data': {'id': 'bot', 'author': 'AutoModerator', 'body': 'Rules'}},
                {'kind': 't1', 'data': {'id': 'gone', 'body': '[deleted]'}},
                {'kind': 'more', 'data': {'count': 497, 'children': ['next']}}]}}]


def test_comments_record_sample_scope_and_omissions():
    parsed = inv.parse_comments(comment_payload(), 'abc')
    assert parsed['usable_count'] == 1
    assert parsed['more_count'] == 497 and parsed['more_ids'] == ['next']
    assert parsed['complete_thread'] is False
    assert parsed['excluded'] == {'bot_or_moderator': 1, 'removed_or_deleted': 1}
    with pytest.raises(ValueError):
        inv.parse_comments(comment_payload(), 'different')
    with pytest.raises(ValueError):
        inv.parse_comments({}, 'abc')


@pytest.mark.asyncio
async def test_rate_limit_retry_is_recorded_and_replay_never_uses_network(tmp_path):
    seen = []
    def respond(request):
        seen.append(request)
        return httpx.Response(429 if len(seen) == 1 else 200,
                              headers={'retry-after': '0'}, json={'data': []})
    p = {'max_json_attempts': 3, 'request_delay_seconds': 0, 'max_retry_wait_seconds': 30}
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        recorder = inv.Recorder(tmp_path, p, client)
        assert await recorder.get(PULLPUSH_BASE, {'size': 100}, {'Authorization': 'secret'}) == {'data': []}
        assert await recorder.get(PULLPUSH_BASE, {'size': 100}) == {'data': []}
        assert len(seen) == 2
        path = recorder.path(PULLPUSH_BASE, {'size': 100})
        assert 'secret' not in path.read_text()
        saved = json.loads(path.read_text())
        assert [r['http_status'] for r in saved['attempts']] == [429, 200]
        saved['attempts'][-1]['payload'] = {'data': [post('injected')]}
        path.write_text(json.dumps(saved))
        with pytest.raises(ValueError, match='changed'):
            await recorder.get(PULLPUSH_BASE, {'size': 100})


@pytest.mark.asyncio
async def test_failed_request_is_preserved_on_resume(tmp_path):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(403, json={'error': 'denied'}))) as client:
        recorder = inv.Recorder(tmp_path, {'max_json_attempts': 3, 'request_delay_seconds': 0}, client)
        for _ in range(2):
            with pytest.raises(inv.RequestFailure, match='403'):
                await recorder.get(PULLPUSH_BASE, {})
        assert len(json.loads(recorder.path(PULLPUSH_BASE, {}).read_text())['attempts']) == 1


@pytest.mark.asyncio
async def test_legacy_client_no_longer_turns_api_errors_into_empty_posts():
    async with PullpushClient() as client:
        client._http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(429)))
        with pytest.raises(httpx.HTTPStatusError):
            await client._fetch_page('test', 1000, 5000)


@pytest.mark.asyncio
async def test_image_redirects_and_non_images_are_failures(tmp_path):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(302, headers={'location': 'http://localhost/private'}))) as client:
        result = await inv.collect_image(tmp_path, {'post_id': 'abc', 'image_url': 'https://i.redd.it/x.jpg'}, client)
    assert result['status'] == 'error' and result['http_status'] == 302
    assert not (tmp_path / 'images' / 'abc').exists()


@pytest.mark.asyncio
async def test_completed_manifest_verifies_without_credentials_or_network(tmp_path, monkeypatch):
    p, baseline = {'code_sha256': inv.code_hashes()}, {'posts': []}
    p['baseline_sha256'] = digest(baseline)
    p['inventory_id'] = digest(p)
    inv.write(tmp_path / 'plan.json', p)
    inv.write(tmp_path / 'baseline.json', baseline)
    inv.write(tmp_path / 'report.json', {'selected': 3})
    inv.write(tmp_path / 'manifest.json', {'files': {'report.json': inv.file_hash(tmp_path / 'report.json')}})
    monkeypatch.setattr(inv, 'Config', lambda: pytest.fail('Replay must not load credentials'))
    assert await inv.run(tmp_path) == {'selected': 3}
    inv.write(tmp_path / 'report.json', {'selected': 4})
    with pytest.raises(ValueError, match='artifact changed'):
        await inv.run(tmp_path)
