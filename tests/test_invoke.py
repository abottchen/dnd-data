"""Tests for build.invoke._parse_frontmatter — exercises only the pure
parsing logic, no subprocess. The CLI invocation path (call_transformer)
needs an integration harness and is not covered here."""
import pytest

from build.invoke import FrontmatterError, _parse_frontmatter


def test_standard_frontmatter_with_model_opus():
    fm, body = _parse_frontmatter("---\nmodel: opus\n---\nbody text\n")
    assert fm == {"model": "opus"}
    assert body == "body text\n"


def test_standard_frontmatter_with_model_sonnet():
    fm, body = _parse_frontmatter("---\nmodel: sonnet\n---\nyou are a function\n")
    assert fm == {"model": "sonnet"}
    assert body.startswith("you are a function")


def test_no_frontmatter_returns_text_unchanged():
    text = "just a body, no frontmatter\nsecond line\n"
    fm, body = _parse_frontmatter(text)
    assert fm == {}
    assert body == text


def test_blank_lines_and_comments_inside_frontmatter_are_skipped():
    text = "---\n# a comment\n\nmodel: opus\n# trailing comment\n---\nbody"
    fm, body = _parse_frontmatter(text)
    assert fm == {"model": "opus"}
    assert body == "body"


def test_crlf_line_endings_are_tolerated():
    text = "---\r\nmodel: opus\r\n---\r\nbody line one\r\nbody line two\r\n"
    fm, body = _parse_frontmatter(text)
    assert fm == {"model": "opus"}
    # CRLF is normalized inside the body too — that's the simplest behavior
    # and the body is then handed to claude -p as a UTF-8 file, so LF is fine.
    assert "body line one" in body
    assert "body line two" in body


def test_multiple_frontmatter_keys():
    text = "---\nmodel: opus\nfoo: bar\n---\nbody"
    fm, _ = _parse_frontmatter(text)
    assert fm == {"model": "opus", "foo": "bar"}


def test_empty_frontmatter_block_yields_empty_dict():
    text = "---\n---\nbody"
    fm, body = _parse_frontmatter(text)
    assert fm == {}
    assert body == "body"


def test_unclosed_frontmatter_raises():
    text = "---\nmodel: opus\nbody without close\n"
    with pytest.raises(FrontmatterError, match="no closing"):
        _parse_frontmatter(text)


def test_malformed_line_without_colon_raises():
    text = "---\nmodel opus\n---\nbody"
    with pytest.raises(FrontmatterError, match="no ':'"):
        _parse_frontmatter(text)


def test_value_with_internal_colons_keeps_remainder():
    text = "---\nnote: a: b: c\n---\nbody"
    fm, _ = _parse_frontmatter(text)
    assert fm == {"note": "a: b: c"}


def test_missing_dash_prefix_is_not_an_error():
    """A file with no leading '---' is not malformed — it's just a
    frontmatterless prompt. Returning ({}, text) is the contract."""
    text = "model: opus\n---\nbody\n"
    fm, body = _parse_frontmatter(text)
    assert fm == {}
    assert body == text
