from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from htmltools import HTML, Tag, TagList, div, span
from shinychat import output_markdown_stream
from shinychat._html_islands import (
    IslandBlockPart,
    IslandResidualPart,
    derive_island_parts,
    split_content_by_trust,
)


def test_plain_html_becomes_single_block_part():
    """Non-react content renders as a single block part (no island tag)."""
    tl = TagList(div("hello"), span("world"))
    parts = derive_island_parts(tl)
    assert len(parts) == 1
    assert isinstance(parts[0], IslandBlockPart)
    assert "<div>hello</div>" in parts[0].html
    assert "<span>world</span>" in parts[0].html
    assert "shiny-chat-raw-html" not in parts[0].html


def test_react_element_becomes_residual_part():
    """A single react element renders bare as a residual string run."""
    tl = TagList(
        Tag("shiny-tool-result", data_shinychat_react=True, request_id="abc")
    )
    parts = derive_island_parts(tl)
    assert len(parts) == 1
    assert isinstance(parts[0], IslandResidualPart)
    assert "shiny-tool-result" in parts[0].html
    assert "data-shinychat-react" in parts[0].html
    assert "shiny-chat-raw-html" not in parts[0].html
    assert parts[0].html.startswith("\n\n")
    assert parts[0].html.endswith("\n\n")


def test_mixed_content_splits_around_react():
    """React elements split surrounding HTML into separate block parts."""
    tl = TagList(
        div("before"),
        Tag("shiny-tool-result", data_shinychat_react=True, request_id="abc"),
        div("after"),
    )
    parts = derive_island_parts(tl)
    assert len(parts) == 3
    assert isinstance(parts[0], IslandBlockPart)
    assert isinstance(parts[1], IslandResidualPart)
    assert isinstance(parts[2], IslandBlockPart)
    assert parts[0].html == "<div>before</div>"
    assert parts[2].html == "<div>after</div>"
    assert "shiny-tool-result" in parts[1].html
    assert "shiny-tool-result" not in parts[0].html
    assert "shiny-tool-result" not in parts[2].html


def test_adjacent_react_elements_coalesce_into_one_residual():
    """Two consecutive react elements coalesce into a single residual run."""
    tl = TagList(
        Tag("shiny-tool-request", data_shinychat_react=True),
        Tag("shiny-tool-result", data_shinychat_react=True),
    )
    parts = derive_island_parts(tl)
    assert len(parts) == 1
    assert isinstance(parts[0], IslandResidualPart)
    assert "shiny-tool-request" in parts[0].html
    assert "shiny-tool-result" in parts[0].html


def test_single_tag_with_react_attr():
    """A single tag (not TagList) with react attr becomes a residual run."""
    tag = Tag("shiny-tool-request", data_shinychat_react=True)
    parts = derive_island_parts(tag)
    assert len(parts) == 1
    assert isinstance(parts[0], IslandResidualPart)
    assert "shiny-tool-request" in parts[0].html


def test_single_tag_without_react_attr():
    """A single tag without react attr becomes a block part."""
    tag = div("hello")
    parts = derive_island_parts(tag)
    assert len(parts) == 1
    assert isinstance(parts[0], IslandBlockPart)
    assert parts[0].html == "<div>hello</div>"


def test_string_content_in_taglist_becomes_block_part():
    """Raw string content inside a TagList renders as a block part."""
    tl = TagList("hello world")
    parts = derive_island_parts(tl)
    assert len(parts) == 1
    assert isinstance(parts[0], IslandBlockPart)
    assert "hello world" in parts[0].html


def test_bare_string_content_becomes_block_part():
    """A bare string passed directly renders as a block part."""
    parts = derive_island_parts("hello world")
    assert len(parts) == 1
    assert isinstance(parts[0], IslandBlockPart)
    assert "hello world" in parts[0].html


def test_tagifiable_with_react_attr_becomes_residual_part():
    """A Tagifiable whose tagify() produces a react-attr Tag renders bare."""
    from htmltools import Tagifiable

    class FakeToolResult(Tagifiable):
        def tagify(self):
            return Tag(
                "shiny-tool-result",
                data_shinychat_react=True,
                request_id="test-123",
                tool_name="test_tool",
            ).tagify()

    parts = derive_island_parts(FakeToolResult())
    assert len(parts) == 1
    assert isinstance(parts[0], IslandResidualPart)
    assert "shiny-tool-result" in parts[0].html
    assert "data-shinychat-react" in parts[0].html


