from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from htmltools import HTML, Tag, TagList, div, span
from shinychat import output_markdown_stream
from shinychat._html_islands import (
    split_content_by_trust,
    split_html_islands,
)


def test_plain_html_wrapped_in_single_island():
    """Non-react content gets a single <shiny-chat-raw-html> wrapper."""
    tl = TagList(div("hello"), span("world"))
    result = split_html_islands(tl)
    rendered = TagList(result).render()["html"]
    assert "<shiny-chat-raw-html>" in rendered
    assert "<div>hello</div>" in rendered
    assert "<span>world</span>" in rendered
    assert rendered.count("<shiny-chat-raw-html>") == 1


def test_react_element_emitted_bare():
    """A single react element is emitted without any wrapper."""
    tl = TagList(
        Tag("shiny-tool-result", data_shinychat_react=True, request_id="abc")
    )
    result = split_html_islands(tl)
    rendered = TagList(result).render()["html"]
    assert "<shiny-chat-raw-html>" not in rendered
    assert "shiny-tool-result" in rendered
    assert "data-shinychat-react" in rendered


def test_mixed_content_splits_around_react():
    """React elements split surrounding HTML into separate islands."""
    tl = TagList(
        div("before"),
        Tag("shiny-tool-result", data_shinychat_react=True, request_id="abc"),
        div("after"),
    )
    result = split_html_islands(tl)
    rendered = TagList(result).render()["html"]
    assert rendered.count("<shiny-chat-raw-html>") == 2
    assert "shiny-tool-result" in rendered
    lines = rendered.split("\n")
    for line in lines:
        if "shiny-tool-result" in line:
            assert "shiny-chat-raw-html" not in line


def test_adjacent_react_elements_no_empty_islands():
    """Two consecutive react elements produce no empty islands between them."""
    tl = TagList(
        Tag("shiny-tool-request", data_shinychat_react=True),
        Tag("shiny-tool-result", data_shinychat_react=True),
    )
    result = split_html_islands(tl)
    rendered = TagList(result).render()["html"]
    assert "<shiny-chat-raw-html>" not in rendered
    assert "shiny-tool-request" in rendered
    assert "shiny-tool-result" in rendered


def test_single_tag_with_react_attr():
    """A single tag (not TagList) with react attr is emitted bare."""
    tag = Tag("shiny-tool-request", data_shinychat_react=True)
    result = split_html_islands(tag)
    rendered = TagList(result).render()["html"]
    assert "<shiny-chat-raw-html>" not in rendered


def test_single_tag_without_react_attr():
    """A single tag without react attr gets wrapped."""
    tag = div("hello")
    result = split_html_islands(tag)
    rendered = TagList(result).render()["html"]
    assert "<shiny-chat-raw-html>" in rendered


def test_string_content_in_taglist_wrapped():
    """Raw string content inside a TagList gets wrapped in an island."""
    tl = TagList("hello world")
    result = split_html_islands(tl)
    rendered = TagList(result).render()["html"]
    assert "<shiny-chat-raw-html>" in rendered
    assert "hello world" in rendered


def test_bare_string_content_wrapped():
    """A bare string passed directly is wrapped in an island."""
    result = split_html_islands("hello world")
    rendered = TagList(result).render()["html"]
    assert "<shiny-chat-raw-html>" in rendered
    assert "hello world" in rendered


def test_tagifiable_with_react_attr_emitted_bare():
    """A Tagifiable whose tagify() produces a react-attr Tag is emitted bare."""
    from htmltools import Tagifiable

    class FakeToolResult(Tagifiable):
        def tagify(self):
            return Tag(
                "shiny-tool-result",
                data_shinychat_react=True,
                request_id="test-123",
                tool_name="test_tool",
            )

    result = split_html_islands(FakeToolResult())
    rendered = TagList(result).render()["html"]
    assert "<shiny-chat-raw-html>" not in rendered
    assert "shiny-tool-result" in rendered
    assert "data-shinychat-react" in rendered


def test_tagifiable_without_react_attr_wrapped():
    """A Tagifiable whose tagify() produces a non-react Tag gets wrapped."""
    from htmltools import Tagifiable

    class FakeWidget(Tagifiable):
        def tagify(self):
            return div("widget content").tagify()

    result = split_html_islands(FakeWidget())
    rendered = TagList(result).render()["html"]
    assert "<shiny-chat-raw-html>" in rendered
    assert "widget content" in rendered


def test_tagifiable_in_taglist_splits_correctly():
    """A Tagifiable inside a TagList is correctly identified and split."""
    from htmltools import Tagifiable

    class FakeToolResult(Tagifiable):
        def tagify(self):
            return Tag(
                "shiny-tool-result",
                data_shinychat_react=True,
                request_id="test-456",
            ).tagify()

    tl = TagList(div("before"), FakeToolResult(), div("after"))
    result = split_html_islands(tl)
    rendered = TagList(result).render()["html"]
    assert rendered.count("<shiny-chat-raw-html>") == 2
    assert "shiny-tool-result" in rendered
    for line in rendered.split("\n"):
        if "shiny-tool-result" in line:
            assert "shiny-chat-raw-html" not in line


def test_mixed_taglist_keeps_plain_strings_untrusted():
    segments = split_content_by_trust(
        TagList("## This is markdown", div("This is HTML"))
    )

    assert len(segments) == 2
    assert segments[0] == (False, "## This is markdown")
    assert segments[1][0] is True


def test_html_marked_string_is_trusted():
    segments = split_content_by_trust(
        TagList("model text", HTML("<strong>server HTML</strong>"))
    )

    assert [trusted for trusted, _ in segments] == [False, True]


