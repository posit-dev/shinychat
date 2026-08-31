"""Wire-order tests for structured blocks (Phase 1 structured-content slice).

Covers:
- `transform_assistant_response` rewrites the string content only; structured
  `tool_result` blocks still ride along in the message payload's `segments`.
- Ordered interleaving: a chatlas `Turn` with text/tool-result/text content
  keeps its source order on the wire — as one `message` action's segments
  (non-streaming) and as a `chunk`/`block_insert`/`chunk` action sequence
  (streaming).
- `StoredMessage.wire_segments()` re-interleaves blocks at their recorded
  `block_positions`.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from chatlas import Turn
from chatlas._tools import Tool
from chatlas.types import (
    ContentText,
    ContentToolRequest,
    ContentToolResult,
    ToolInfo,
)
from shinychat._chat_types import (
    StoredMessage,
    StoredSegment,
    ToolResultBlock,
)
from shinychat.types import ChatMessage


def _tool() -> Tool:
    def my_tool(x: int) -> int:
        return x

    return Tool.from_func(my_tool)


def _request() -> ContentToolRequest:
    req = ContentToolRequest(id="call-1", name="my_tool", arguments={"x": 1})
    # Mirrors what chatlas itself does internally: `x.tool =
    # ToolInfo.from_tool(tool)`.
    req.tool = ToolInfo.from_tool(_tool())
    return req


def _result(request: ContentToolRequest) -> ContentToolResult:
    return ContentToolResult(value=2, request=request)


def _block() -> ToolResultBlock:
    return {
        "type": "tool_result",
        "version": 1,
        "request_id": "call-1",
        "tool_name": "my_tool",
        "status": "success",
        "value": "2",
        "value_type": "code",
    }


# ---------------------------------------------------------------------------
# Fix 1: transform_assistant_response carries structured blocks through
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_transform_preserves_structured_blocks() -> None:
    """A registered transform rewrites the string content only.

    `_transform_message` rebuilds the message from the transformed content;
    the structured `tool_result` block must carry through unchanged or the
    client never learns about the tool call.
    """
    from shiny._deprecated import ShinyDeprecationWarning
    from shiny.express._stub_session import ExpressStubSession
    from shiny.session import session_context
    from shinychat import Chat

    sent: list[Any] = []

    async def capture_action(action: Any, deps: Any = None) -> None:
        sent.append(action)

    with session_context(ExpressStubSession()):
        chat = Chat(id="chat")
        chat._send_action = capture_action  # type: ignore[method-assign]
        with pytest.warns(ShinyDeprecationWarning):
            chat.transform_assistant_response(lambda content: content.upper())
        await chat.append_message(
            ChatMessage(
                content="**before**",
                role="assistant",
                blocks=[_block()],
            )
        )

    assert len(sent) == 1
    action = sent[0]
    assert action["type"] == "message"
    segments = action["message"]["segments"]

    string_segments = [s for s in segments if "content" in s]
    assert [s["content"] for s in string_segments] == ["**BEFORE**"]

    block_segments = [s for s in segments if s.get("type") == "tool_result"]
    assert block_segments == [_block()]


# ---------------------------------------------------------------------------
# Fix 3: ordered interleaving of string runs and structured blocks
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_append_message_turn_interleaves_segments_in_order() -> None:
    """A text/tool-result/text Turn must arrive as text/block/text segments
    in one `message` action — not as text/text with the block appended."""
    from shiny.express._stub_session import ExpressStubSession
    from shiny.session import session_context
    from shinychat import Chat

    sent: list[Any] = []

    async def capture_action(action: Any, deps: Any = None) -> None:
        sent.append(action)

    turn = Turn(
        [
            ContentText(text="Before "),
            _result(_request()),
            ContentText(text=" After"),
        ],
        role="assistant",
    )

    with session_context(ExpressStubSession()):
        chat = Chat(id="chat")
        chat._send_action = capture_action  # type: ignore[method-assign]
        await chat.append_message(turn)

    assert len(sent) == 1
    action = sent[0]
    assert action["type"] == "message"
    segments = action["message"]["segments"]

    assert len(segments) == 3
    assert segments[0] == {"content": "Before ", "content_type": "markdown"}
    assert segments[1]["type"] == "tool_result"
    assert segments[1]["request_id"] == "call-1"
    assert segments[1]["tool_name"] == "my_tool"
    assert segments[2] == {"content": " After", "content_type": "markdown"}

    # No segment carries tool markup; the block is the only representation.
    assert all(
        "<shiny-tool-result" not in s.get("content", "") for s in segments
    )


@pytest.mark.anyio
async def test_stream_turn_interleaves_actions_in_order() -> None:
    """The same Turn mid-stream must emit a `chunk`/`block_insert`/`chunk`
    action sequence so the in-flight message keeps the source order."""
    from shiny.express._stub_session import ExpressStubSession
    from shiny.session import session_context
    from shinychat import Chat

    sent: list[Any] = []

    async def capture_action(action: Any, deps: Any = None) -> None:
        sent.append(action)

    turn = Turn(
        [
            ContentText(text="Before "),
            _result(_request()),
            ContentText(text=" After"),
        ],
        role="assistant",
    )

    with session_context(ExpressStubSession()):
        chat = Chat(id="chat")
        chat._send_action = capture_action  # type: ignore[method-assign]
        await chat._append_message_chunk(turn, stream_id="s1")

    types = [a["type"] for a in sent]
    assert types == ["chunk", "block_insert", "chunk"]

    chunks = [a for a in sent if a["type"] == "chunk"]
    assert [c["content"] for c in chunks] == ["Before ", " After"]
    assert all("<shiny-tool-result" not in c["content"] for c in chunks)

    block_action = sent[1]
    assert block_action["block"]["type"] == "tool_result"
    assert block_action["block"]["request_id"] == "call-1"


# ---------------------------------------------------------------------------
# Uniform replace semantics (kata#0r4g): a replace wipes the in-flight
# message (structured blocks included), then parts re-emit as appends
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_send_message_parts_replace_wipes_before_reemitting() -> None:
    """A block-carrying message sent with operation="replace" must emit a
    leading empty replace chunk (the wipe) before any part, then emit every
    part as an append.

    Without the leading wipe, a block emitted before the first string part
    would be wiped by that part's own replace chunk, and each subsequent
    string part would wipe the parts before it."""
    from shiny.express._stub_session import ExpressStubSession
    from shiny.session import session_context
    from shinychat import Chat

    sent: list[Any] = []

    async def capture_action(action: Any, deps: Any = None) -> None:
        sent.append(action)

    stored = StoredMessage(
        role="assistant",
        segments=[
            StoredSegment(content="Before ", content_type="markdown"),
            StoredSegment(content=" After", content_type="markdown"),
        ],
        blocks=[_block()],
        block_positions=[1],
    )

    with session_context(ExpressStubSession()):
        chat = Chat(id="chat")
        chat._send_action = capture_action  # type: ignore[method-assign]
        await chat._send_message_parts(stored, "replace")

    types = [a["type"] for a in sent]
    assert types == ["chunk", "chunk", "block_insert", "chunk"]

    wipe = sent[0]
    assert wipe["operation"] == "replace"
    assert wipe["content"] == ""

    # Every re-emitted part is an append, in wire-segment order.
    chunks = [a for a in sent[1:] if a["type"] == "chunk"]
    assert [c["operation"] for c in chunks] == ["append", "append"]
    assert [c["content"] for c in chunks] == ["Before ", " After"]
    assert sent[2]["block"]["type"] == "tool_result"


@pytest.mark.anyio
async def test_send_message_parts_replace_blocks_only_still_wipes() -> None:
    """A blocks-only replace has no string part to carry operation="replace";
    the leading wipe is what actually replaces the in-flight message."""
    from shiny.express._stub_session import ExpressStubSession
    from shiny.session import session_context
    from shinychat import Chat

    sent: list[Any] = []

    async def capture_action(action: Any, deps: Any = None) -> None:
        sent.append(action)

    stored = StoredMessage(
        role="assistant",
        segments=[],
        blocks=[_block()],
    )

    with session_context(ExpressStubSession()):
        chat = Chat(id="chat")
        chat._send_action = capture_action  # type: ignore[method-assign]
        await chat._send_message_parts(stored, "replace")

    types = [a["type"] for a in sent]
    assert types == ["chunk", "block_insert"]
    assert sent[0]["operation"] == "replace"
    assert sent[0]["content"] == ""
    assert sent[1]["block"]["type"] == "tool_result"


def test_wire_segments_reinterleaves_blocks_at_recorded_positions() -> None:
    """`block_positions` records how many string segments precede each block;
    `wire_segments()` must reproduce that interleaving."""
    stored = StoredMessage(
        role="assistant",
        segments=[
            StoredSegment(content="Before ", content_type="markdown"),
            StoredSegment(content=" After", content_type="markdown"),
        ],
        blocks=[_block()],
        block_positions=[1],
    )

    segments = stored.wire_segments()

    assert len(segments) == 3
    assert segments[0] == {"content": "Before ", "content_type": "markdown"}
    assert segments[1] == cast(Any, _block())
    assert segments[2] == {"content": " After", "content_type": "markdown"}


def test_wire_segments_falls_back_to_flat_layout() -> None:
    """Without `block_positions`, blocks keep following the string segments
    (the pre-interleaving wire shape)."""
    stored = StoredMessage(
        role="assistant",
        segments=[StoredSegment(content="text", content_type="markdown")],
        blocks=[_block()],
    )

    segments = stored.wire_segments()

    assert len(segments) == 2
    assert segments[0] == {"content": "text", "content_type": "markdown"}
    assert segments[1] == cast(Any, _block())
