"""Shared fixtures for basedBench tests."""

import pytest

from basedbench.db import Database
from basedbench.schemas import RawPost, RedditComment


@pytest.fixture
def db() -> Database:
    """In-memory database with migrations applied."""
    return Database.open_in_memory()


def sample_post(post_id: str = "post1") -> RawPost:
    """Create a sample RawPost for testing."""
    return RawPost(
        post_id=post_id,
        subreddit="memes",
        title="Test meme",
        image_url="https://i.redd.it/test.jpg",
        permalink=f"/r/memes/comments/{post_id}/test",
        score=100,
        created_utc="2025-01-01T00:00:00Z",
        retrieved_at="2025-01-02T00:00:00Z",
        comments=[
            RedditComment(
                comment_id=f"{post_id}_c1",
                author="user1",
                body="This is about X",
                score=50,
                is_moderator=False,
            ),
            RedditComment(
                comment_id=f"{post_id}_c2",
                author="user2",
                body="Yeah it's X",
                score=30,
                is_moderator=False,
            ),
        ],
    )
