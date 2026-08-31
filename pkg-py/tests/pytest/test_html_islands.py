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
    # Trusted UI ships as a structured html_block entry, not an island-tag
    # string segment (kata#mhyd).
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
    path, which must never render fallback content as trusted (kata#mhyd)."""
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


def test_chat_message_block_html_deps_stashes_dep_objects():
    """ChatMessage.__init__ stashes dep OBJECTS per block index in
    _block_html_deps so the session-aware send path can serialize them
    through _process_ui. The block's raw as_dict() is the no-session
    fallback. See kata#rpx1."""
    from htmltools import HTMLDependency
    from shinychat._chat_types import ChatMessage

    dep = HTMLDependency(
        "testlib", "1.0", source={"href": "/test"}, script={"src": "test.js"}
    )
    m = ChatMessage(content=TagList(div("x"), dep))

    assert len(m.blocks) == 1
    # _block_html_deps maps block index → dep objects
    assert 0 in m._block_html_deps
    stashed = m._block_html_deps[0]
    assert len(stashed) == 1
    assert isinstance(stashed[0], HTMLDependency)
    assert stashed[0].name == "testlib"


def test_chat_message_block_html_deps_multiple_blocks_indexed():
    """When content produces multiple html_blocks, _block_html_deps maps
    each block index to its dep objects. See kata#rpx1."""
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
    # The React element splits the content into two islands, each with its
    # own dep, producing two html_blocks.
    m = ChatMessage(content=TagList(div("x"), dep1, react_el, div("y"), dep2))

    assert len(m.blocks) == 2
    assert set(m._block_html_deps.keys()) == {0, 1}
    assert [d.name for d in m._block_html_deps[0]] == ["lib1"]
    assert [d.name for d in m._block_html_deps[1]] == ["lib2"]


def test_as_stored_message_processes_block_deps_with_session():
    """_as_stored_message overwrites block-level raw as_dict() html_deps
    with session-processed deps (route-registered hrefs, lib_prefix
    applied). See kata#rpx1."""
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
        # Processed deps carry the session marker
        assert block_deps[0].get("from_session") == "process-ui-session"
        assert block_deps[0]["name"] == "testlib"


def test_as_stored_message_no_session_keeps_raw_deps():
    """Without a session, _as_stored_message cannot process block deps;
    the raw as_dict() fallback on the block survives. See kata#rpx1."""
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
        # Simulate the no-session path: _serialize_html_deps returns None
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
        # No session → _serialize_html_deps returns None → raw as_dict() stays
        assert block_deps is not None
        assert "from_session" not in block_deps[0]
        assert block_deps[0]["name"] == "testlib"


def test_append_message_emits_processed_block_deps():
    """Wire-level: append_message with html_block content carrying a
    dependency → the block_insert action's block html_deps are
    session-processed. See kata#rpx1."""
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
        # Non-streaming message with blocks emits via _send_message_parts
        # (block_insert actions) — but actually for chunk=False, it sends a
        # "message" action with segments. Check both paths.
        if block_inserts:
            block = block_inserts[0]["action"]["block"]
        else:
            # The "message" action carries segments including the block
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


def test_turn_normalization_reindexes_block_dep_objects():
    """Turn normalization combines item messages into a new ChatMessage; the
    per-block dep-object map must be reindexed onto the combined block list
    or _as_stored_message can't session-process the deps. See kata#rpx1."""
    from chatlas import Turn
    from chatlas._content import ContentText
    from htmltools import HTMLDependency
    from shinychat import _chat_normalize
    from shinychat._chat_types import ChatMessage

    dep = HTMLDependency(
        "testlib", "1.0", source={"href": "/test"}, script={"src": "test.js"}
    )

    # Turn contents are a closed union of chatlas types, none of which
    # produce html_blocks today — simulate a future content type by
    # patching the per-item normalizer.
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
