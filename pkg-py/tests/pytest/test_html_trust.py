from __future__ import annotations

import asyncio
import threading
from typing import Any, cast

import pytest
from htmltools import HTML
from shiny import Inputs, Session
from shiny.module import ResolvedId
from shinychat._html_trust import (
    is_trusted_html,
    record_sent_action,
    trusted_html_deps,
)
from shinychat._input_handler import messages_input_value

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


class _MockSession:
    ns: ResolvedId = ResolvedId("")
    app: object = None
    id: str = "mock-session"
    input: Any

    def __init__(self) -> None:
        self.input = Inputs({}, ns=ResolvedId)

    def on_ended(self, callback: object) -> None:
        pass

    def on_destroy(self, callback: object) -> None:
        pass

    def _increment_busy_count(self) -> None:
        pass

    async def send_custom_message(self, type: str, message: Any) -> None:
        pass


def new_session() -> Session:
    return cast(Session, _MockSession())


def run_async(coro_fn: Any) -> None:
    exc: list[BaseException] = []

    def _run() -> None:
        try:
            asyncio.run(coro_fn())
        except BaseException as err:  # noqa: BLE001
            exc.append(err)

    t = threading.Thread(target=_run)
    t.start()
    t.join()
    if exc:
        raise exc[0]


def seg(content: str, content_type: str = "html") -> dict[str, Any]:
    return {"content": content, "content_type": content_type}


def send_message(
    session: Session, *segments: dict[str, Any], id: str = "chat"
) -> None:
    record_sent_action(
        session,
        id,
        cast(
            Any,
            {
                "type": "message",
                "message": {"role": "assistant", "segments": list(segments)},
            },
        ),
    )


def send_chunk_start(
    session: Session, *segments: dict[str, Any], id: str = "chat"
) -> None:
    record_sent_action(
        session,
        id,
        cast(
            Any,
            {
                "type": "chunk_start",
                "message": {"role": "assistant", "segments": list(segments)},
            },
        ),
    )


def send_chunk(
    session: Session,
    content: str,
    content_type: str | None = "html",
    operation: str = "append",
    id: str = "chat",
) -> None:
    action: dict[str, Any] = {
        "type": "chunk",
        "content": content,
        "operation": operation,
    }
    if content_type is not None:
        action["content_type"] = content_type
    record_sent_action(session, id, cast(Any, action))


def send_chunk_end(session: Session, id: str = "chat") -> None:
    record_sent_action(session, id, cast(Any, {"type": "chunk_end"}))


def reported_html(*segments: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"role": "assistant", "segments": list(segments)}]


# ----------------------------------------------------------------------
# The ledger
# ----------------------------------------------------------------------


def test_nothing_is_trusted_before_the_server_sends_anything():
    assert not is_trusted_html(new_session(), "<div>a</div>")


def test_one_shot_html_message_is_trusted():
    session = new_session()
    send_message(session, seg("<div>a</div>"))
    assert is_trusted_html(session, "<div>a</div>")
    assert not is_trusted_html(session, "<div>b</div>")


def test_each_segment_of_a_multi_segment_message_is_trusted_on_its_own():
    session = new_session()
    send_message(session, seg("<div>a</div>"), seg("<div>b</div>"))
    assert is_trusted_html(session, "<div>a</div>")
    assert is_trusted_html(session, "<div>b</div>")
    # The client never merges across segments of one payload, so the
    # concatenation must not become trusted.
    assert not is_trusted_html(session, "<div>a</div><div>b</div>")


def test_streamed_html_is_trusted_as_the_client_merges_it():
    session = new_session()
    send_chunk_start(session, seg("A"))
    send_chunk(session, "B")
    send_chunk(session, "C")
    send_chunk_end(session)
    assert is_trusted_html(session, "ABC")
    assert not is_trusted_html(session, "AC")


def test_a_stream_in_flight_has_nothing_to_trust_yet():
    # The browser reports only settled messages -- buildMessagesSnapshot() drops
    # anything still streaming -- so the intermediate prefixes of a stream are
    # never reported back and must not be trusted just because we sent them.
    session = new_session()
    send_chunk_start(session, seg("A"))
    send_chunk(session, "B")
    assert not is_trusted_html(session, "A")
    assert not is_trusted_html(session, "AB")

    send_chunk_end(session)
    assert is_trusted_html(session, "AB")


