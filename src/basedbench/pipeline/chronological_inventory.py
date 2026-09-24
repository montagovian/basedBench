"""Resumable, bounded UTC-day source inventory for the authorized chronological backfill."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import fcntl
import io
import json
from pathlib import Path

import httpx
from PIL import Image

from basedbench.config import Config
from basedbench.pipeline import source_inventory as pilot
from basedbench.pipeline.curation_corpus import digest, file_hash
from basedbench.reddit.images import MAX_IMAGE_BYTES, _validate_image_url

VERSION = 'chronological-inventory-v1'
SUBREDDITS = ('ExplainTheJoke', 'explainitpeter')
MAX_PAGES_PER_DAY = 10


def code_hashes() -> dict:
    return {**pilot.code_hashes(), 'chronological_inventory.py': file_hash(Path(__file__))}


def read(path: Path):
    return json.loads(path.read_text())


def checked(path: Path, expected: str, label: str):
    if not path.is_file() or file_hash(path) != expected:
        raise ValueError(f'{label} changed: {path}')


def verify_manifest(directory: Path, manifest: dict):
    if not isinstance(manifest.get('files'), dict):
        raise ValueError('Invalid inventory manifest')
    for name, expected in manifest['files'].items():
        target = directory / name
        if target.resolve().is_relative_to(directory.resolve()) is False:
            raise ValueError('Invalid inventory manifest path')
        checked(target, expected, 'Frozen artifact')


def prior_ids(prior: Path) -> tuple[set[str], str]:
    manifest_path = prior / 'manifest.json'
    manifest = read(manifest_path)
    verify_manifest(prior, manifest)
    if manifest.get('inventory_id') != read(prior / 'plan.json').get('inventory_id'):
        raise ValueError('Prior inventory ID mismatch')
    candidates = read(prior / 'candidates.json')
    selection = read(prior / 'selection.json')
    return ({p['post_id'] for p in candidates} | {p['post_id'] for p in selection}, file_hash(manifest_path))


def prepare(database: Path, output: Path, *, snapshot: str, start: str, end: str,
            ceiling: int = 1000, prior_inventories: list[Path] | None = None) -> dict:
    if output.exists():
        raise FileExistsError('Use a new inventory directory')
    after, before = pilot.timestamp(start), pilot.timestamp(end)
    if (after >= before or after % 86400 or before % 86400 or
            not 1 <= ceiling <= 1000 or before - after > 31 * 86400):
        raise ValueError('Require UTC day boundaries, <=31 days, and ceiling 1..1000')
    prior_inventories = [Path(p).resolve() for p in (prior_inventories or [])]
    prior_pool = set()
    prior_files = {}
    for prior in prior_inventories:
        ids, sha = prior_ids(prior)
        prior_pool.update(ids)
        prior_files[str(prior)] = sha
    baseline = pilot.audit_database(database, snapshot)
    plan = {'version': VERSION, 'created_at': pilot.now(), 'start': pilot.iso(after),
            'end_exclusive': pilot.iso(before), 'subreddits': list(SUBREDDITS),
            'candidate_ceiling': ceiling, 'max_pages_per_subreddit': MAX_PAGES_PER_DAY,
            'page_size': 100, 'min_score': 10, 'min_comments': 3,
            'require_direct_image': True, 'selection': 'UTC day, source timestamp, post ID ascending',
            'prior_inventories': prior_files, 'prior_pool_ids': sorted(prior_pool),
            'request_delay_seconds': 3, 'max_json_attempts': 3,
            'max_retry_wait_seconds': 60, 'max_image_bytes': MAX_IMAGE_BYTES,
            'comments': {'limit': 100, 'depth': 1, 'sort': 'top', 'raw_json': 1},
            'code_sha256': code_hashes(), 'baseline_sha256': digest(baseline),
            'model_budget_usd': 0, 'model_calls': 0,
            'limits': ['Archive discovery completeness is not established.',
                       'Comments are top-level samples; replies and morechildren are not expanded.',
                       'Missing assets and comments do not cause replacement selection.']}
    plan['inventory_id'] = digest(plan)
    pilot.write(output / 'baseline.json', baseline)
    pilot.write(output / 'plan.json', plan)
    return plan


class RequestFailure(Exception):
    def __init__(self, reason: str, *, stop: str | None = None):
        super().__init__(reason)
        self.stop = stop


def retry_delay(value: str | None, fallback: int) -> float:
    if not value:
        return float(fallback)
    try:
        return max(0., float(value))
    except ValueError:
        try:
            at = parsedate_to_datetime(value)
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            return max(0., (at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return float(fallback)


def refusal(status: int, payload) -> bool:
    if status not in (403, 429):
        return False
    message = json.dumps(payload).lower() if payload is not None else ''
    return any(term in message for term in ('agent', 'user-agent', 'user agent',
                                            'free scraping resources', 'access denied', 'forbidden'))


class Recorder:
    """Persist public GET evidence without request headers or authentication bodies."""
    def __init__(self, output: Path, plan: dict, client: httpx.AsyncClient):
        self.output, self.plan, self.client = output, plan, client
        self.stops: dict[str, str] = {}

    def path(self, url: str, params: dict) -> Path:
        return self.output / 'requests' / (digest({'url': url, 'params': params}) + '.json')

    async def get(self, url: str, params: dict, headers: dict | None = None,
                  *, service: str = 'archive'):
        if service in self.stops:
            raise RequestFailure(self.stops[service], stop=self.stops[service])
        key = {'url': url, 'params': params}
        path = self.path(url, params)
        if path.exists():
            record = read(path)
            if (record.get('request') != key or record.get('record_sha256') !=
                    digest({k: v for k, v in record.items() if k != 'record_sha256'})):
                raise ValueError('Cached request changed')
        else:
            record = {'request': key, 'attempts': [], 'status': 'error'}
            for attempt in range(self.plan['max_json_attempts']):
                await asyncio.sleep(self.plan['request_delay_seconds'])
                row = {'requested_at': pilot.now()}
                transient, delay = False, (10 if attempt == 0 else 30)
                try:
                    response = await self.client.get(url, params=params, headers=headers)
                    row['http_status'] = response.status_code
                    row['retry_after'] = response.headers.get('retry-after')
                    try:
                        row['payload'] = response.json()
                    except ValueError:
                        row['error'] = 'invalid_json'
                    status = response.status_code
                    if status == 200 and 'payload' in row:
                        record['status'] = 'ok'
                    elif refusal(status, row.get('payload')):
                        record['stop'] = 'explicit_agent_refusal'
                    elif status in (429, 500, 502, 503, 504):
                        transient = True
                        delay = retry_delay(row['retry_after'], delay)
                        if delay > self.plan['max_retry_wait_seconds']:
                            record['stop'] = 'excessive_retry_after'
                            transient = False
                    elif status == 403:
                        record['stop'] = 'forbidden'
                    elif status == 401 and service == 'reddit':
                        record['stop'] = 'unauthorized'
                except httpx.HTTPError as exc:
                    row['error'] = type(exc).__name__
                    transient = True
                record['attempts'].append(row)
                if record['status'] == 'ok' or record.get('stop') or not transient or attempt == self.plan['max_json_attempts'] - 1:
                    break
                await asyncio.sleep(delay)
            record['record_sha256'] = digest(record)
            pilot.write(path, record)
        if record.get('stop'):
            self.stops[service] = record['stop']
        if record['status'] != 'ok':
            last = record['attempts'][-1]
            raise RequestFailure(f"HTTP {last.get('http_status', 'unavailable')}; "
                                 f"{last.get('error', record.get('stop', 'request_failed'))}",
                                 stop=record.get('stop'))
        return record['attempts'][-1]['payload']


async def collect_image(output: Path, post: dict, client: httpx.AsyncClient) -> dict:
    pid = post['post_id']
    meta = output / 'image_records' / f'{pid}.json'
    if meta.exists():
        record = read(meta)
        if record.get('url') != post['image_url'] or record.get('record_sha256') != digest(
                {k: v for k, v in record.items() if k != 'record_sha256'}):
            raise ValueError('Cached image record changed')
        if record['status'] == 'available':
            checked(output / record['path'], record['sha256'], 'Cached image')
        return record
    record = {'url': post['image_url'], 'requested_at': pilot.now(), 'attempts': [],
              'status': 'error'}
    try:
        _validate_image_url(post['image_url'])
        for attempt in range(3):
            row = {'requested_at': pilot.now()}
            transient, delay = False, 10 if attempt == 0 else 30
            payload = None
            try:
                async with client.stream('GET', post['image_url']) as response:
                    row['http_status'] = response.status_code
                    row['retry_after'] = response.headers.get('retry-after')
                    record['http_status'] = response.status_code
                    if response.status_code == 200:
                        payload = bytearray()
                        async for chunk in response.aiter_bytes():
                            payload.extend(chunk)
                            if len(payload) > MAX_IMAGE_BYTES:
                                raise ValueError('Image exceeds byte limit')
                    elif response.status_code == 429 or response.status_code >= 500:
                        transient = True
                        delay = retry_delay(row['retry_after'], delay)
                        if delay > 60:
                            record['stop'] = 'excessive_retry_after'
                            transient = False
                    else:
                        row['error'] = 'HTTPStatusError'
                if payload is not None:
                    with Image.open(io.BytesIO(payload)) as image:
                        record.update(width=image.width, height=image.height, format=image.format,
                                      frames=getattr(image, 'n_frames', 1))
                        image.load()  # Decode pixels, not just container metadata.
                    path = output / 'images' / pid
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_suffix('.tmp')
                    temporary.write_bytes(payload)
                    temporary.replace(path)
                    record.update(status='available', path=str(path.relative_to(output)),
                                  sha256=file_hash(path), bytes=len(payload))
            except httpx.TransportError as exc:
                row['error'] = type(exc).__name__
                transient = True
            except (OSError, ValueError, Image.DecompressionBombError) as exc:
                row['error'] = type(exc).__name__
            record['attempts'].append(row)
            if record['status'] == 'available' or not transient or attempt == 2:
                break
            await asyncio.sleep(delay)
        if record['status'] != 'available':
            record['error_type'] = record['attempts'][-1].get('error', 'HTTPStatusError')
    except (httpx.HTTPError, OSError, ValueError, Image.DecompressionBombError) as exc:
        record.update(status='error', error_type=type(exc).__name__)
    record['record_sha256'] = digest(record)
    pilot.write(meta, record)
    return record


def dates(plan: dict):
    current = pilot.timestamp(plan['start'])
    before = pilot.timestamp(plan['end_exclusive'])
    while current < before:
        yield pilot.iso(current)[:10]
        current += 86400


def checkpoint_path(output: Path, day: str) -> Path:
    return output / 'days' / f'{day}.json'


def verify_checkpoint(output: Path, day: str) -> dict:
    path = checkpoint_path(output, day)
    record = read(path)
    if record.get('record_sha256') != digest({k: v for k, v in record.items() if k != 'record_sha256'}):
        raise ValueError(f'Daily checkpoint changed: {day}')
    if record['day'] != day:
        raise ValueError(f'Daily checkpoint day changed: {day}')
    return record


async def discover_day(plan: dict, day: str, source: str, recorder: Recorder) -> dict:
    day_start = pilot.timestamp(day + 'T00:00:00+00:00')
    local_plan = {**plan, 'start': pilot.iso(day_start),
                  'end_exclusive': pilot.iso(day_start + 86400)}
    async def fetch(url, params):
        try:
            return await recorder.get(url, params, service='archive')
        except RequestFailure as exc:
            raise pilot.RequestFailure(str(exc)) from exc
    result = await pilot.discover(local_plan, source, fetch)
    result['day'] = day
    if recorder.stops.get('archive'):
        result['stop_reason'] = recorder.stops['archive']
    return result


def select_day(day_results: list[dict], existing: set[str], selected_ids: set[str],
               prior: set[str], remaining: int) -> tuple[list[dict], dict]:
    by_id = {}
    excluded = Counter()
    for result in day_results:
        for post in result.get('posts', []):
            pid = post['post_id']
            if pid in existing:
                excluded['archive_overlap'] += 1
            elif pid in prior:
                excluded['prior_inventory_overlap'] += 1
            elif pid in selected_ids or pid in by_id:
                excluded['duplicate_discovery'] += 1
            else:
                by_id[pid] = post
    ordered = sorted(by_id.values(), key=lambda p: (p['created_utc'], p['post_id']))
    selected = []
    for post in ordered[:remaining]:
        selected.append({**post, 'in_existing_corpus': False,
                         'in_original_release': False})
    excluded['ceiling_not_selected'] = max(0, len(ordered) - remaining)
    return selected, dict(excluded)


async def _run(output: Path, plan: dict, baseline: dict, *, client: httpx.AsyncClient,
               authenticate=None) -> dict:
    recorder = Recorder(output, plan, client)
    existing = {p['post_id'] for p in baseline['posts']}
    prior = set(plan['prior_pool_ids'])
    all_days = list(dates(plan))
    selection_path = output / 'selection.json'
    selected, coverage = [], []
    selected_ids = set()
    stop = None
    for index, day in enumerate(all_days):
        cp = checkpoint_path(output, day)
        if cp.exists():
            record = verify_checkpoint(output, day)
            day_selected = record['selected']
            if selected_ids & {p['post_id'] for p in day_selected}:
                raise ValueError('Repeated ID in daily checkpoints')
            selected.extend(day_selected)
            selected_ids.update(p['post_id'] for p in day_selected)
            coverage.append({k: v for k, v in record.items() if k not in ('selected', 'record_sha256')})
            stop = record.get('stop') or stop
            if stop:
                recorder.stops['archive'] = stop
                break
            continue
        if stop or len(selected) >= plan['candidate_ceiling']:
            break
        discoveries = []
        for source in SUBREDDITS:
            if recorder.stops.get('archive'):
                discoveries.append({'subreddit': source, 'day': day, 'posts': [], 'pages': [],
                                    'stop_reason': 'unattempted_service_stop', 'excluded': {}})
                break
            discoveries.append(await discover_day(plan, day, source, recorder))
        day_selected, exclusions = select_day(discoveries, existing, selected_ids, prior,
                                              plan['candidate_ceiling'] - len(selected))
        selected.extend(day_selected)
        selected_ids.update(p['post_id'] for p in day_selected)
        stop = recorder.stops.get('archive')
        record = {'day': day, 'sources': discoveries, 'selected': day_selected,
                  'excluded': exclusions, 'stop': stop,
                  'selected_cumulative': len(selected), 'completed_at': pilot.now()}
        record['record_sha256'] = digest(record)
        pilot.write(cp, record)
        print(f"{day}: {len(day_selected)} selected, cumulative {len(selected)}; "
              f"archive stop {stop or 'none'}", flush=True)
        coverage.append({k: v for k, v in record.items() if k not in ('selected', 'record_sha256')})
    if selection_path.exists():
        prior_selection = read(selection_path)
        if prior_selection != selected:
            raise ValueError('Frozen selection changed')
    else:
        pilot.write(selection_path, selected)
    # Asset retrieval follows frozen selection. Missing evidence never prompts replacement.
    candidate_path = output / 'candidates.json'
    candidates = read(candidate_path) if candidate_path.exists() else []
    if candidates != sorted(candidates, key=lambda c: next(
            (i for i, p in enumerate(selected) if p['post_id'] == c['post_id']), -1)):
        raise ValueError('Candidate order changed')
    if any(c['post_id'] != selected[i]['post_id'] for i, c in enumerate(candidates)):
        raise ValueError('Candidate prefix changed')
    for row in candidates:
        stored = read(output / 'candidate_records' / f"{row['post_id']}.json")
        if stored.get('record_sha256') != digest({k: v for k, v in stored.items() if k != 'record_sha256'}) or \
                {k: v for k, v in stored.items() if k != 'record_sha256'} != row:
            raise ValueError('Candidate record changed')
        record = read(output / 'image_records' / f"{row['post_id']}.json")
        if row['image'] != record or record.get('record_sha256') != digest(
                {k: v for k, v in record.items() if k != 'record_sha256'}):
            raise ValueError('Candidate image evidence changed')
        if record['status'] == 'available':
            checked(output / record['path'], record['sha256'], 'Cached image')
    token = None
    auth_error = None
    for post in selected[len(candidates):]:
        url = f"https://oauth.reddit.com/r/{post['subreddit']}/comments/{post['post_id']}"
        comment_record = {'status': 'error'}
        try:
            if 'reddit' in recorder.stops:
                raise RequestFailure(recorder.stops['reddit'], stop=recorder.stops['reddit'])
            request_path = recorder.path(url, plan['comments'])
            if not request_path.exists() and token is None:
                if authenticate is None:
                    raise RequestFailure('Reddit authentication unavailable')
                try:
                    token = await authenticate()
                    pilot.write(output / 'auth.json', {'status': 'ok', 'checked_at': pilot.now()})
                except Exception as exc:
                    auth_error = type(exc).__name__
                    pilot.write(output / 'auth.json', {'status': 'error', 'error_type': auth_error,
                                                       'checked_at': pilot.now()})
                    recorder.stops['reddit'] = 'authentication_failure'
                    raise RequestFailure('Reddit authentication failed', stop='authentication_failure') from exc
            payload = await recorder.get(url, plan['comments'],
                                         {'Authorization': f'Bearer {token}'} if token else None,
                                         service='reddit')
            comment_record = pilot.parse_comments(payload, post['post_id'])
        except (RequestFailure, ValueError, TypeError, KeyError) as exc:
            comment_record['error_type'] = type(exc).__name__
            comment_record['error'] = str(exc)
        image_record = await collect_image(output, post, client)
        live = comment_record.get('live_post', {})
        mismatches = [k for k in ('created_utc', 'subreddit') if live and live.get(k) != post[k]]
        if live and live.get('url') != post['image_url']:
            mismatches.append('image_url')
        candidates.append({**post, 'source_date': pilot.iso(post['created_utc']),
                           'image': image_record, 'comment_retrieval': comment_record,
                           'source_mismatches': mismatches})
        frozen = {**candidates[-1], 'record_sha256': digest(candidates[-1])}
        pilot.write(output / 'candidate_records' / f"{post['post_id']}.json", frozen)
        pilot.write(candidate_path, candidates)
        if len(candidates) % 10 == 0:
            print(f"Assets/comments recorded: {len(candidates)}/{len(selected)}", flush=True)
    if not candidate_path.exists():
        pilot.write(candidate_path, candidates)
    summaries = []
    for offset in range(0, len(all_days), 7):
        chunk = all_days[offset:offset + 7]
        visited = [c for c in coverage if c['day'] in chunk]
        summaries.append({'start': chunk[0], 'end_exclusive':
                          pilot.iso(pilot.timestamp(chunk[-1] + 'T00:00:00+00:00') + 86400)[:10],
                          'attempted_days': len(visited),
                          'selected': sum(len(read(checkpoint_path(output, c['day']))['selected']) for c in visited),
                          'source_stops': [{ 'day': c['day'], 'stop': c['stop']} for c in visited if c.get('stop')]})
    pilot.write(output / 'checkpoints.json', summaries)
    requests = [read(p) for p in sorted((output / 'requests').glob('*.json'))]
    report = {'inventory_id': plan['inventory_id'], 'source_window': [plan['start'], plan['end_exclusive']],
              'candidate_ceiling': plan['candidate_ceiling'], 'selected': len(selected),
              'candidate_ids_sha256': digest([c['post_id'] for c in candidates]),
              'daily_coverage': coverage, 'seven_day_checkpoints': summaries,
              'unattempted_partitions': [{'day': day, 'subreddit': sub} for day in all_days
                                         for sub in SUBREDDITS if not any(
                                             c['day'] == day and any(d['subreddit'] == sub and
                                             d.get('stop_reason') != 'unattempted_service_stop'
                                             for d in c['sources']) for c in coverage)],
              'stop_reason': recorder.stops.get('archive') or ('candidate_ceiling' if len(selected) >=
                              plan['candidate_ceiling'] else 'end_of_window'),
              'source_stops': {'archive': recorder.stops.get('archive'),
                               'reddit': recorder.stops.get('reddit')},
              'prior_pool_ids': plan['prior_pool_ids'],
              'selected_by_subreddit': dict(Counter(c['subreddit'] for c in candidates)),
              'selected_by_source_day': dict(Counter(c['source_date'][:10] for c in candidates)),
              'images': dict(Counter(c['image']['status'] for c in candidates)),
              'comments': dict(Counter(c['comment_retrieval']['status'] for c in candidates)),
              'at_least_3_comments_and_image': sum(c['image']['status'] == 'available' and
                    c['comment_retrieval'].get('usable_count', 0) >= 3 and not c['source_mismatches']
                    for c in candidates),
              'source_mismatch_cases': [c['post_id'] for c in candidates if c['source_mismatches']],
              'comment_thread_completeness': 'Not established; top-level sample only.',
              'image_bytes': sum(c['image'].get('bytes', 0) for c in candidates),
              'json_requests': len(requests),
              'json_attempts': sum(len(r['attempts']) for r in requests),
              'http_statuses': dict(Counter(str(a.get('http_status', 'transport_error'))
                                    for r in requests for a in r['attempts'])),
              'model_calls': 0, 'model_cost_usd': 0, 'limits': plan['limits']}
    pilot.write(output / 'report.json', report)
    pilot.write(output / 'manifest.json', {'inventory_id': plan['inventory_id'], 'files': {
        str(p.relative_to(output)): file_hash(p) for p in sorted(output.rglob('*'))
        if p.is_file() and p.name not in ('run.lock', 'manifest.json') and p.suffix != '.tmp'}})
    return report


async def run(output: Path, *, client: httpx.AsyncClient | None = None, authenticate=None) -> dict:
    output = Path(output)
    with (output / 'run.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan, baseline = read(output / 'plan.json'), read(output / 'baseline.json')
        if (plan.get('inventory_id') != digest({k: v for k, v in plan.items() if k != 'inventory_id'})
                or plan.get('baseline_sha256') != digest(baseline)
                or plan.get('code_sha256') != code_hashes()
                or plan.get('subreddits') != list(SUBREDDITS)):
            raise ValueError('Frozen plan, baseline or code changed')
        for prior, expected in plan['prior_inventories'].items():
            checked(Path(prior) / 'manifest.json', expected, 'Prior inventory manifest')
            ids, _ = prior_ids(Path(prior))
            if not ids <= set(plan['prior_pool_ids']):
                raise ValueError('Prior inventory IDs changed')
        manifest_path = output / 'manifest.json'
        if manifest_path.exists():
            manifest = read(manifest_path)
            if manifest.get('inventory_id') != plan['inventory_id']:
                raise ValueError('Inventory ID changed')
            verify_manifest(output, manifest)
            return read(output / 'report.json')
        if client is not None:
            return await _run(output, plan, baseline, client=client, authenticate=authenticate)
        config = Config()
        async with httpx.AsyncClient(timeout=30, headers={'User-Agent': config.reddit_user_agent}) as http:
            async def auth():
                # No token endpoint response is recorded in inventory artifacts.
                from basedbench.reddit.client import RedditClient
                async with RedditClient(config) as reddit:
                    await reddit.authenticate()
                    return reddit._access_token
            return await _run(output, plan, baseline, client=http, authenticate=auth)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('output', type=Path)
    prep.add_argument('--database', type=Path, default=Path('data/basedbench.db'))
    prep.add_argument('--snapshot', default='basedBench-519-2026-07')
    prep.add_argument('--start', required=True)
    prep.add_argument('--end', required=True)
    prep.add_argument('--ceiling', type=int, default=1000)
    prep.add_argument('--prior-inventory', type=Path, action='append', default=[])
    execute = commands.add_parser('run')
    execute.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.database, args.output, snapshot=args.snapshot,
                         start=args.start, end=args.end, ceiling=args.ceiling,
                         prior_inventories=args.prior_inventory)
    else:
        result = asyncio.run(run(args.output))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
