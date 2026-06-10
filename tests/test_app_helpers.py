"""Unit tests for app.py pure helpers (no Gradio runtime required)."""

from __future__ import annotations

from pathlib import Path

import basedbench.app as app_mod
import basedbench.cli as cli_mod
from basedbench.app import (
    _classify_state,
    _comment_md,
    _eval_expected_label,
    _eval_where,
    _inline_image_urls,
    _inspect_where,
    _position_text,
    _resolve_image,
    set_db_path,
)


def _row(**kw):
    """Minimal stand-in for an sqlite3.Row (supports __getitem__ by name)."""
    base = {
        "review_status": None,
        "review_reason": None,
        "explanation": None,
        "consensus_ran": 0,
    }
    base.update(kw)
    return base


def test_classify_state_validated():
    assert _classify_state(_row(review_status="validated")) == "validated"


def test_classify_state_gate_exclusions_by_reason_prefix():
    assert _classify_state(
        _row(review_status="excluded", review_reason="safety: slur")
    ) == "safety_excluded"
    assert _classify_state(
        _row(review_status="excluded", review_reason="auto: no clear joke")
    ) == "quality_excluded"
    assert _classify_state(
        _row(review_status="excluded", review_reason="image_missing")
    ) == "image_missing"
    assert _classify_state(
        _row(review_status="excluded", review_reason="bad image")
    ) == "human_excluded"


def test_classify_state_unreviewed_vs_no_consensus_vs_pending():
    # Has a ground-truth explanation, no review -> in the queue
    assert _classify_state(_row(explanation="it's about cats")) == "unreviewed"
    # No GT but consensus ran -> genuine no-consensus
    assert _classify_state(_row(consensus_ran=1)) == "no_consensus"
    # No GT, consensus never ran -> not yet processed
    assert _classify_state(_row()) == "pending"


def test_inspect_where_all_has_no_state_condition():
    where, params = _inspect_where("all", "all", "")
    assert where == "1=1"
    assert params == []


def test_inspect_where_quality_excluded_uses_auto_prefix():
    where, params = _inspect_where("quality_excluded", "all", "")
    assert "r.reason LIKE 'auto:%'" in where
    assert params == []


def test_inspect_where_combines_status_subreddit_search():
    where, params = _inspect_where("validated", "memes", "cat")
    assert "r.status = 'validated'" in where
    assert "m.subreddit = ?" in where
    assert "m.title LIKE ?" in where
    assert params == ["memes", "%cat%"]


def test_inspect_where_human_excluded_excludes_gate_reasons():
    where, _ = _inspect_where("human_excluded", "all", "")
    assert "NOT LIKE 'safety:%'" in where
    assert "NOT LIKE 'auto:%'" in where
    assert "image_missing" in where


def test_position_text():
    assert _position_text(0, [], 0) == "0 / 0"
    assert _position_text(0, ["a", "b", "c"], 3) == "1 / 3"
    assert _position_text(2, ["a", "b", "c"], 3) == "3 / 3"
    # capped result notes the true total
    assert _position_text(0, ["a"], 50) == "1 / 1 (capped from 50)"


def test_eval_expected_label():
    assert _eval_expected_label(1) == "consensus"
    assert _eval_expected_label(True) == "consensus"
    assert _eval_expected_label(0) == "no_consensus"
    assert _eval_expected_label(False) == "no_consensus"


def test_eval_where_filters_category_and_search():
    where, params = _eval_where("true_no_consensus", "cat")
    assert "cei.active = 1" in where
    assert "cei.category = ?" in where
    assert "m.title LIKE ?" in where
    assert "m.post_id LIKE ?" in where
    assert params == ["true_no_consensus", "%cat%", "%cat%"]


def test_eval_where_all_category_only_filters_active():
    where, params = _eval_where("all", "")
    assert where == "cei.active = 1"
    assert params == []


