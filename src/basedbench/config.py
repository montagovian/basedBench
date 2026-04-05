"""Configuration via Pydantic Settings (.env + environment variables)."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_project_root() -> Path:
    """Walk up from CWD to find .env or pyproject.toml."""
    d = Path.cwd()
    while True:
        if (d / ".env").exists() or (d / "pyproject.toml").exists():
            return d
        parent = d.parent
        if parent == d:
            return Path.cwd()
        d = parent


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Reddit
    reddit_client_id: str
    reddit_client_secret: str
    reddit_user_agent: str = "basedbench/5.0.0"

    # LLM
    openai_api_key: str
    anthropic_api_key: str | None = None

    # Model selection
    consensus_model: str = "gpt-4o-mini"
    judge_model: str = "gpt-4o-mini"

    # Quality thresholds (same defaults as v4)
    min_agreeing_comments: int = 3
    min_avg_comment_score: float = 10.0
    min_comment_score: int = 5
    max_comments_for_consensus: int = 10

    # HuggingFace
    hf_token: str | None = None
    hf_dataset_repo: str = ""  # Must be set explicitly before push

    @property
    def project_root(self) -> Path:
        # On HF Space, use /data for persistent storage
        if os.environ.get("SPACE_ID"):
            return Path("/data")
        return _find_project_root()

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "basedbench.db"

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "images"

    def ensure_dirs(self) -> None:
        """Create data directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
