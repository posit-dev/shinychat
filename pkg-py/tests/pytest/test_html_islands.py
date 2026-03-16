from __future__ import annotations

from htmltools import Tag, TagList, div, span
from shinychat._html_islands import split_html_islands


def test_plain_html_wrapped_in_single_island():
    """Non-react content gets a single <shinychat-html> wrapper."""
    tl = TagList(div("hello"), span("world"))
    result = split_html_islands(tl)
    rendered = TagList(result).render()["html"]
    assert "<shinychat-html>" in rendered
    assert "<div>hello</div>" in rendered
    assert "<span>world</span>" in rendered
    assert rendered.count("<shinychat-html>") == 1


def test_react_element_emitted_bare():
    """A single react element is emitted without any wrapper."""
    tl = TagList(Tag("shiny-tool-result", data_shinychat_react=True, request_id="abc"))
    result = split_html_islands(tl)
    rendered = TagList(result).render()["html"]
    assert "<shinychat-html>" not in rendered
    assert "shiny-tool-result" in rendered
    assert 'data-shinychat-react' in rendered


def test_mixed_content_splits_around_react():
    """React elements split surrounding HTML into separate islands."""
    tl = TagList(
        div("before"),
        Tag("shiny-tool-result", data_shinychat_react=True, request_id="abc"),
        div("after"),
    )
    result = split_html_islands(tl)
    rendered = TagList(result).render()["html"]
    assert rendered.count("<shinychat-html>") == 2
    assert "shiny-tool-result" in rendered
    lines = rendered.split("\n")
    for line in lines:
        if "shiny-tool-result" in line:
            assert "shinychat-html" not in line


def test_adjacent_react_elements_no_empty_islands():
    """Two consecutive react elements produce no empty islands between them."""
    tl = TagList(
        Tag("shiny-tool-request", data_shinychat_react=True),
        Tag("shiny-tool-result", data_shinychat_react=True),
    )
    result = split_html_islands(tl)
    rendered = TagList(result).render()["html"]
    assert "<shinychat-html>" not in rendered
    assert "shiny-tool-request" in rendered
    assert "shiny-tool-result" in rendered


def test_single_tag_with_react_attr():
    """A single tag (not TagList) with react attr is emitted bare."""
    tag = Tag("shiny-tool-request", data_shinychat_react=True)
    result = split_html_islands(tag)
    rendered = TagList(result).render()["html"]
    assert "<shinychat-html>" not in rendered


def test_single_tag_without_react_attr():
    """A single tag without react attr gets wrapped."""
    tag = div("hello")
    result = split_html_islands(tag)
    rendered = TagList(result).render()["html"]
    assert "<shinychat-html>" in rendered


def test_string_content_in_taglist_wrapped():
    """Raw string content inside a TagList gets wrapped in an island."""
    tl = TagList("hello world")
    result = split_html_islands(tl)
    rendered = TagList(result).render()["html"]
    assert "<shinychat-html>" in rendered
    assert "hello world" in rendered


def test_bare_string_content_wrapped():
    """A bare string passed directly is wrapped in an island."""
    result = split_html_islands("hello world")
    rendered = TagList(result).render()["html"]
    assert "<shinychat-html>" in rendered
    assert "hello world" in rendered
