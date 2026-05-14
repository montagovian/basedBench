"""Reddit OAuth2 client — fetches top posts and their comments from a subreddit."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from basedbench.config import Config
from basedbench.errors import (
    RedditApiError,
    RedditAuthError,
    RedditRateLimitError,
    is_retryable,
)
from basedbench.schemas import RawPost, RedditComment

log = logging.getLogger(__name__)

MIN_POST_SCORE = 10
MIN_POST_COMMENTS = 3
INTER_REQUEST_DELAY = 0.1
HTTP_TIMEOUT = 30.0


def _is_image_url(url: str) -> bool:
    """v4 parity: extension match OR known image host."""
    lower = url.lower()
    path = lower.split("?", 1)[0]
    if path.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
        return True
    return "i.redd.it" in lower or "i.imgur.com" in lower


def _ts_to_iso(ts: float | int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()


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


class RedditClient:
    """Authenticates with Reddit OAuth2 and fetches posts + comments."""

    def __init__(self, config: Config) -> None:
        self._client_id = config.reddit_client_id
        self._client_secret = config.reddit_client_secret
        self._user_agent = config.reddit_user_agent
        self._http = httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": self._user_agent},
        )
        self._access_token: str | None = None

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> RedditClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def authenticate(self) -> None:
        async for attempt in _retry():
            with attempt:
                resp = await self._http.post(
                    "https://www.reddit.com/api/v1/access_token",
                    auth=(self._client_id, self._client_secret),
                    data={"grant_type": "client_credentials"},
                )
                if resp.status_code != 200:
                    raise RedditAuthError(
                        f"HTTP {resp.status_code}: {resp.text}"
                    )
                data = resp.json()

        token = data.get("access_token")
        if not isinstance(token, str):
            raise RedditAuthError("missing access_token in response")
        self._access_token = token

    async def fetch_posts(self, subreddit: str, limit: int) -> list[RawPost]:
        if self._access_token is None:
            raise RedditAuthError("not authenticated")

        posts: list[RawPost] = []
        after: str | None = None
        batch = min(100, limit)

        while len(posts) < limit:
            remaining = limit - len(posts)
            count = min(batch, remaining)
            url = f"https://oauth.reddit.com/r/{subreddit}/top?t=week&limit={count}"
            if after:
                url += f"&after={after}"

            data = await self._get_json(url)

            children = data.get("data", {}).get("children", [])
            if not children:
                break
            after = data.get("data", {}).get("after")

            for child in children:
                cdata = child.get("data", {})
                post_id_raw = cdata.get("name", "")
                post_id = post_id_raw.removeprefix("t3_") if post_id_raw else ""
                url_str = cdata.get("url", "") or ""
                score = int(cdata.get("score", 0) or 0)
                num_comments = int(cdata.get("num_comments", 0) or 0)

                if not _is_image_url(url_str):
                    continue
                if score < MIN_POST_SCORE or num_comments < MIN_POST_COMMENTS:
                    continue

                await asyncio.sleep(INTER_REQUEST_DELAY)
                comments = await self._fetch_comments(subreddit, post_id)

                posts.append(
                    RawPost(
                        post_id=post_id,
                        subreddit=subreddit,
                        title=cdata.get("title", "") or "",
                        image_url=url_str,
                        permalink=cdata.get("permalink", "") or "",
                        score=score,
                        created_utc=_ts_to_iso(cdata.get("created_utc")),
                        retrieved_at=datetime.now(timezone.utc).isoformat(),
                        comments=comments,
                    )
                )
                if len(posts) >= limit:
                    break

            if not after:
                break
            await asyncio.sleep(INTER_REQUEST_DELAY)

        return posts

    async def _fetch_comments(self, subreddit: str, post_id: str) -> list[RedditComment]:
        url = (
            f"https://oauth.reddit.com/r/{subreddit}/comments/{post_id}"
            f"?limit=100&depth=1"
        )
        data = await self._get_json(url)

        listing: list[Any] = []
        if isinstance(data, list) and len(data) >= 2:
            listing = data[1].get("data", {}).get("children", []) or []

        comments: list[RedditComment] = []
        for child in listing:
            if child.get("kind") != "t1":
                continue
            cdata = child.get("data", {})
            author = (cdata.get("author") or "").strip()
            body = cdata.get("body", "") or ""
            distinguished = cdata.get("distinguished", "") or ""

            if author == "AutoModerator" or author.lower().startswith("bot"):
                continue
            if body in ("[deleted]", "[removed]"):
                continue
            if distinguished == "moderator":
                continue

            comment_id_raw = cdata.get("name", "") or ""
            comment_id = comment_id_raw.removeprefix("t1_")
            comments.append(
                RedditComment(
                    comment_id=comment_id,
                    author=author,
                    body=body,
                    score=int(cdata.get("score", 0) or 0),
                    is_moderator=False,
                    created_utc=_ts_to_iso(cdata.get("created_utc")),
                )
            )

        comments.sort(key=lambda c: c.score, reverse=True)
        return comments

    async def _get_json(self, url: str) -> Any:
        """GET with bearer auth and tenacity retry on transient errors."""
        if self._access_token is None:
            raise RedditAuthError("not authenticated")
        token = self._access_token

        async for attempt in _retry():
            with attempt:
                resp = await self._http.get(
                    url, headers={"Authorization": f"Bearer {token}"}
                )
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", "60") or "60")
                    raise RedditRateLimitError(retry_after)
                if resp.status_code >= 400:
                    raise RedditApiError(resp.status_code, resp.text)
                payload = resp.json()
        return payload