def test_preview_redd_it_url_becomes_clickable_image():
    body = "https://preview.redd.it/wvbeqskxuq0g1.jpeg?width=427&format=pjpg"
    out = _inline_image_urls(body)
    assert out.startswith("[![](")
    assert out.endswith(")")
    assert body in out  # url is preserved as both link target and image source


def test_i_redd_it_url_transformed():
    body = "lol https://i.redd.it/abc123.jpg"
    out = _inline_image_urls(body)
    assert "[![](https://i.redd.it/abc123.jpg)](https://i.redd.it/abc123.jpg)" in out
    assert out.startswith("lol ")


def test_imgur_url_transformed():
    body = "https://i.imgur.com/xyz.png"
    out = _inline_image_urls(body)
    assert "[![(" not in out  # sanity: not nested
    assert "[![](https://i.imgur.com/xyz.png)](https://i.imgur.com/xyz.png)" == out


def test_generic_image_url_with_extension_transformed():
    body = "see https://example.com/cat.gif here"
    out = _inline_image_urls(body)
    assert "![](https://example.com/cat.gif)" in out
    assert "see " in out
    assert " here" in out


def test_non_image_url_unchanged():
    body = "go to https://en.wikipedia.org/wiki/Meme for context"
    assert _inline_image_urls(body) == body


def test_plain_text_unchanged():
    assert _inline_image_urls("just a normal comment") == "just a normal comment"
    assert _inline_image_urls("") == ""


def test_multiple_image_urls_all_transformed():
    body = (
        "first https://i.redd.it/a.jpg "
        "second https://preview.redd.it/b.png?width=100"
    )
    out = _inline_image_urls(body)
    assert out.count("[![](") == 2


def test_webp_extension_matched():
    body = "https://example.com/img.webp"
    out = _inline_image_urls(body)
    assert "![](https://example.com/img.webp)" in out


def test_jpeg_extension_matched():
    body = "https://example.com/photo.jpeg"
    out = _inline_image_urls(body)
    assert "![](https://example.com/photo.jpeg)" in out


def test_url_inside_parens_doesnt_swallow_paren():
    """Trailing ) shouldn't be consumed by the URL match — would break markdown."""
    body = "(see https://i.redd.it/x.jpg)"
    out = _inline_image_urls(body)
    # The trailing ) should remain outside the URL/markdown
    assert out.endswith(")")
    assert "https://i.redd.it/x.jpg)](" in out  # url is the link target


def test_comment_markdown_escapes_html_and_links():
    row = {
        "author": "<script>alert(1)</script>",
        "score": 1,
        "body": "<b>x</b> [click](javascript:alert(1))",
    }

    out = _comment_md(row)

    assert "<script>" not in out
    assert "<b>" not in out
    assert "[click](javascript:alert(1))" not in out
    assert "\\[click\\]" in out
    assert "javascript:alert" in out


def test_resolve_image_rejects_path_traversal(tmp_path: Path):
    old_db = app_mod._DB_PATH
    try:
        db_path = tmp_path / "data" / "basedbench.db"
        image_path = tmp_path / "data" / "images" / "meme.jpg"
        image_path.parent.mkdir(parents=True)
        image_path.write_bytes(b"fake")
        (tmp_path / ".env").write_text("SECRET=1")
        set_db_path(db_path)

        assert _resolve_image("data/images/meme.jpg") == str(image_path.resolve())
        assert _resolve_image("../../.env") is None
        assert _resolve_image(str((tmp_path / ".env").resolve())) is None
    finally:
        set_db_path(old_db)


def test_view_launches_gradio_read_only(monkeypatch):
    class DummyDb:
        def close(self) -> None:
            pass

    calls = []
    monkeypatch.setattr(cli_mod, "_load", lambda: (DummyDb(), object()))
    monkeypatch.setattr(app_mod, "launch", lambda **kw: calls.append(kw))

    cli_mod.view()

    assert calls == [{"read_only": True}]
