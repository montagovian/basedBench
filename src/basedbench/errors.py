"""Exception hierarchy for basedBench."""


class BasedBenchError(Exception):
    """Base exception for all basedBench errors."""


# --- Configuration ---


class MissingEnvVarError(BasedBenchError):
    """A required environment variable is not set."""

    def __init__(self, var: str) -> None:
        self.var = var
        super().__init__(f"missing environment variable: {var}")


class ConfigError(BasedBenchError):
    """General configuration error."""


# --- Reddit ---


class RedditAuthError(BasedBenchError):
    """Reddit authentication failed."""


class RedditApiError(BasedBenchError):
    """Reddit API returned an error."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"Reddit API error: {status} - {body}")


class RedditRateLimitError(BasedBenchError):
    """Reddit rate limited us."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"Reddit rate limited, retry after {retry_after}s")


# --- LLM ---


class OpenAIError(BasedBenchError):
    """OpenAI API error."""

    def __init__(self, msg: str, *, fatal: bool = False, code: str | None = None) -> None:
        super().__init__(msg)
        self.fatal = fatal
        self.code = code


class AnthropicError(BasedBenchError):
    """Anthropic API error."""

    def __init__(self, msg: str, *, fatal: bool = False, code: str | None = None) -> None:
        super().__init__(msg)
        self.fatal = fatal
        self.code = code


class LlmJsonParseError(BasedBenchError):
    """Failed to parse LLM JSON response."""


# --- Images ---


class ImageDownloadError(BasedBenchError):
    """Failed to download an image."""

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"image download failed for {url}: {reason}")


class ImageValidationError(BasedBenchError):
    """Image failed validation."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"image validation failed for {path}: {reason}")


class ImageNotFoundError(BasedBenchError):
    """No image found for a post."""

    def __init__(self, post_id: str) -> None:
        self.post_id = post_id
        super().__init__(f"image not found for post {post_id}")


# --- Data ---


class NoConsensusError(BasedBenchError):
    """No consensus found for a post."""

    def __init__(self, post_id: str) -> None:
        self.post_id = post_id
        super().__init__(f"no consensus found for post {post_id}")


class QualityThresholdError(BasedBenchError):
    """Quality threshold not met."""


class MemeNotFoundError(BasedBenchError):
    """Meme not found in database."""

    def __init__(self, post_id: str) -> None:
        self.post_id = post_id
        super().__init__(f"meme not found: {post_id}")


class PredictionNotFoundError(BasedBenchError):
    """Prediction not found in database."""


class SnapshotNotFoundError(BasedBenchError):
    """Snapshot not found in database."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"snapshot not found: {name}")


# --- Database ---


class DatabaseError(BasedBenchError):
    """Database operation failed."""


class MigrationError(BasedBenchError):
    """Database migration failed."""


# --- Retryability ---

RETRYABLE_TYPES = (
    OpenAIError,
    AnthropicError,
    RedditRateLimitError,
)

RETRYABLE_REDDIT_STATUSES = {429, 500, 502, 503}


def is_retryable(error: Exception) -> bool:
    """Return True if the error is transient and the operation should be retried."""
    if isinstance(error, RETRYABLE_TYPES):
        return True
    if isinstance(error, RedditApiError) and error.status in RETRYABLE_REDDIT_STATUSES:
        return True
    return False


# --- LLM provider fatal errors (auth, quota, billing) ---

# Codes seen in the wild from OpenAI & Anthropic SDK exceptions
# (these never resolve on retry — the caller needs to fix billing/keys).
FATAL_LLM_ERROR_CODES = frozenset(
    {
        "insufficient_quota",
        "invalid_api_key",
        "account_deactivated",
        "invalid_organization",
        "billing_not_active",
    }
)

# HTTP statuses that signal auth/billing failure regardless of code field.
FATAL_LLM_STATUS_CODES = frozenset({401, 402, 403})


def is_fatal_llm_error(error: BaseException) -> bool:
    """Return True if this LLM provider error will not resolve on retry.

    Recognises:
    - ``fatal=True`` on our own wrapper exceptions
    - the ``code`` field exposed by openai/anthropic SDK exceptions
    - HTTP-level auth/payment statuses (401, 402, 403)
    """
    if getattr(error, "fatal", False):
        return True
    status = getattr(error, "status_code", None)
    if isinstance(status, int) and status in FATAL_LLM_STATUS_CODES:
        return True
    code = getattr(error, "code", None)
    if isinstance(code, str) and code in FATAL_LLM_ERROR_CODES:
        return True
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        inner = body.get("error")
        if isinstance(inner, dict) and inner.get("code") in FATAL_LLM_ERROR_CODES:
            return True
    return False