def test_markdown_stream_serializes_mixed_initial_provenance():
    el = output_markdown_stream(
        "stream",
        content=TagList("## This is markdown", div("This is HTML")),
    )
    segments = json.loads(str(el.attrs["content-segments"]))

    assert segments[0] == {
        "text": "## This is markdown",
        "trusted": False,
    }
    assert segments[1]["trusted"] is True
    assert "<shiny-chat-raw-html>" in segments[1]["text"]
    assert "<div>This is HTML</div>" in segments[1]["text"]
    assert el.attrs["content-trusted"] == "false"


def test_markdown_stream_marks_single_tag_initial_content_trusted():
    el = output_markdown_stream("stream", content=div("Trusted"))
    segments = json.loads(str(el.attrs["content-segments"]))

    assert segments[0]["trusted"] is True
    assert el.attrs["content-trusted"] == "true"


# --- Structured html_block emission from ChatMessage (kata#h6g2) ---


def test_chat_message_raw_html_becomes_html_block():
    """Raw (non-React) HTML content becomes a structured html_block; the
    content string stays empty and the message is html-typed."""
    from shinychat._chat_types import ChatMessage

    m = ChatMessage(content=HTML("<b>raw</b>"))

    assert m.content == ""
    assert m.content_type == "html"
    assert m.blocks == [
        {"type": "html_block", "version": 1, "content": "<b>raw</b>"}
    ]


def test_chat_message_mixed_content_interleaves_parts():
    """React elements stay bare string content; surrounding raw HTML becomes
    html_blocks; `parts` preserves the original order."""
    from shinychat._chat_types import ChatMessage

    react_el = Tag(
        "shiny-tool-result", data_shinychat_react=True, request_id="abc"
    )
    m = ChatMessage(content=TagList(div("before"), react_el, div("after")))

    assert [cast("HtmlBlock", b)["content"] for b in m.blocks] == [
        "<div>before</div>",
        "<div>after</div>",
    ]
    assert m.parts is not None
    assert m.parts[0] == m.blocks[0]
    assert isinstance(m.parts[1], str)
    assert "shiny-tool-result" in m.parts[1]
    assert m.parts[2] == m.blocks[1]
    # Flat content view holds the residual (React) markup
    assert "shiny-tool-result" in m.content
    assert m.content_type == "html"


def test_chat_message_html_block_deps_collected_on_block_and_message():
    """Block-level deps ride the block as serialized dicts AND the message as
    dep objects (the latter registers web-dependency routes)."""
    from htmltools import HTMLDependency
    from shinychat._chat_types import ChatMessage

    dep = HTMLDependency(
        "testlib", "1.0", source={"href": "/test"}, script={"src": "test.js"}
    )
    m = ChatMessage(content=TagList(div("x"), dep))

    assert len(m.blocks) == 1
    block = cast("HtmlBlock", m.blocks[0])
    assert block["type"] == "html_block"
    block_deps = block.get("html_deps")
    assert block_deps is not None
    assert block_deps[0]["name"] == "testlib"
    assert [d.name for d in m.html_deps] == ["testlib"]


def test_chat_message_mixed_content_wire_segments_preserve_order():
    """StoredMessage round-trip: wire_segments() reproduces the block/string
    interleaving recorded in `parts`."""
    from shinychat._chat_types import ChatMessage, StoredMessage

    react_el = Tag(
        "shiny-tool-result", data_shinychat_react=True, request_id="abc"
    )
    m = ChatMessage(content=TagList(div("before"), react_el, div("after")))
    stored = StoredMessage.from_chat_message(m)

    wire = stored.wire_segments()

    assert len(wire) == 3
    first = cast("HtmlBlock", wire[0])
    middle = cast("dict[str, str]", wire[1])
    last = cast("HtmlBlock", wire[2])
    assert first["type"] == "html_block"
    assert first["content"] == "<div>before</div>"
    assert "shiny-tool-result" in middle["content"]
    assert last["type"] == "html_block"
    assert last["content"] == "<div>after</div>"


if TYPE_CHECKING:
    from shinychat._chat_types import HtmlBlock, ToolResultBlock


def test_chat_message_html_content_with_supplied_blocks_merges_order():
    """When the caller passes BOTH non-string content (generating html_blocks)
    AND blocks=[...], the supplied blocks follow the content-derived parts,
    preserving prior flat-layout semantics (string segments first, then
    blocks). `parts` includes both; `wire_segments` round-trips."""
    from shinychat._chat_types import (
        ChatMessage,
        StoredMessage,
    )

    tool_block: ToolResultBlock = {
        "type": "tool_result",
        "version": 1,
        "request_id": "req-1",
        "tool_name": "my_tool",
        "status": "success",
        "value": "42",
    }
    m = ChatMessage(content=HTML("<b>raw</b>"), blocks=[tool_block])

    # blocks: generated html_block first, then supplied tool_block
    assert len(m.blocks) == 2
    assert m.blocks[0]["type"] == "html_block"
    assert m.blocks[1]["type"] == "tool_result"
    assert m.blocks[0]["content"] == "<b>raw</b>"

    # parts includes both the html_block and the supplied tool_block
    assert m.parts is not None
    assert len(m.parts) == 2
    assert m.parts[0] == m.blocks[0]
    assert m.parts[1] == m.blocks[1]

    # content is empty (no residual string from the HTML island)
    assert m.content == ""
    assert m.content_type == "html"

    # wire_segments round-trips: the flat layout leads with the (empty)
    # string segment, then the blocks in order
    stored = StoredMessage.from_chat_message(m)
    wire = stored.wire_segments()
    assert len(wire) == 3
    first = cast("dict[str, str]", wire[0])
    assert first == {"content": "", "content_type": "html"}
    assert cast("HtmlBlock", wire[1])["type"] == "html_block"
    assert cast("ToolResultBlock", wire[2])["type"] == "tool_result"