def test_tagifiable_without_react_attr_becomes_block_part():
    """A Tagifiable whose tagify() produces a non-react Tag becomes a block."""
    from htmltools import Tagifiable

    class FakeWidget(Tagifiable):
        def tagify(self):
            return div("widget content").tagify()

    parts = derive_island_parts(FakeWidget())
    assert len(parts) == 1
    assert isinstance(parts[0], IslandBlockPart)
    assert "widget content" in parts[0].html


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
    parts = derive_island_parts(tl)
    assert len(parts) == 3
    assert isinstance(parts[0], IslandBlockPart)
    assert isinstance(parts[1], IslandResidualPart)
    assert isinstance(parts[2], IslandBlockPart)
    assert "shiny-tool-result" in parts[1].html
    assert "shiny-tool-result" not in parts[0].html
    assert "shiny-tool-result" not in parts[2].html


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
    # Trusted UI ships as a structured html_block entry, not an island-tag
    # string segment.
    assert segments[1] == {
        "block": {
            "type": "html_block",
            "version": 1,
            "content": "<div>This is HTML</div>",
        }
    }
    assert el.attrs["content-trusted"] == "false"


def test_markdown_stream_single_tag_initial_content_becomes_block():
    """A lone trusted tag becomes a single html_block entry. The
    content-trusted fallback stays "false": it only governs the fail-closed
    path, which must never render fallback content as trusted."""
    el = output_markdown_stream("stream", content=div("Trusted"))
    segments = json.loads(str(el.attrs["content-segments"]))

    assert segments[0] == {
        "block": {
            "type": "html_block",
            "version": 1,
            "content": "<div>Trusted</div>",
        }
    }
    assert el.attrs["content-trusted"] == "false"


# --- Structured html_block emission from ChatMessage ---


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


def test_chat_message_block_html_deps_stashes_dep_objects():
    """ChatMessage.__init__ stashes dep objects per block index in
    _block_html_deps so the session-aware send path can serialize them
    through _process_ui. The block's raw as_dict() is the no-session
    fallback."""
    from htmltools import HTMLDependency
    from shinychat._chat_types import ChatMessage

    dep = HTMLDependency(
        "testlib", "1.0", source={"href": "/test"}, script={"src": "test.js"}
    )
    m = ChatMessage(content=TagList(div("x"), dep))

    assert len(m.blocks) == 1
    assert 0 in m._block_html_deps
    stashed = m._block_html_deps[0]
    assert len(stashed) == 1
    assert isinstance(stashed[0], HTMLDependency)
    assert stashed[0].name == "testlib"


def test_chat_message_block_html_deps_multiple_blocks_indexed():
    """When content produces multiple html_blocks, _block_html_deps maps
    each block index to its dep objects."""
    from htmltools import HTMLDependency
    from shinychat._chat_types import ChatMessage

    dep1 = HTMLDependency(
        "lib1", "1.0", source={"href": "/a"}, script={"src": "a.js"}
    )
    dep2 = HTMLDependency(
        "lib2", "2.0", source={"href": "/b"}, script={"src": "b.js"}
    )
    react_el = Tag(
        "shiny-tool-result", data_shinychat_react=True, request_id="abc"
    )
    m = ChatMessage(content=TagList(div("x"), dep1, react_el, div("y"), dep2))

    assert len(m.blocks) == 2
    assert set(m._block_html_deps.keys()) == {0, 1}
    assert [d.name for d in m._block_html_deps[0]] == ["lib1"]
    assert [d.name for d in m._block_html_deps[1]] == ["lib2"]


def test_as_stored_message_processes_block_deps_with_session():
    """_as_stored_message overwrites block-level raw as_dict() html_deps
    with session-processed deps (route-registered hrefs, lib_prefix
    applied)."""
    from typing import Any, cast

    from htmltools import HTMLDependency, TagList
    from shiny import Inputs, Session
    from shiny.module import ResolvedId
    from shiny.session import session_context
    from shinychat import Chat
    from shinychat._chat_types import ChatMessage

    class _ProcessUISession:
        ns: ResolvedId = ResolvedId("")
        app: object = None
        id: str = "process-ui-session"

        def __init__(self) -> None:
            self.input = Inputs({}, ns=ResolvedId)

        def on_ended(self, callback: object) -> None:
            pass

        def on_destroy(self, callback: object) -> None:
            pass

        def _increment_busy_count(self) -> None:
            pass

        def _process_ui(self, ui: object) -> dict[str, object]:
            rendered = TagList(cast(Any, ui)).render()
            return {
                "html": rendered["html"],
                "deps": [
                    {**d.as_dict(), "from_session": self.id}
                    for d in rendered["dependencies"]
                ],
            }

        async def send_custom_message(
            self, type: str, message: dict[str, Any]
        ) -> None:
            pass

    session = cast(Session, _ProcessUISession())
    with session_context(session):
        chat = Chat(id="chat")
        dep = HTMLDependency(
            "testlib",
            "1.0",
            source={"href": "/test"},
            script={"src": "test.js"},
        )
        msg = ChatMessage(content=TagList(div("x"), dep))
        stored = chat._as_stored_message(msg)

        assert len(stored.blocks) == 1
        block = cast("HtmlBlock", stored.blocks[0])
        block_deps = block.get("html_deps")
        assert block_deps is not None
        assert block_deps[0].get("from_session") == "process-ui-session"
        assert block_deps[0]["name"] == "testlib"