def test_a_chunk_of_another_content_type_starts_a_new_segment():
    session = new_session()
    send_chunk_start(session, seg("A"))
    send_chunk(session, "text", content_type="markdown")
    send_chunk(session, "B")
    send_chunk_end(session)
    assert is_trusted_html(session, "A")
    assert is_trusted_html(session, "B")
    assert not is_trusted_html(session, "AB")


def test_a_chunk_without_a_content_type_continues_the_one_in_progress():
    session = new_session()
    send_chunk_start(session, seg("A"))
    send_chunk(session, "B", content_type=None)
    send_chunk_end(session)
    assert is_trusted_html(session, "AB")


def test_replace_restarts_the_accumulation():
    session = new_session()
    send_chunk_start(session, seg("A"))
    send_chunk(session, "B", operation="replace")
    send_chunk(session, "C")
    send_chunk_end(session)
    assert is_trusted_html(session, "BC")
    assert not is_trusted_html(session, "A")
    assert not is_trusted_html(session, "ABC")


def test_an_unrelated_action_between_chunks_does_not_split_the_merge():
    session = new_session()
    send_chunk_start(session, seg("A"))
    record_sent_action(session, "chat", cast(Any, {"type": "clear"}))
    send_chunk(session, "B")
    send_chunk_end(session)
    assert is_trusted_html(session, "AB")


def test_a_chunk_with_no_stream_open_displays_nothing_to_trust():
    # The client's `chunk` reducer bails when there is no streaming message, so
    # neither should the ledger invent one.
    session = new_session()
    send_chunk(session, "orphan")
    send_chunk_end(session)
    assert not is_trusted_html(session, "orphan")


def test_streams_from_concurrent_chats_do_not_interleave():
    session = new_session()
    send_chunk_start(session, seg("A1"), id="one")
    send_chunk_start(session, seg("B1"), id="two")
    send_chunk(session, "A2", id="one")
    send_chunk(session, "B2", id="two")
    send_chunk_end(session, id="one")
    send_chunk_end(session, id="two")
    assert is_trusted_html(session, "A1A2")
    assert is_trusted_html(session, "B1B2")
    assert not is_trusted_html(session, "A1B1")
    assert not is_trusted_html(session, "A1B2")


def test_trust_is_not_consumed_by_a_first_lookup():
    session = new_session()
    send_message(session, seg("<div>a</div>"))
    assert is_trusted_html(session, "<div>a</div>")
    assert is_trusted_html(session, "<div>a</div>")


def test_non_html_segments_never_enter_the_ledger():
    session = new_session()
    send_message(session, seg("plain", content_type="markdown"))
    assert not is_trusted_html(session, "plain")
    assert not is_trusted_html(None, "plain")


def test_non_string_content_is_never_trusted():
    # A forged report can claim content_type "html" for a non-string value;
    # that must degrade to untrusted, not raise out of hash_content().
    session = new_session()
    send_message(session, seg("<div>a</div>"))
    assert not is_trusted_html(session, 42)
    assert not is_trusted_html(session, None)
    assert not is_trusted_html(session, ["<div>a</div>"])


def test_ledgers_do_not_leak_between_sessions():
    author = new_session()
    other = new_session()
    send_message(author, seg("<div>a</div>"))
    assert is_trusted_html(author, "<div>a</div>")
    assert not is_trusted_html(other, "<div>a</div>")


# ----------------------------------------------------------------------
# The input handler
# ----------------------------------------------------------------------


def test_html_the_server_never_sent_degrades_to_markdown():
    session = new_session()
    with pytest.warns(UserWarning, match="did not send"):
        out = messages_input_value(
            reported_html(seg("<img src=x onerror=alert(1)>")), session
        )
    assert out[0].segments[0].content_type == "markdown"
    # The content is preserved -- it just renders as literal text now.
    assert out[0].segments[0].content == "<img src=x onerror=alert(1)>"


def test_html_the_server_sent_survives_unchanged():
    session = new_session()
    send_message(session, seg("<div>ok</div>"))
    out = messages_input_value(reported_html(seg("<div>ok</div>")), session)
    assert out[0].segments[0].content_type == "html"


