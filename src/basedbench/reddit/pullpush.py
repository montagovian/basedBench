"""Pullpush.io client — Pushshift mirror for arbitrary date-range Reddit queries.

Reddit's native /top listings only support a fixed set of time windows (hour/day/
week/month/year/all). Pullpush.io serves a Pushshift-compatible archive that
supports arbitrary `after`/`before` Unix timestamp filters — making it the only
practical way to fetch posts from a specific historical window.

This client only lists post metadata. Comments are fetched separately via the
authenticated RedditClient because pullpush's comments index is less reliable.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from basedbench.errors import is_retryable

log = logging.getLogger(__name__)

PULLPUSH_BASE = "https://api.pullpush.io/reddit/search/submission/"
HTTP_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
MAX_RESULTS_PER_REQUEST = 100  # pullpush caps here; can't be overridden
INTER_REQUEST_DELAY = 1.0  # polite gap to avoid hitting pullpush rate limits
MAX_PAGES_DEFAULT = 100  # safety cap: 100 × 100 = 10k raw posts inspected per sub


@dataclass
class PullpushPost:
    """A post discovered via pullpush, before comments are fetched.

    Mirrors the subset of fields we need to construct a RawPost later, plus
    `created_utc` for pagination and `over_18` for the existing safety filter.
    """

    post_id: str
    subreddit: str
    title: str
    image_url: str | None  # None if is_self or non-image link
    permalink: str
    score: int
    num_comments: int
    created_utc: float
    over_18: bool


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError)):
        return True
    if isinstance(exc, Exception) and is_retryable(exc):
        return True
    return False


def _retry() -> AsyncRetrying:
    return AsyncRetrying(
        retry=retry_if_exception(_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        reraise=True,
    )


class PullpushClient:
    """Hits api.pullpush.io for date-range post discovery."""

    def __init__(self, user_agent: str = "basedbench/5.0.0") -> None:
        self._http = httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": user_agent},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "PullpushClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def list_posts(
        self,
        subreddit: str,
        after_unix: int,
        before_unix: int,
        limit: int,
        min_score: int = 10,
        min_comments: int = 3,
        require_image: bool = True,
        max_pages: int = MAX_PAGES_DEFAULT,
    ) -> list[PullpushPost]:
        """List up to `limit` *qualifying* posts in [after_unix, before_unix).

        Paginates via `created_utc` walk-back (sort=desc by date) since pullpush
        caps at 100 results per request and doesn't expose a stable cursor.
        Applies the quality filter inline so `limit=N` returns N usable posts
        (where "usable" means: has an image URL if require_image, score >=
        min_score, num_comments >= min_comments).

        Stops when we hit `limit`, walk past `after_unix`, encounter an empty
        page, or exhaust `max_pages` (safety cap to prevent infinite loops in
        sparse date ranges).
        """
        if after_unix >= before_unix:
            raise ValueError(
                f"after_unix ({after_unix}) must be < before_unix ({before_unix})"
            )

        posts: list[PullpushPost] = []
        current_before = before_unix
        pages_fetched = 0
        raw_inspected = 0

        while len(posts) < limit and pages_fetched < max_pages:
            page = await self._fetch_page(
                subreddit=subreddit,
                after=after_unix,
                before=current_before,
            )
            pages_fetched += 1
            if not page:
                break

            raw_inspected += len(page)
            for raw in page:
                pp = _to_pullpush_post(raw)
                if pp is None:
                    continue
                if require_image and pp.image_url is None:
                    continue
                if pp.score < min_score:
                    continue
                if pp.num_comments < min_comments:
                    continue
                posts.append(pp)
                if len(posts) >= limit:
                    break

            oldest = min(raw.get("created_utc", before_unix) for raw in page)
            new_before = int(oldest) - 1
            if new_before <= after_unix or new_before >= current_before:
                break
            current_before = new_before

            await asyncio.sleep(INTER_REQUEST_DELAY)

        log.info(
            "pullpush list_posts r/%s: %d qualifying / %d inspected over %d page(s)",
            subreddit, len(posts), raw_inspected, pages_fetched,
        )
        return posts

    async def _fetch_page(
        self,
        subreddit: str,
        after: int,
        before: int,
    ) -> list[dict]:
        params = {
            "subreddit": subreddit,
            "after": after,
            "before": before,
            "size": MAX_RESULTS_PER_REQUEST,
            "sort": "desc",
            "sort_type": "created_utc",
        }

        async for attempt in _retry():
            with attempt:
                resp = await self._http.get(PULLPUSH_BASE, params=params)
                if resp.status_code >= 500:
                    raise httpx.ReadError(f"pullpush {resp.status_code}")
                if resp.status_code >= 400:
                    log.warning(
                        "Pullpush %d for r/%s: %s",
                        resp.status_code, subreddit, resp.text[:200],
                    )
                    return []
                payload = resp.json()

        return payload.get("data", []) or []


def _to_pullpush_post(raw: dict) -> PullpushPost | None:
    """Convert one pullpush API response row into a PullpushPost.

    Returns None when the row doesn't represent something we'd want to ingest
    (missing fields, self-post with no image, etc.). Callers further filter
    by score and num_comments after collection.
    """
    post_id = raw.get("id") or ""
    if not post_id:
        return None

    is_self = bool(raw.get("is_self"))
    url = raw.get("url") or ""
    image_url = url if (url and not is_self and _is_image_link(url)) else None

    try:
        created_utc = float(raw.get("created_utc") or 0)
    except (TypeError, ValueError):
        return None
    if created_utc <= 0:
        return None

    return PullpushPost(
        post_id=post_id,
        subreddit=raw.get("subreddit") or "",
        title=raw.get("title") or "",
        image_url=image_url,
        permalink=raw.get("permalink") or "",
        score=int(raw.get("score") or 0),
        num_comments=int(raw.get("num_comments") or 0),
        created_utc=created_utc,
        over_18=bool(raw.get("over_18")),
    )


def _is_image_link(url: str) -> bool:
    """Mirror of reddit.client._is_image_url, kept local to avoid circular imports."""
    lower = url.lower()
    path = lower.split("?", 1)[0]
    if path.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
        return True
    return "i.redd.it" in lower or "i.imgur.com" in lower
