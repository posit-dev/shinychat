"""Tests for MarkdownStream structured `html_block` emission (kata#mhyd).

Trusted non-string content (Shiny UI) in a markdown stream ships as
structured `html_block` envelopes — not as `<shiny-chat-raw-html>` island
tags inside content strings — both mid-stream (`MarkdownStream.stream()`)
and in the initial `content-segments` attribute (`output_markdown_stream`).
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, cast

from htmltools import HTMLDependency, Tag, TagList, div
from shiny import Inputs, Session
from shiny.module import ResolvedId
from shiny.session import session_context
from shinychat import MarkdownStream, output_markdown_stream


class _CaptureSession:
    """Minimal session capturing custom messages. `_process_ui` marks deps
    as session-processed (mirrors the pattern in test_html_islands.py)."""

    ns: ResolvedId = ResolvedId("")
    app: object = None
    id: str = "capture-session"

    def __init__(self) -> None:
        self.input = Inputs({}, ns=ResolvedId)
        self.messages: list[dict[str, Any]] = []

    def on_ended(self, callback: object) -> None:
        pass

    def on_destroy(self, callback: object) -> None:
        pass

    def _increment_busy_count(self) -> None:
        pass

    def is_stub_session(self) -> bool:
        return False

    def _process_ui(self, ui: object) -> dict[str, Any]:
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
        assert type == "shinyMarkdownStreamMessage"
        self.messages.append(message)


def run_stream(ms: MarkdownStream, content: Any) -> str:
    """Drive MarkdownStream.stream()'s extended task to completion.

    stream() schedules a reactive extended task on the current event loop,
    so run it inside asyncio.run (in a thread, mirroring run_async in
    test_chat.py) and await the underlying asyncio task to make the wire
    emission synchronous for the test. Returns the task's result string.
    """
    results: list[str] = []
    errors: list[BaseException] = []

    def _run() -> None:
        async def _exercise() -> None:
            task = await ms.stream(content)
            # The ExtendedTask's underlying asyncio task; awaiting it runs
            # the stream body to completion.
            inner = getattr(task, "_task", None)
            if inner is not None:
                await inner
                results.append(inner.result())
            # Let the done-callback's reactive flush (and the error-handling
            # effect's self-destruction) settle before the loop closes.
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        try:
            asyncio.run(_exercise())
        except BaseException as err:  # noqa: BLE001
            errors.append(err)

    t = threading.Thread(target=_run)
    t.start()
    t.join()
    if errors:
        raise errors[0]
    return results[0] if results else ""


def content_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The non-streaming-dot messages (content and block carriers)."""
    return [m for m in messages if "isStreaming" not in m]


# ---------------------------------------------------------------------------
# MarkdownStream.stream() wire emission
# ---------------------------------------------------------------------------


def test_stream_emits_html_block_for_trusted_island_content():
    """A trusted tag ships as a structured html_block block-message, not as
    an island-tag string segment."""
    mock = _CaptureSession()
    with session_context(cast(Session, mock)):
        ms = MarkdownStream(id="stream")
        run_stream(ms, [div("trusted UI")])

    msgs = content_messages(mock.messages)
    # Leading empty replace (the clear), then the block message.
    assert msgs[0] == {
        "id": "stream",
        "content": "",
        "operation": "replace",
        "html_deps": [],
        "trusted": False,
        "segment_start": True,
    }
    assert len(msgs) == 2
    block_msg = msgs[1]
    # A message carries content XOR block (kata#mhyd).
    assert "content" not in block_msg
    assert block_msg["operation"] == "append"
    block = block_msg["block"]
    assert block["type"] == "html_block"
    assert block["version"] == 1
    assert "<div>trusted UI</div>" in block["content"]
    # The island wrapper never appears on the wire anymore.
    assert "<shiny-chat-raw-html>" not in block["content"]


def test_stream_mixed_content_interleaves_blocks_and_segments():
    """Untrusted text stays an untrusted string segment; island wrappers
    become block messages; bare data-shinychat-react elements stay trusted
    residual string segments (blank-line wrapped)."""
    mock = _CaptureSession()
    react_el = Tag(
        "shiny-tool-result", data_shinychat_react=True, request_id="abc"
    )
    with session_context(cast(Session, mock)):
        ms = MarkdownStream(id="stream")
        run_stream(
            ms,
            ["model text ", TagList(div("before"), react_el, div("after"))],
        )

    msgs = content_messages(mock.messages)[1:]  # drop the leading clear

    kinds = ["block" if "block" in m else "content" for m in msgs]
    assert kinds == ["content", "block", "content", "block"]

    # Untrusted model text: unchanged string-segment behavior.
    assert msgs[0]["content"] == "model text "
    assert msgs[0]["trusted"] is False
    assert msgs[0]["segment_start"] is False

    # Island wrappers -> html_block envelopes carrying the children HTML.
    assert msgs[1]["block"]["type"] == "html_block"
    assert "<div>before</div>" in msgs[1]["block"]["content"]
    assert msgs[3]["block"]["type"] == "html_block"
    assert "<div>after</div>" in msgs[3]["block"]["content"]

    # Bare React element: trusted residual string segment, surrounded by
    # blank lines (same as ChatMessage's derivation), never island-wrapped.
    residual = msgs[2]
    assert residual["trusted"] is True
    assert residual["segment_start"] is True
    assert "shiny-tool-result" in residual["content"]
    assert residual["content"].startswith("\n\n")
    assert residual["content"].endswith("\n\n")
    assert "<shiny-chat-raw-html>" not in residual["content"]