def test_only_the_untrusted_segment_degrades():
    session = new_session()
    send_message(session, seg("<div>ok</div>"))
    with pytest.warns(UserWarning, match="did not send"):
        out = messages_input_value(
            [
                {
                    "role": "assistant",
                    "segments": [
                        seg("<div>ok</div>"),
                        seg("<div>forged</div>"),
                        seg("some *markdown*", content_type="markdown"),
                    ],
                },
                {"role": "user", "segments": [seg("hi", "markdown")]},
            ],
            session,
        )
    assert [s.content_type for s in out[0].segments] == [
        "html",
        "markdown",
        "markdown",
    ]
    assert out[1].segments[0].content == "hi"


def test_a_merged_streamed_html_segment_survives():
    session = new_session()
    send_chunk_start(session, seg("<div>a</div>"))
    send_chunk(session, "<div>b</div>")
    send_chunk_end(session)
    out = messages_input_value(
        reported_html(seg("<div>a</div><div>b</div>")), session
    )
    assert out[0].segments[0].content_type == "html"


def test_one_warning_covers_a_whole_forged_transcript():
    session = new_session()
    with pytest.warns(UserWarning) as record:
        messages_input_value(
            reported_html(seg("<div>1</div>"), seg("<div>2</div>")), session
        )
    assert len(record) == 1
    assert "2 reported chat segment(s)" in str(record[0].message)


def test_no_session_means_no_trusted_html():
    with pytest.warns(UserWarning, match="did not send"):
        out = messages_input_value(reported_html(seg("<div>a</div>")), None)
    assert out[0].segments[0].content_type == "markdown"


# ----------------------------------------------------------------------
# html dependencies
# ----------------------------------------------------------------------


def test_reported_dependencies_are_replaced_by_the_servers_own_copies():
    session = new_session()
    real = {"name": "widget", "version": "1.0", "script": [{"src": "real.js"}]}
    record_sent_action(
        session,
        "chat",
        cast(
            Any,
            {
                "type": "message",
                "message": {"role": "assistant", "segments": []},
            },
        ),
        [real],
    )

    forged = {
        "name": "widget",
        "version": "1.0",
        "script": [{"src": "evil.js"}],
    }
    out = messages_input_value(
        [
            {
                "role": "assistant",
                "segments": [seg("hi", "markdown")],
                "htmlDeps": [forged],
            }
        ],
        session,
    )
    assert out[0].segments[0].html_deps == [real]


def test_dependencies_the_server_never_sent_are_dropped():
    session = new_session()
    out = messages_input_value(
        [
            {
                "role": "assistant",
                "segments": [seg("hi", "markdown")],
                "htmlDeps": [{"name": "evil", "version": "1.0"}],
            }
        ],
        session,
    )
    assert out[0].segments[0].html_deps is None


def test_trusted_html_deps_guards_missing_inputs():
    session = new_session()
    assert trusted_html_deps(session, None) is None
    assert trusted_html_deps(session, []) is None
    assert trusted_html_deps(None, [{"name": "w", "version": "1.0"}]) is None


def test_malformed_dep_entries_are_ignored_not_raised():
    # A forged htmlDeps entry need not even be a dict.
    session = new_session()
    real = {"name": "widget", "version": "1.0", "script": [{"src": "real.js"}]}
    record_sent_action(
        session,
        "chat",
        cast(
            Any,
            {"type": "message", "message": {"role": "assistant", "segments": []}},
        ),
        [real],
    )
    out = messages_input_value(
        [
            {
                "role": "assistant",
                "segments": [seg("hi", "markdown")],
                "htmlDeps": ["not-a-dict", 42, None, real],
            }
        ],
        session,
    )
    assert out[0].segments[0].html_deps == [real]


# ----------------------------------------------------------------------
# End to end: a real append must not have its own html rejected
# ----------------------------------------------------------------------


def test_a_real_html_append_survives_the_round_trip():
    # The ledger is only useful if it agrees with what the client will report
    # back for genuine server output. Drive the actual send path, then feed the
    # wire content back through the handler the way the browser would.
    from shiny.session import session_context
    from shinychat import Chat

    session = new_session()
    sent: list[dict[str, Any]] = []
    real_send = None

    with session_context(session):
        chat = Chat(id="chat_html_roundtrip")

        real_send = chat._send_action

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)
            await real_send(action, deps)

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _exercise() -> None:
            await chat.append_message(HTML("<div class='card'>hello</div>"))

        run_async(_exercise)

    wire = [a for a in sent if a["type"] == "message"][0]["message"]
    reported = [{"role": wire["role"], "segments": wire["segments"]}]

    out = messages_input_value(reported, session)
    assert [s.content_type for s in out[0].segments] == ["html"]
