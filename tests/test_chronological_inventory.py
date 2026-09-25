"""Chronological selection, refusal policy and resumable evidence stay bounded."""
import io
import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
from PIL import Image
import pytest

from basedbench.pipeline import chronological_inventory as inv
from basedbench.pipeline.curation_corpus import digest


def plan(tmp_path, *, ceiling=1000, start='2026-06-27T00:00:00+00:00', end='2026-06-29T00:00:00+00:00'):
    baseline = {'posts': [], 'release_ids': []}
    p = {'version': inv.VERSION, 'start': start, 'end_exclusive': end,
         'subreddits': list(inv.SUBREDDITS), 'candidate_ceiling': ceiling,
         'max_pages_per_subreddit': 2, 'page_size': 100, 'min_score': 10,
         'min_comments': 3, 'prior_inventories': {}, 'prior_pool_ids': [],
         'request_delay_seconds': 0, 'max_json_attempts': 3,
         'max_retry_wait_seconds': 60, 'comments': {'limit': 100},
         'code_sha256': inv.code_hashes(), 'baseline_sha256': digest(baseline),
         'limits': []}
    p['inventory_id'] = digest(p)
    inv.pilot.write(tmp_path / 'baseline.json', baseline)
    inv.pilot.write(tmp_path / 'plan.json', p)
    return p


def post(pid, created, subreddit='ExplainTheJoke'):
    return {'id': pid, 'subreddit': subreddit, 'created_utc': created,
            'score': 50, 'num_comments': 20, 'url': 'https://i.redd.it/x.png',
            'title': pid}


@pytest.mark.asyncio
async def test_agent_refusal_stops_entire_archive_service_with_no_retry(tmp_path):
    p = plan(tmp_path)
    seen = []
    def respond(request):
        seen.append(request)
        return httpx.Response(429, json={'error': 'Rate limit exceeded. This website does not provide free scraping resources for agents.'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await inv.run(tmp_path, client=client)
        assert result['selected'] == 0
        assert len(seen) == 1
        assert len(result['unattempted_partitions']) == 3
        assert result['source_stops']['archive'] == 'explicit_agent_refusal'
        assert 'PeterExplainsTheJoke' not in seen[0].url.params.get('subreddit', '')
        assert 'Authorization' not in next((tmp_path / 'requests').glob('*.json')).read_text()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: pytest.fail('replay used network'))) as client:
        assert (await inv.run(tmp_path, client=client))['selected'] == 0
    inv.pilot.write(tmp_path / 'report.json', {'changed': True})
    with pytest.raises(ValueError, match='Frozen artifact changed'):
        await inv.run(tmp_path, client=client)