def test_stream_block_message_carries_session_processed_deps():
    """Island dependencies are serialized through session._process_ui and
    ride the block (not the message envelope)."""
    mock = _CaptureSession()
    dep = HTMLDependency(
        "testlib", "1.0", source={"href": "/test"}, script={"src": "test.js"}
    )
    with session_context(cast(Session, mock)):
        ms = MarkdownStream(id="stream")
        run_stream(ms, [TagList(div("x"), dep)])

    msgs = content_messages(mock.messages)
    block_msg = msgs[1]
    assert block_msg["html_deps"] == []
    block_deps = block_msg["block"].get("html_deps")
    assert block_deps is not None
    assert block_deps[0]["name"] == "testlib"
    # Session-processed (route-registered / lib_prefix applied by the real
    # session; the mock marks processing instead).
    assert block_deps[0].get("from_session") == "capture-session"


def test_stream_result_includes_island_html():
    """The stream result string accumulates untrusted text, island HTML,
    and residual markup alike."""
    mock = _CaptureSession()
    with session_context(cast(Session, mock)):
        ms = MarkdownStream(id="stream")
        result = run_stream(ms, ["model text ", div("trusted UI")])

    assert "model text " in result
    assert "<div>trusted UI</div>" in result


def test_stream_untrusted_content_unchanged():
    """Plain string streams keep the exact pre-block wire shape (no block
    key, content present, append with segment_start=False)."""
    mock = _CaptureSession()
    with session_context(cast(Session, mock)):
        ms = MarkdownStream(id="stream")
        run_stream(ms, ["hello ", "world"])

    msgs = content_messages(mock.messages)[1:]  # drop the leading clear
    assert msgs == [
        {
            "id": "stream",
            "content": "hello ",
            "operation": "append",
            "html_deps": [],
            "trusted": False,
            "segment_start": False,
        },
        {
            "id": "stream",
            "content": "world",
            "operation": "append",
            "html_deps": [],
            "trusted": False,
            "segment_start": False,
        },
    ]


# ---------------------------------------------------------------------------
# output_markdown_stream() initial content-segments
# ---------------------------------------------------------------------------


def test_output_emits_block_entries_for_island_content():
    el = output_markdown_stream(
        "stream",
        content=TagList("## This is markdown", div("This is HTML")),
    )
    segments = json.loads(str(el.attrs["content-segments"]))

    assert segments[0] == {"text": "## This is markdown", "trusted": False}
    # Trusted UI ships as a structured html_block entry, not an island-tag
    # string segment (kata#mhyd).
    assert segments[1] == {
        "block": {
            "type": "html_block",
            "version": 1,
            "content": "<div>This is HTML</div>",
        }
    }
    # The fallback content attribute carries the island HTML too, so a
    # client that fails closed on the provenance array (or predates block
    # entries) still shows it — escaped and untrusted.
    assert "<div>This is HTML</div>" in str(el.attrs["content"])
    assert el.attrs["content-trusted"] == "false"


def test_output_block_entry_carries_serialized_deps():
    """Block-level deps ride the block entry as serialized dicts AND the
    element's dependencies (page-level, registered at render)."""
    dep = HTMLDependency(
        "testlib", "1.0", source={"href": "/test"}, script={"src": "test.js"}
    )
    el = output_markdown_stream("stream", content=TagList(div("x"), dep))
    segments = json.loads(str(el.attrs["content-segments"]))

    block_deps = segments[0]["block"].get("html_deps")
    assert block_deps is not None
    assert block_deps[0]["name"] == "testlib"
    rendered = TagList(el).render()
    assert any(d.name == "testlib" for d in rendered["dependencies"])


def test_output_react_element_stays_trusted_text_segment():
    """Bare data-shinychat-react elements remain trusted residual string
    segments (blank-line wrapped); surrounding UI becomes block entries."""
    react_el = Tag(
        "shiny-tool-result", data_shinychat_react=True, request_id="abc"
    )
    el = output_markdown_stream(
        "stream",
        content=TagList(div("before"), react_el, div("after")),
    )
    segments = json.loads(str(el.attrs["content-segments"]))

    assert len(segments) == 3
    assert segments[0]["block"]["type"] == "html_block"
    assert "<div>before</div>" in segments[0]["block"]["content"]
    assert segments[1]["trusted"] is True
    assert "shiny-tool-result" in segments[1]["text"]
    assert segments[1]["text"].startswith("\n\n")
    assert segments[2]["block"]["type"] == "html_block"
    assert "<div>after</div>" in segments[2]["block"]["content"]


def test_output_single_react_element_keeps_trusted_fallback():
    """A lone residual text segment (no blocks) keeps content-trusted=true:
    the fallback content is exactly the trusted server-authored HTML."""
    react_el = Tag(
        "shiny-tool-result", data_shinychat_react=True, request_id="abc"
    )
    el = output_markdown_stream("stream", content=react_el)
    segments = json.loads(str(el.attrs["content-segments"]))

    assert len(segments) == 1
    assert segments[0]["trusted"] is True
    assert el.attrs["content-trusted"] == "true"
