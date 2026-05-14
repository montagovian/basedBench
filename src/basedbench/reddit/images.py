"""Image downloader — fetches Reddit images, validates with Pillow, stores on disk."""

from __future__ import annotations

import io
import logging
from pathlib import Path

import httpx
from PIL import Image, UnidentifiedImageError
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from basedbench.errors import ImageDownloadError, ImageValidationError, is_retryable

log = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 20 * 1024 * 1024
KNOWN_EXTENSIONS = ("jpg", "jpeg", "png", "gif", "webp")
HTTP_TIMEOUT = 30.0


def _extension_from_url(url: str) -> str:
    path = url.split("?", 1)[0].lower()
    if path.endswith(".png"):
        return "png"
    if path.endswith(".gif"):
        return "gif"
    if path.endswith(".webp"):
        return "webp"
    if path.endswith(".jpeg"):
        return "jpeg"
    return "jpg"


def find_local_image(images_dir: Path, post_id: str) -> Path | None:
    """Return the on-disk path of an already-downloaded image, or None."""
    for ext in KNOWN_EXTENSIONS:
        candidate = images_dir / f"{post_id}.{ext}"
        if candidate.exists():
            return candidate
    return None


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError)):
        return True
    if isinstance(exc, Exception) and is_retryable(exc):
        return True
    return False


class ImageDownloader:
    """Downloads, validates, and stores meme images locally."""

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._http = httpx.AsyncClient(timeout=HTTP_TIMEOUT)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> ImageDownloader:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def download(self, url: str, post_id: str) -> str:
        """Download an image. Returns a `data/images/<post_id>.<ext>` relative path."""
        existing = find_local_image(self._output_dir, post_id)
        if existing is not None:
            return f"data/images/{existing.name}"

        bytes_payload: bytes | None = None
        async for attempt in AsyncRetrying(
            retry=retry_if_exception(_retryable),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=60),
            reraise=True,
        ):
            with attempt:
                resp = await self._http.get(url)
                if resp.status_code >= 400:
                    raise ImageDownloadError(url, f"HTTP {resp.status_code}")
                bytes_payload = resp.content

        assert bytes_payload is not None

        if len(bytes_payload) > MAX_IMAGE_BYTES:
            raise ImageDownloadError(url, "image exceeds 20MB limit")

        try:
            Image.open(io.BytesIO(bytes_payload)).verify()
        except (UnidentifiedImageError, OSError) as e:
            raise ImageValidationError(url, str(e)) from e

        ext = _extension_from_url(url)
        filename = f"{post_id}.{ext}"
        (self._output_dir / filename).write_bytes(bytes_payload)
        return f"data/images/{filename}"