@pytest.mark.asyncio
async def test_retry_after_http_date_stops_source(tmp_path):
    p = plan(tmp_path)
    future = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=180))
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(429, headers={'Retry-After': future}, json={'error': 'busy'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        recorder = inv.Recorder(tmp_path, p, client)
        with pytest.raises(inv.RequestFailure) as error:
            await recorder.get('https://example.test/x', {})
        assert error.value.stop == 'excessive_retry_after'
        with pytest.raises(inv.RequestFailure):
            await recorder.get('https://example.test/y', {})
        assert len(calls) == 1


@pytest.mark.asyncio
async def test_days_select_in_timestamp_id_order_and_cap_before_assets(tmp_path):
    p = plan(tmp_path, ceiling=2)
    start = inv.pilot.timestamp(p['start'])
    def respond(request):
        if request.url.host == 'i.redd.it':
            return httpx.Response(404)
        source = request.url.params['subreddit']
        after = int(request.url.params['after'])
        rows = []
        if after == start - 1:
            rows = [post('z', start + 20, source), post('a', start + 10, source)] if source == 'ExplainTheJoke' else [post('b', start + 10, source)]
        return httpx.Response(200, json={'data': rows})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await inv.run(tmp_path, client=client)
    assert result['selected'] == 2
    assert [r['post_id'] for r in inv.read(tmp_path / 'selection.json')] == ['a', 'b']
    assert result['unattempted_partitions'] == [{'day': '2026-06-28', 'subreddit': 'ExplainTheJoke'},
                                                 {'day': '2026-06-28', 'subreddit': 'explainitpeter'}]
    assert len(inv.read(tmp_path / 'candidates.json')) == 2
    assert result['comments']['error'] == 2  # Authentication unavailable in injected client path.


def test_prior_ids_require_complete_hashed_manifest(tmp_path):
    prior = tmp_path / 'prior'
    inv.pilot.write(prior / 'plan.json', {'inventory_id': 'old'})
    inv.pilot.write(prior / 'selection.json', [{'post_id': 'old'}])
    inv.pilot.write(prior / 'candidates.json', [{'post_id': 'old'}])
    (prior / 'images').mkdir()
    (prior / 'images' / 'old').write_bytes(b'\x89PNG\x00binary')
    files = {name: inv.file_hash(prior / name) for name in ('plan.json', 'selection.json', 'candidates.json')}
    files['images/old'] = inv.file_hash(prior / 'images' / 'old')
    inv.pilot.write(prior / 'manifest.json', {'inventory_id': 'old', 'files': files})
    assert inv.prior_ids(prior)[0] == {'old'}
    inv.pilot.write(prior / 'selection.json', [{'post_id': 'tampered'}])
    with pytest.raises(ValueError, match='changed'):
        inv.prior_ids(prior)


def test_selection_excludes_archive_prior_and_is_chronological():
    rows = [{'posts': [{'post_id': pid, 'created_utc': ts} for pid, ts in
                       [('new2', 20), ('archive', 11), ('new1', 10), ('prior', 9)]]}]
    selected, exclusions = inv.select_day(rows, {'archive'}, set(), {'prior'}, 2)
    assert [p['post_id'] for p in selected] == ['new1', 'new2']
    assert exclusions['archive_overlap'] == exclusions['prior_inventory_overlap'] == 1


@pytest.mark.asyncio
async def test_image_requires_full_decode_and_replay_hash(tmp_path):
    image = Image.new('RGB', (2, 2), 'red')
    payload = io.BytesIO()
    image.save(payload, format='PNG')
    post_row = {'post_id': 'img', 'image_url': 'https://i.redd.it/x.png'}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=payload.getvalue()))) as client:
        record = await inv.collect_image(tmp_path, post_row, client)
        assert record['status'] == 'available' and record['width'] == 2
        assert (await inv.collect_image(tmp_path, post_row, client)) == record
    (tmp_path / record['path']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='Cached image changed'):
        await inv.collect_image(tmp_path, post_row, client)


@pytest.mark.asyncio
async def test_image_404_is_terminal_and_transient_attempts_are_bounded(tmp_path, monkeypatch):
    sleeps = []
    async def fake_sleep(seconds):
        sleeps.append(seconds)
    monkeypatch.setattr(inv.asyncio, 'sleep', fake_sleep)
    rows = []
    def fail(request):
        rows.append(request)
        return httpx.Response(503)
    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
        failed = await inv.collect_image(tmp_path, {'post_id': 'fail', 'image_url': 'https://i.redd.it/x.png'}, client)
    assert failed['status'] == 'error' and len(rows) == 3 and sleeps == [10, 30]
    seen = []
    def missing(request):
        seen.append(request)
        return httpx.Response(404)
    async with httpx.AsyncClient(transport=httpx.MockTransport(missing)) as client:
        record = await inv.collect_image(tmp_path, {'post_id': 'missing', 'image_url': 'https://i.redd.it/x.png'}, client)
    assert record['http_status'] == 404 and len(seen) == 1


@pytest.mark.asyncio
async def test_resume_detects_candidate_changes_before_network(tmp_path):
    p = plan(tmp_path, ceiling=1, end='2026-06-28T00:00:00+00:00')
    ts = inv.pilot.timestamp(p['start'])
    def respond(request):
        if request.url.host == 'i.redd.it':
            return httpx.Response(404)
        if request.url.params.get('subreddit') == 'ExplainTheJoke':
            return httpx.Response(200, json={'data': [post('one', ts + 1)]})
        return httpx.Response(200, json={'data': []})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await inv.run(tmp_path, client=client)
    (tmp_path / 'manifest.json').unlink()
    cases = inv.read(tmp_path / 'candidates.json')
    cases[0]['comment_retrieval']['error'] = 'tampered'
    inv.pilot.write(tmp_path / 'candidates.json', cases)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: pytest.fail('resume used network'))) as client:
        with pytest.raises(ValueError, match='Candidate record changed'):
            await inv.run(tmp_path, client=client)
