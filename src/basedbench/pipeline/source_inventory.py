"""Bounded, replayable source inventory. No model calls or corpus database writes."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3

import httpx
from PIL import Image

from basedbench.config import Config
from basedbench.pipeline.curation_corpus import digest, file_hash
from basedbench.reddit import client as reddit_client, images, pullpush
from basedbench.reddit.client import RedditClient
from basedbench.reddit.images import MAX_IMAGE_BYTES, _validate_image_url
from basedbench.reddit.pullpush import PULLPUSH_BASE, _to_pullpush_post

VERSION = 'source-inventory-v1'
SUBREDDITS = ('ExplainTheJoke', 'PeterExplainsTheJoke', 'explainitpeter')


def code_hashes() -> dict:
    return {Path(p).name: file_hash(Path(p)) for p in
            (__file__, reddit_client.__file__, images.__file__, pullpush.__file__)}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def timestamp(value: str) -> int:
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def iso(value: int | float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def audit_database(database: Path, snapshot: str) -> dict:
    """Read a consistent transaction; preserve the baseline ID list for overlap."""
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        release = db.execute('SELECT * FROM snapshots WHERE name=? OR snapshot_id=?',
                             (snapshot, snapshot)).fetchone()
        if release is None:
            raise ValueError('Unknown release snapshot')
        posts = [dict(r) for r in db.execute(
            'SELECT post_id,subreddit,created_utc,retrieved_at FROM memes ORDER BY post_id')]
        ids = [r[0] for r in db.execute(
            'SELECT post_id FROM snapshot_memes WHERE snapshot_id=? ORDER BY post_id',
            (release['snapshot_id'],))]
        pushes = [dict(r) for r in db.execute(
            'SELECT * FROM dataset_pushes WHERE snapshot_id=?', (release['snapshot_id'],))]
    release_ids = set(ids)

    def coverage(rows):
        dates = sorted(r['created_utc'] for r in rows if r['created_utc'])
        return {'count': len(rows), 'oldest': dates[0] if dates else None,
                'newest': dates[-1] if dates else None,
                'missing_dates': sum(not r['created_utc'] for r in rows)}

    members = [p for p in posts if p['post_id'] in release_ids]
    if len(ids) != release['meme_count'] or len(members) != len(ids):
        raise ValueError('Snapshot membership mismatch')
    return {'release': dict(release), 'pushes': pushes, 'release_ids': ids,
            'release_coverage': coverage(members), 'archive_coverage': coverage(posts),
            'release_by_subreddit': {s: coverage([p for p in members if p['subreddit'] == s])
                                     for s in SUBREDDITS},
            'archive_by_subreddit': {s: coverage([p for p in posts if p['subreddit'] == s])
                                     for s in SUBREDDITS},
            'latest_retrieval': max(p['retrieved_at'] for p in posts), 'posts': posts,
            'limitation': 'Observed source dates and membership, not proof of exhaustive coverage.'}


def prepare(database: Path, output: Path, *, snapshot: str, start: str, end: str,
            ceiling: int = 100, max_pages: int = 10) -> dict:
    if output.exists():
        raise ValueError('Use a new output directory for each inventory plan')
    after, before = timestamp(start), timestamp(end)
    if after >= before or not 1 <= ceiling <= 100 or not 1 <= max_pages <= 10:
        raise ValueError('Require start < end, ceiling 1..100, pages 1..10 per subreddit')
    baseline = audit_database(database, snapshot)
    plan = {'version': VERSION, 'created_at': now(), 'start': iso(after), 'end_exclusive': iso(before),
            'subreddits': list(SUBREDDITS), 'candidate_ceiling': ceiling,
            'max_pages_per_subreddit': max_pages, 'page_size': 100,
            'min_score': 10, 'min_comments': 3, 'require_direct_image': True,
            'selection': 'Exclude baseline post IDs, SHA256(seed:post_id), round-robin subreddits.',
            'selection_seed': VERSION, 'model_budget_usd': 0, 'model_calls': 0,
            'request_delay_seconds': 3, 'max_json_attempts': 3,
            'max_retry_wait_seconds': 30, 'max_image_bytes': MAX_IMAGE_BYTES,
            'comments': {'limit': 100, 'depth': 1, 'sort': 'top', 'raw_json': 1},
            'code_sha256': code_hashes(), 'baseline_sha256': digest(baseline),
            'limits': ['Discovery may stop at page cap; archive completeness is unknown.',
                       'Comments are a top-level sample; replies/morechildren are not expanded.',
                       'NSFW metadata is retained, not an admission decision.',
                       'No answer, content, suitability or duplicate-family judgments are made.']}
    plan['inventory_id'] = digest(plan)
    write(output / 'baseline.json', baseline)
    write(output / 'plan.json', plan)
    return plan


class RequestFailure(Exception):
    pass


class Recorder:
    """Persist every public JSON attempt, excluding auth headers and token responses."""
    def __init__(self, output: Path, plan: dict, client: httpx.AsyncClient):
        self.output, self.plan, self.client = output, plan, client

    def path(self, url: str, params: dict) -> Path:
        return self.output / 'requests' / (digest({'url': url, 'params': params}) + '.json')

    async def get(self, url: str, params: dict, headers: dict | None = None) -> dict:
        key = {'url': url, 'params': params}
        path = self.path(url, params)
        if path.exists():
            record = json.loads(path.read_text())
            if record['request'] != key or record['record_sha256'] != digest(
                {k: v for k, v in record.items() if k != 'record_sha256'}
            ):
                raise ValueError('Cached request changed')
        else:
            record = {'request': key, 'attempts': [], 'status': 'error'}
            for attempt in range(self.plan['max_json_attempts']):
                await asyncio.sleep(self.plan['request_delay_seconds'])
                row = {'requested_at': now()}
                retry, delay = False, self.plan['request_delay_seconds']
                try:
                    response = await self.client.get(url, params=params, headers=headers)
                    row['http_status'] = response.status_code
                    row['retry_after'] = response.headers.get('retry-after')
                    try:
                        row['payload'] = response.json()
                    except ValueError:
                        row['error'] = 'invalid_json'
                    retry = response.status_code == 429 or response.status_code >= 500
                    if retry:
                        try:
                            delay = max(delay, float(row['retry_after'] or 10))
                        except ValueError:
                            delay = 10
                        if delay > self.plan['max_retry_wait_seconds']:
                            retry = False
                    if response.status_code == 200 and 'payload' in row:
                        record['status'] = 'ok'
                except httpx.HTTPError as e:
                    row['error'] = type(e).__name__
                    retry = True
                record['attempts'].append(row)
                if not retry or attempt + 1 == self.plan['max_json_attempts']:
                    break
                await asyncio.sleep(delay)
            record['record_sha256'] = digest(record)
            write(path, record)
        if record['status'] != 'ok':
            last = record['attempts'][-1]
            raise RequestFailure(f"HTTP {last.get('http_status', 'unavailable')}; "
                                 f"{last.get('error', 'request_failed')}")
        return record['attempts'][-1]['payload']


def parse_page(payload) -> list[dict]:
    if (not isinstance(payload, dict) or payload.get('error')
            or not isinstance(payload.get('data'), list)
            or not all(isinstance(row, dict) for row in payload['data'])):
        raise RequestFailure('Malformed archive response or archive error')
    if len(payload['data']) > 100:
        raise RequestFailure('Archive exceeded requested page size')
    return payload['data']


async def discover(plan: dict, subreddit: str, fetch) -> dict:
    """Walk descending timestamps with overlap; never skip the boundary second.

    Saturated timestamps, non-progress, errors and caps are explicit gaps. A
    source-exhausted result only describes this API, not all historical Reddit.
    """
    start, end = timestamp(plan['start']), timestamp(plan['end_exclusive'])
    cursor = end
    seen, posts, pages = set(), [], []
    rejected = Counter()
    stop = 'page_cap'
    for _ in range(plan['max_pages_per_subreddit']):
        params = {'subreddit': subreddit, 'after': start - 1, 'before': cursor,
                  'size': 100, 'sort': 'desc', 'sort_type': 'created_utc'}
        page_info = {'params': params}
        pages.append(page_info)
        try:
            raw = parse_page(await fetch(PULLPUSH_BASE, params))
        except RequestFailure as e:
            page_info['error'] = str(e)
            stop = 'request_error'
            break
        page_info['raw_count'] = len(raw)
        dates = []
        for row in raw:
            try:
                post = _to_pullpush_post(row)
            except (ValueError, TypeError, OverflowError):
                post = None
            if post is None or not re.fullmatch('[a-zA-Z0-9]+', post.post_id):
                rejected['malformed'] += 1
                continue
            if not start <= post.created_utc < cursor:
                rejected['outside_requested_window'] += 1
                continue
            if post.subreddit.lower() != subreddit.lower():
                rejected['wrong_subreddit'] += 1
                continue
            dates.append(post.created_utc)
            if post.post_id in seen:
                rejected['pagination_overlap'] += 1
                continue
            seen.add(post.post_id)
            if post.image_url is None:
                rejected['no_direct_image'] += 1
            elif post.score < plan['min_score']:
                rejected['low_score'] += 1
            elif post.num_comments < plan['min_comments']:
                rejected['few_comments'] += 1
            else:
                posts.append(asdict(post))
        page_info['oldest'] = iso(min(dates)) if dates else None
        if len(dates) != len(raw):
            stop = 'invalid_page'
            break
        if len(raw) < 100:
            stop = 'source_exhausted'
            break
        # Including the boundary second lets us detect a tie overflow rather
        # than silently dropping records with the same timestamp.
        next_cursor = int(min(dates)) + 1
        if next_cursor >= cursor:
            stop = 'timestamp_stalled'
            break
        cursor = next_cursor
    return {'subreddit': subreddit, 'posts': posts, 'pages': pages,
            'stop_reason': stop, 'source_exhausted': stop == 'source_exhausted',
            'archive_completeness': 'unknown', 'distinct_posts_seen': len(seen),
            'excluded': dict(rejected), 'remaining_before': iso(cursor)}


def select_candidates(discoveries: list[dict], baseline: dict, plan: dict) -> list[dict]:
    existing, release = {p['post_id'] for p in baseline['posts']}, set(baseline['release_ids'])
    pools, seen = [], set()
    for discovery in discoveries:
        pool = []
        for post in discovery['posts']:
            post = dict(post)
            post['in_existing_corpus'] = post['post_id'] in existing
            post['in_original_release'] = post['post_id'] in release
            if post['in_existing_corpus'] or post['post_id'] in seen:
                continue
            seen.add(post['post_id'])
            pool.append(post)
        pool.sort(key=lambda p: hashlib.sha256(
            f"{plan['selection_seed']}:{p['post_id']}".encode()).hexdigest())
        pools.append(pool)
    selected = []
    while len(selected) < plan['candidate_ceiling'] and any(pools):
        for pool in pools:
            if pool and len(selected) < plan['candidate_ceiling']:
                selected.append(pool.pop(0))
    return selected


def parse_comments(payload, post_id: str) -> dict:
    try:
        source_post = payload[0]['data']['children'][0]['data']
        children = payload[1]['data']['children']
        if source_post['id'] != post_id or not isinstance(children, list):
            raise ValueError('Post mismatch')
    except (TypeError, KeyError, IndexError, AttributeError) as e:
        raise ValueError('Malformed comment response') from e
    comments, excluded, ids = [], Counter(), set()
    more_count, more_ids = 0, []
    for child in children:
        if not isinstance(child, dict) or not isinstance(child.get('data'), dict):
            raise ValueError('Malformed comment child')
        data = child.get('data', {})
        if child.get('kind') == 'more':
            more_count += data.get('count', 0) or 0
            more_ids.extend(data.get('children', []) or [])
            continue
        if child.get('kind') != 't1':
            excluded['non_comment'] += 1
            continue
        author, body = data.get('author') or '', data.get('body') or ''
        cid = data.get('id') or ''
        if not cid or not body or cid in ids:
            excluded['missing_or_duplicate'] += 1
            continue
        ids.add(cid)
        if body in ('[removed]', '[deleted]'):
            excluded['removed_or_deleted'] += 1
        elif author == 'AutoModerator' or author.lower().startswith('bot') or data.get('distinguished') == 'moderator':
            excluded['bot_or_moderator'] += 1
        else:
            comments.append({'comment_id': cid, 'author': author, 'body': body,
                             'score': int(data.get('score') or 0),
                             'created_utc': data.get('created_utc'),
                             'parent_id': data.get('parent_id'), 'is_moderator': False})
    comments.sort(key=lambda c: (-c['score'], c['comment_id']))
    return {'status': 'available' if comments else 'empty_after_filtering',
            'comments': comments, 'usable_count': len(comments), 'excluded': dict(excluded),
            'reported_num_comments': source_post.get('num_comments'),
            'listing_children': len(children), 'more_count': more_count,
            'more_ids': more_ids, 'complete_thread': False, 'scope': 'top-level, top sort, limit 100, depth 1',
            'live_post': {k: source_post.get(k) for k in
                          ('id', 'created_utc', 'subreddit', 'url', 'over_18',
                           'removed_by_category', 'is_self', 'title')}}


async def collect_image(output: Path, post: dict, client: httpx.AsyncClient) -> dict:
    pid = post['post_id']
    meta_path = output / 'image_records' / f'{pid}.json'
    if meta_path.exists():
        record = json.loads(meta_path.read_text())
        if record.get('status') == 'available' and file_hash(output / record['path']) != record['sha256']:
            raise ValueError('Cached image changed')
        return record
    record = {'url': post['image_url'], 'requested_at': now()}
    try:
        _validate_image_url(post['image_url'])
        async with client.stream('GET', post['image_url']) as response:
            record['http_status'] = response.status_code
            response.raise_for_status()
            payload = bytearray()
            async for chunk in response.aiter_bytes():
                payload.extend(chunk)
                if len(payload) > MAX_IMAGE_BYTES:
                    raise ValueError('Image exceeds byte limit')
        with Image.open(io.BytesIO(payload)) as img:
            record.update(width=img.width, height=img.height, format=img.format,
                          frames=getattr(img, 'n_frames', 1))
            img.verify()
        path = output / 'images' / pid
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(payload)
        temporary.replace(path)
        record.update(status='available', path=str(path.relative_to(output)),
                      sha256=file_hash(path), bytes=len(payload))
    except Exception as e:
        record.update(status='error', error_type=type(e).__name__)
    write(meta_path, record)
    return record


def report_inventory(plan: dict, baseline: dict, discoveries: list[dict], candidates: list[dict], output: Path) -> dict:
    existing = {p['post_id'] for p in baseline['posts']}
    release = set(baseline['release_ids'])
    all_posts = {p['post_id']: p for d in discoveries for p in d['posts']}
    requests = [json.loads(p.read_text()) for p in sorted((output / 'requests').glob('*.json'))]
    counts = lambda key: dict(Counter(c[key]['status'] for c in candidates))
    readiness = sum(c['image']['status'] == 'available' and
                    c['comment_retrieval'].get('usable_count', 0) >= 3 and
                    not c.get('source_mismatches') for c in candidates)
    return {'inventory_id': plan['inventory_id'], 'source_window': [plan['start'], plan['end_exclusive']],
            'candidate_ceiling': plan['candidate_ceiling'], 'selected': len(candidates),
            'candidate_ids_sha256': digest([c['post_id'] for c in candidates]),
            'qualifying_discovered': len(all_posts),
            'overlap_with_corpus': len(set(all_posts) & existing),
            'overlap_with_release': len(set(all_posts) & release),
            'selected_by_subreddit': dict(Counter(c['subreddit'] for c in candidates)),
            'selected_by_source_day': dict(Counter(iso(c['created_utc'])[:10] for c in candidates)),
            'images': counts('image'), 'comments': counts('comment_retrieval'),
            'at_least_3_comments_and_image': readiness,
            'source_mismatch_cases': [c['post_id'] for c in candidates if c.get('source_mismatches')],
            'has_unexpanded_comments': sum(c['comment_retrieval'].get('more_count', 0) > 0 for c in candidates),
            'comment_thread_completeness': 'Not established; no replies or morechildren expansion.',
            'image_bytes': sum(c['image'].get('bytes', 0) for c in candidates),
            'discovery': [{k: v for k, v in d.items() if k != 'posts'} for d in discoveries],
            'json_requests': len(requests), 'json_attempts': sum(len(r['attempts']) for r in requests),
            'http_statuses': dict(Counter(str(a.get('http_status', 'transport_error'))
                                          for r in requests for a in r['attempts'])),
            'model_calls': 0, 'model_cost_usd': 0,
            'limits': plan['limits'] + ['Candidate readiness is asset/evidence availability, not admission.']}


async def run(output: Path) -> dict:
    plan, baseline = [json.loads((output / f'{name}.json').read_text()) for name in ('plan', 'baseline')]
    if (plan['inventory_id'] != digest({k: v for k, v in plan.items() if k != 'inventory_id'})
            or plan['baseline_sha256'] != digest(baseline)
            or plan['code_sha256'] != code_hashes()):
        raise ValueError('Frozen plan, baseline or code changed; prepare a new inventory')
    manifest_path = output / 'manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        for name, expected in manifest['files'].items():
            if file_hash(output / name) != expected:
                raise ValueError(f'Frozen artifact changed: {name}')
        return json.loads((output / 'report.json').read_text())
    config = Config()
    discoveries, candidates = [], []
    async with httpx.AsyncClient(timeout=30, headers={'User-Agent': config.reddit_user_agent}) as client:
        recorder = Recorder(output, plan, client)
        for sub in plan['subreddits']:
            d = await discover(plan, sub, recorder.get)
            discoveries.append(d)
            write(output / 'discovery.json', discoveries)
            print(f"{sub}: {len(d['posts'])} qualifying; {d['stop_reason']}", flush=True)
        selected = select_candidates(discoveries, baseline, plan)
        write(output / 'selection.json', selected)
        async with RedditClient(config) as reddit:
            auth_error = None
            for index, post in enumerate(selected):
                url = f"https://oauth.reddit.com/r/{post['subreddit']}/comments/{post['post_id']}"
                comment_record = {'status': 'error'}
                try:
                    if not recorder.path(url, plan['comments']).exists():
                        if reddit._access_token is None and auth_error is None:
                            try:
                                await reddit.authenticate()
                                write(output / 'auth.json', {'status': 'ok', 'checked_at': now()})
                            except Exception as e:
                                auth_error = type(e).__name__
                                write(output / 'auth.json', {'status': 'error', 'error_type': auth_error, 'checked_at': now()})
                        if auth_error:
                            raise RequestFailure(f'Reddit authentication failed: {auth_error}')
                    payload = await recorder.get(url, plan['comments'],
                                                 {'Authorization': f'Bearer {reddit._access_token}'})
                    comment_record = parse_comments(payload, post['post_id'])
                except (RequestFailure, ValueError, TypeError, KeyError) as e:
                    comment_record['error_type'] = type(e).__name__
                    comment_record['error'] = str(e)
                image_record = await collect_image(output, post, client)
                live = comment_record.get('live_post', {})
                mismatches = [k for k in ('created_utc', 'subreddit') if live and live.get(k) != post[k]]
                if live and live.get('url') != post['image_url']:
                    mismatches.append('image_url')
                candidates.append({**post, 'source_date': iso(post['created_utc']),
                                   'image': image_record, 'comment_retrieval': comment_record,
                                   'source_mismatches': mismatches})
                write(output / 'candidates.json', candidates)
                if (index + 1) % 10 == 0:
                    print(f"Assets/comments recorded: {index + 1}/{len(selected)}", flush=True)
    report = report_inventory(plan, baseline, discoveries, candidates, output)
    write(output / 'report.json', report)
    write(manifest_path, {'inventory_id': plan['inventory_id'], 'files': {
        str(p.relative_to(output)): file_hash(p) for p in sorted(output.rglob('*'))
        if p.is_file() and p.name not in {'run.lock', 'manifest.json'} and p.suffix != '.tmp'}})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('output', type=Path)
    prep.add_argument('--database', type=Path, default=Path('data/basedbench.db'))
    prep.add_argument('--snapshot', default='basedBench-519-2026-07')
    prep.add_argument('--start', required=True)
    prep.add_argument('--end', required=True, help='Exclusive UTC endpoint')
    prep.add_argument('--ceiling', type=int, default=100)
    prep.add_argument('--max-pages', type=int, default=10)
    execute = commands.add_parser('run')
    execute.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.database, args.output, snapshot=args.snapshot, start=args.start,
                         end=args.end, ceiling=args.ceiling, max_pages=args.max_pages)
        print(json.dumps(result, indent=2))
    else:
        with (args.output / 'run.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = asyncio.run(run(args.output))
        print(json.dumps({k: result[k] for k in ('selected', 'images', 'comments', 'model_cost_usd')}, indent=2))


if __name__ == '__main__':
    main()