def test_as_stored_message_no_session_keeps_raw_deps():
    """Without a session, _as_stored_message cannot process block deps;
    the raw as_dict() fallback on the block survives."""
    from typing import Any, cast

    from htmltools import HTMLDependency
    from shiny import Inputs, Session
    from shiny.module import ResolvedId
    from shiny.session import session_context
    from shinychat import Chat
    from shinychat._chat_types import ChatMessage

    class _NoProcessSession:
        ns: ResolvedId = ResolvedId("")
        app: object = None
        id: str = "no-process-session"

        def __init__(self) -> None:
            self.input = Inputs({}, ns=ResolvedId)

        def on_ended(self, callback: object) -> None:
            pass

        def on_destroy(self, callback: object) -> None:
            pass

        def _increment_busy_count(self) -> None:
            pass

        async def send_custom_message(
            self, type: str, message: dict[str, Any]
        ) -> None:
            pass

    session = cast(Session, _NoProcessSession())
    with session_context(session):
        chat = Chat(id="chat")
        cast(Any, chat)._session = None
        dep = HTMLDependency(
            "testlib",
            "1.0",
            source={"href": "/test"},
            script={"src": "test.js"},
        )
        msg = ChatMessage(content=TagList(div("x"), dep))
        stored = chat._as_stored_message(msg)

        assert len(stored.blocks) == 1
        block = cast("HtmlBlock", stored.blocks[0])
        block_deps = block.get("html_deps")
        assert block_deps is not None
        assert "from_session" not in block_deps[0]
        assert block_deps[0]["name"] == "testlib"


def test_append_message_emits_processed_block_deps():
    """Wire-level: append_message with html_block content carrying a
    dependency → the block_insert action's block html_deps are
    session-processed."""
    import asyncio
    import threading
    from typing import Any, cast

    from htmltools import HTMLDependency, TagList
    from shiny import Inputs, Session
    from shiny.module import ResolvedId
    from shiny.session import session_context
    from shinychat import Chat
    from shinychat._chat_types import ChatMessage

    class _CaptureSession:
        ns: ResolvedId = ResolvedId("")
        app: object = None
        id: str = "capture-session"

        def __init__(self) -> None:
            self.input = Inputs({}, ns=ResolvedId)
            self.envelopes: list[dict[str, Any]] = []

        def on_ended(self, callback: object) -> None:
            pass

        def on_destroy(self, callback: object) -> None:
            pass

        def _increment_busy_count(self) -> None:
            pass

        def _process_ui(self, ui: object) -> dict[str, object]:
            rendered = TagList(cast(Any, ui)).render()
            return {
                "html": rendered["html"],
                "deps": [
                    {**d.as_dict(), "from_session": self.id}
                    for d in rendered["dependencies"]
                ],
            }

        async def send_custom_message(
            self, type: str, message: dict[str, Any]
        ) -> None:
            self.envelopes.append(message)

    mock_session = _CaptureSession()
    session = cast(Session, mock_session)
    with session_context(session):
        chat = Chat(id="chat")
        dep = HTMLDependency(
            "testlib",
            "1.0",
            source={"href": "/test"},
            script={"src": "test.js"},
        )
        msg = ChatMessage(content=TagList(div("x"), dep))

        errors: list[BaseException] = []

        def _run() -> None:
            try:
                asyncio.run(chat.append_message(msg))
            except BaseException as err:
                errors.append(err)

        t = threading.Thread(target=_run)
        t.start()
        t.join()
        if errors:
            raise errors[0]

        # Find the block_insert action in the captured envelopes
        block_inserts = [
            e
            for e in mock_session.envelopes
            if e["action"]["type"] == "block_insert"
        ]
        if block_inserts:
            block = block_inserts[0]["action"]["block"]
        else:
            msg_envelopes = [
                e
                for e in mock_session.envelopes
                if e["action"]["type"] == "message"
            ]
            assert msg_envelopes, (
                f"Expected message action, got {[e['action']['type'] for e in mock_session.envelopes]}"
            )
            segments = msg_envelopes[0]["action"]["message"]["segments"]
            block = next(s for s in segments if s.get("type") == "html_block")

        block_deps = block.get("html_deps")
        assert block_deps is not None
        assert block_deps[0].get("from_session") == "capture-session"
        assert block_deps[0]["name"] == "testlib"


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

    assert len(m.blocks) == 2
    assert m.blocks[0]["type"] == "html_block"
    assert m.blocks[1]["type"] == "tool_result"
    assert m.blocks[0]["content"] == "<b>raw</b>"

    assert m.parts is not None
    assert len(m.parts) == 2
    assert m.parts[0] == m.blocks[0]
    assert m.parts[1] == m.blocks[1]

    assert m.content == ""
    assert m.content_type == "html"

    stored = StoredMessage.from_chat_message(m)
    wire = stored.wire_segments()
    assert len(wire) == 3
    first = cast("dict[str, str]", wire[0])
    assert first == {"content": "", "content_type": "html"}
    assert cast("HtmlBlock", wire[1])["type"] == "html_block"
    assert cast("ToolResultBlock", wire[2])["type"] == "tool_result"


