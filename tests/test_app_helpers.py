"""Unit tests for app.py pure helpers (no Gradio runtime required)."""

from __future__ import annotations

from basedbench.app import _inline_image_urls


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
