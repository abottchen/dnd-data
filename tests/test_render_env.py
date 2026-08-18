"""Regression guard: render_page must build its Jinja env with autoescape on.

With autoescape off, every `| safe` filter in the templates is a no-op and any
authored/third-party field containing `<`, `&`, or `"` corrupts markup (or, in a
data attribute, breaks out of the attribute). This test fails if someone flips
autoescape back off.
"""
from build import render


def test_render_env_autoescapes(tmp_path):
    tdir = tmp_path / "t"
    tdir.mkdir()
    (tdir / "base.html").write_text('<p data-x="{{ v }}">{{ v }}</p>')
    out = tmp_path / "out.html"
    render.render_page({"v": '<img onerror=x>"'}, tdir, out)
    html = out.read_text()
    assert "<img onerror" not in html
    assert "&lt;img" in html


def test_paragraphs_filter_splits_on_blank_lines(tmp_path):
    """Authored prose uses a blank line as its only paragraph signal."""
    tdir = tmp_path / "t"
    tdir.mkdir()
    (tdir / "base.html").write_text("<div>{{ v | paragraphs }}</div>")
    out = tmp_path / "out.html"
    render.render_page({"v": "First para.\n\nSecond para."}, tdir, out)
    assert out.read_text() == "<div><p>First para.</p><p>Second para.</p></div>"


def test_paragraphs_filter_escapes_and_handles_single_block(tmp_path):
    """The filter replaces `| safe` on prose, so it must escape its input."""
    tdir = tmp_path / "t"
    tdir.mkdir()
    (tdir / "base.html").write_text("<div>{{ v | paragraphs }}</div>")
    out = tmp_path / "out.html"
    render.render_page({"v": "Only one <img onerror=x> block."}, tdir, out)
    html = out.read_text()
    assert html.count("<p>") == 1
    assert "<img onerror" not in html
    assert "&lt;img" in html