def test_turn_normalization_reindexes_block_dep_objects():
    """Turn normalization combines item messages into a new ChatMessage; the
    per-block dep-object map must be reindexed onto the combined block list
    or _as_stored_message can't session-process the deps."""
    from chatlas import Turn
    from chatlas._content import ContentText
    from htmltools import HTMLDependency
    from shinychat import _chat_normalize
    from shinychat._chat_types import ChatMessage

    dep = HTMLDependency(
        "testlib", "1.0", source={"href": "/test"}, script={"src": "test.js"}
    )

    def fake_normalize(x: object) -> ChatMessage:
        return ChatMessage(content=TagList(div("x"), dep))

    turn = Turn(
        [ContentText(text="a"), ContentText(text="b")], role="assistant"
    )
    original = _chat_normalize.normalize_message
    _chat_normalize.normalize_message = fake_normalize  # type: ignore[assignment]
    try:
        m = _chat_normalize.message_content(turn)
    finally:
        _chat_normalize.normalize_message = original  # type: ignore[assignment]

    assert len(m.blocks) == 2
    assert set(m._block_html_deps.keys()) == {0, 1}
    assert m._block_html_deps[0][0].name == "testlib"
    assert m._block_html_deps[1][0].name == "testlib"


# --- Homogenized construction contract: TagList is an HTML container ---


def test_chat_message_mixed_taglist_bare_string_is_escaped_html():
    """TagList content is an HTML container: a bare string mixed with tags is
    an escaped text node, NOT a markdown segment. The whole TagList renders
    to a single trusted html_block with the string HTML-escaped — matching
    every shipped release's behavior. To mix markdown and UI in one message,
    use the `parts` segment list instead."""
    from shinychat._chat_types import ChatMessage, StoredMessage

    m = ChatMessage(
        content=TagList("**markdown** and <b>html</b>", div("trusted"))
    )

    # One trusted html_block; the bare string is escaped inside it.
    assert m.parts is None
    assert m.content == ""
    assert m.content_type == "html"
    assert len(m.blocks) == 1
    block = cast("HtmlBlock", m.blocks[0])
    assert block["type"] == "html_block"
    assert "**markdown** and &lt;b&gt;html&lt;/b&gt;" in block["content"]
    assert "<div>trusted</div>" in block["content"]

    stored = StoredMessage.from_chat_message(m)
    wire = stored.wire_segments()
    assert len(wire) == 2
    assert cast("dict[str, str]", wire[0]) == {
        "content": "",
        "content_type": "html",
    }
    assert cast("HtmlBlock", wire[1])["content"] == block["content"]


