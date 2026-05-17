"""Tests for build/prepare.py — slice gathering and run-dir population."""
import json
from pathlib import Path

import pytest

from build import prepare


# -- Frontmatter parser (moved from build/invoke.py) ------------------------

def test_parse_frontmatter_no_marker_returns_text_unchanged():
    fm, body = prepare.parse_frontmatter("no marker here\nbody body")
    assert fm == {}
    assert body == "no marker here\nbody body"


def test_parse_frontmatter_key_value_pairs():
    fm, body = prepare.parse_frontmatter("---\nmodel: opus\n---\nbody\n")
    assert fm == {"model": "opus"}
    assert body == "body\n"


def test_parse_frontmatter_empty_block():
    fm, body = prepare.parse_frontmatter("---\n---\nbody\n")
    assert fm == {}
    assert body == "body\n"


def test_parse_frontmatter_crlf_tolerated():
    fm, body = prepare.parse_frontmatter("---\r\nmodel: sonnet\r\n---\r\nbody\r\n")
    assert fm == {"model": "sonnet"}


def test_parse_frontmatter_unclosed_raises():
    with pytest.raises(prepare.FrontmatterError):
        prepare.parse_frontmatter("---\nmodel: opus\nbody but no close")


def test_parse_frontmatter_malformed_line_raises():
    with pytest.raises(prepare.FrontmatterError):
        prepare.parse_frontmatter("---\nthis has no colon\n---\nbody")