def test_chat_message_parts_segment_list_strings_are_markdown():
    """The `parts` segment list is the deliberate mixing affordance: bare
    strings are stamped with the message content_type (markdown by default)
    and interleave with structured blocks on the wire."""
    from shinychat._chat_types import ChatMessage, StoredMessage

    block: HtmlBlock = {
        "type": "html_block",
        "version": 1,
        "content": "<div>trusted</div>",
    }
    m = ChatMessage(content="", parts=["**markdown**", block])

    stored = StoredMessage.from_chat_message(m)
    wire = stored.wire_segments()
    assert len(wire) == 2
    assert cast("dict[str, str]", wire[0]) == {
        "content": "**markdown**",
        "content_type": "markdown",
    }
    assert cast("HtmlBlock", wire[1])["type"] == "html_block"
    assert cast("HtmlBlock", wire[1])["content"] == "<div>trusted</div>"


# --- Pure-case behavior pins ---


def test_chat_message_pure_string_content_stays_markdown():
    """A pure-string ChatMessage keeps content_type "markdown" and parts is
    None (flat layout path)."""
    from shinychat._chat_types import ChatMessage, StoredMessage

    m = ChatMessage(content="**plain markdown**")

    assert m.content == "**plain markdown**"
    assert m.content_type == "markdown"
    assert m.blocks == []
    assert m.parts is None

    stored = StoredMessage.from_chat_message(m)
    wire = stored.wire_segments()
    assert len(wire) == 1
    assert cast("dict[str, str]", wire[0])["content"] == "**plain markdown**"
    assert cast("dict[str, str]", wire[0])["content_type"] == "markdown"


def test_chat_message_pure_tag_content_becomes_html_block():
    """A pure-tag ChatMessage (no bare strings) becomes a single html_block;
    parts stays None (flat layout)."""
    from shinychat._chat_types import ChatMessage, StoredMessage

    m = ChatMessage(content=div("trusted"))

    assert m.content == ""
    assert m.content_type == "html"
    assert len(m.blocks) == 1
    assert m.blocks[0] == {
        "type": "html_block",
        "version": 1,
        "content": "<div>trusted</div>",
    }
    assert m.parts is None

    stored = StoredMessage.from_chat_message(m)
    wire = stored.wire_segments()
    assert len(wire) == 2
    assert cast("dict[str, str]", wire[0]) == {
        "content": "",
        "content_type": "html",
    }
    assert cast("HtmlBlock", wire[1])["content"] == "<div>trusted</div>"


def test_chat_message_html_marked_string_stays_trusted_html_block():
    """An HTML()-marked string is trusted and becomes a single html_block."""
    from shinychat._chat_types import ChatMessage, StoredMessage

    m = ChatMessage(content=HTML("<b>raw</b>"))

    assert m.content == ""
    assert m.content_type == "html"
    assert m.blocks == [
        {"type": "html_block", "version": 1, "content": "<b>raw</b>"}
    ]
    assert m.parts is None

    stored = StoredMessage.from_chat_message(m)
    wire = stored.wire_segments()
    assert len(wire) == 2
    assert cast("dict[str, str]", wire[0]) == {
        "content": "",
        "content_type": "html",
    }
    assert cast("HtmlBlock", wire[1])["content"] == "<b>raw</b>"


# --- Segments-native ChatMessage ---


def test_chat_message_parts_and_blocks_raise():
    """parts= and blocks= are mutually exclusive input spellings."""
    import pytest
    from shinychat._chat_types import ChatMessage

    block = cast("HtmlBlock", {"type": "html_block", "version": 1, "content": "<b>x</b>"})
    with pytest.raises(ValueError, match="mutually exclusive"):
        ChatMessage(content="", blocks=[block], parts=["text"])


def test_chat_message_parts_and_nonempty_content_raise():
    """parts= combined with string content raises instead of silently
    discarding the content."""
    import pytest
    from shinychat._chat_types import ChatMessage

    with pytest.raises(ValueError, match="cannot be combined"):
        ChatMessage(content="dropped", parts=["text"])


def test_chat_message_parts_and_tagchild_content_raise():
    """parts= combined with TagChild content raises instead of silently
    overwriting the caller's parts."""
    import pytest
    from shinychat._chat_types import ChatMessage

    with pytest.raises(ValueError, match="cannot be combined"):
        ChatMessage(content=HTML("<b>x</b>"), parts=["text"])


def test_chat_message_parts_only_construction_derives_views():
    """parts-only construction compiles to segments; content/blocks/parts are
    derived views and the wire round-trips the interleaving."""
    from shinychat._chat_types import ChatMessage, StoredMessage

    block = cast("HtmlBlock", {"type": "html_block", "version": 1, "content": "<div>trusted</div>"})
    m = ChatMessage("", parts=["**a**", block, "b"])

    assert m.content == "**a**b"
    assert m.blocks == [block]
    assert m.parts == ["**a**", block, "b"]
    assert m.content_type == "markdown"

    stored = StoredMessage.from_chat_message(m)
    wire = stored.wire_segments()
    assert len(wire) == 3
    assert wire[0] == {"content": "**a**", "content_type": "markdown"}
    assert cast("HtmlBlock", wire[1])["type"] == "html_block"
    assert wire[2] == {"content": "b", "content_type": "markdown"}


def test_chat_message_segments_pin_taglist_html_container():
    """The TagList-as-HTML-container contract on segments: one html_block
    with bare strings escaped, content_type flipped to html."""
    from shinychat._chat_types import ChatMessage

    m = ChatMessage(
        content=TagList("**markdown** and <b>html</b>", div("trusted"))
    )

    assert len(m.segments) == 1
    block = m.segments[0]
    assert isinstance(block, dict)
    assert block["type"] == "html_block"
    assert "**markdown** and &lt;b&gt;html&lt;/b&gt;" in str(block["content"])
    assert "<div>trusted</div>" in str(block["content"])
    assert m.content_type == "html"


def test_chat_message_segments_pin_mixed_react_interleave():
    """Mixed TagList content compiles to [html_block, residual string,
    html_block] segments; the residual string segment is content_type html."""
    from shinychat._chat_types import ChatMessage, ContentSegment

    react_el = Tag(
        "shiny-tool-result", data_shinychat_react=True, request_id="abc"
    )
    m = ChatMessage(content=TagList(div("before"), react_el, div("after")))

    assert len(m.segments) == 3
    first, middle, last = m.segments
    assert isinstance(first, dict) and first["type"] == "html_block"
    assert isinstance(middle, ContentSegment)
    assert middle.content_type == "html"
    assert "shiny-tool-result" in middle.content
    assert isinstance(last, dict) and last["type"] == "html_block"


def test_chat_message_content_setter_collapses_to_flat_layout():
    """The streaming replace path (content= then parts=None) collapses an
    interleaved message to one string segment with blocks trailing."""
    from shinychat._chat_types import ChatMessage, ContentSegment, StoredMessage

    react_el = Tag(
        "shiny-tool-result", data_shinychat_react=True, request_id="abc"
    )
    m = ChatMessage(content=TagList(div("before"), react_el, div("after")))

    m.content = "replaced"
    m.parts = None

    assert isinstance(m.segments[0], ContentSegment)
    assert m.content == "replaced"
    assert len(m.blocks) == 2

    stored = StoredMessage.from_chat_message(m)
    assert stored.block_positions is None
    wire = stored.wire_segments()
    assert [s.get("type", "str") for s in wire] == [
        "str",
        "html_block",
        "html_block",
    ]
    assert wire[0] == {"content": "replaced", "content_type": "html"}


def test_turn_normalization_round_trips_through_parts():
    """A text-only Turn merges into a single flat markdown segment, as
    before the segments-native refactor."""
    from chatlas import Turn
    from chatlas._content import ContentText
    from shinychat import _chat_normalize
    from shinychat._chat_types import StoredMessage

    turn = Turn(
        [ContentText(text="a"), ContentText(text="b")], role="assistant"
    )
    m = _chat_normalize.message_content(turn)

    assert m.content == "ab"
    assert m.content_type == "markdown"
    assert m.parts is None
    assert m.blocks == []

    stored = StoredMessage.from_chat_message(m)
    wire = stored.wire_segments()
    assert wire == [{"content": "ab", "content_type": "markdown"}]


def test_chat_message_parts_coalesce_with_paragraph_break():
    """Adjacent bare strings in parts= coalesce into one segment joined by a
    paragraph break (direct concatenation is unsafe at a markdown seam)."""
    from shinychat._chat_types import ChatMessage, StoredMessage

    m = ChatMessage("", parts=["# Title", "body text"])

    assert m.content == "# Title\n\nbody text"
    assert m.parts is None

    stored = StoredMessage.from_chat_message(m)
    assert stored.wire_segments() == [
        {"content": "# Title\n\nbody text", "content_type": "markdown"}
    ]


def test_chat_message_parts_coalesce_non_markdown_directly():
    """Only markdown parts coalesce with a paragraph break; html and text
    parts concatenate directly (author controls the exact bytes)."""
    from shinychat._chat_types import ChatMessage

    m = ChatMessage("", content_type="html", parts=["<b>", "</b>"])
    assert m.content == "<b></b>"

    m = ChatMessage("", content_type="text", parts=["a", "b"])
    assert m.content == "ab"
