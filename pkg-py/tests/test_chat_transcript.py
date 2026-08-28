from __future__ import annotations

import anyio
import pytest
from shinychat._chat_transcript import ChatTranscript, TranscriptEntry
from shinychat._chat_types import ChatMessage, ContentSegment, StoredMessage


def entry(
    role: str, content: str, *, icon: str | None = None
) -> TranscriptEntry:
    return TranscriptEntry(
        message=StoredMessage.from_chat_message(
            ChatMessage(content=content, role=role)  # type: ignore[arg-type]
        ),
        icon=icon,
    )


async def sent() -> bool:
    return True


async def sent_action() -> None:
    return None


def segment(content: str, content_type: str = "markdown") -> ContentSegment:
    return ContentSegment(
        content=content,
        content_type=content_type,  # type: ignore[arg-type]
    )


async def start_stream(
    transcript: ChatTranscript,
    *,
    stream_id: str = "stream",
    owner_task: object | None = None,
) -> None:
    await transcript.start_stream(
        stream_id=stream_id,
        entry=entry("assistant", ""),
        owner_task=owner_task,
        exchange_id=transcript.open_exchange_id,
        send=sent,
    )


@pytest.mark.anyio
async def test_read_returns_a_defensive_copy() -> None:
    transcript = ChatTranscript()
    await transcript.append(
        entry("user", "hello", icon="<i>user</i>"),
        exchange_id=transcript.open_exchange_id,
        send=sent,
    )

    projection = transcript.read()
    projection[0].message.segments[0].content = "mutated"
    projection[0].icon = "mutated"

    committed = transcript.read()[0]
    assert committed.message.content == "hello"
    assert committed.icon == "<i>user</i>"


@pytest.mark.anyio
async def test_append_sends_before_committing() -> None:
    transcript = ChatTranscript()
    sent_message = entry("assistant", "hello")
    events: list[tuple[str, int]] = []

    async def send() -> bool:
        events.append(("send", len(transcript.read())))
        return True

    await transcript.append(
        sent_message,
        exchange_id=transcript.open_exchange_id,
        send=send,
    )
    events.append(("commit", len(transcript.read())))

    assert events == [("send", 0), ("commit", 1)]


@pytest.mark.anyio
async def test_capture_events_are_awaited_after_their_commits() -> None:
    events: list[tuple[str, str, int]] = []

    async def accepted_input(exchange_id: str, message: StoredMessage) -> None:
        events.append(("input", exchange_id, len(transcript.read())))
        assert message.content == "question"

    async def message_committed(
        exchange_id: str | None, message: TranscriptEntry
    ) -> None:
        events.append(("message", exchange_id or "", len(transcript.read())))
        assert message.message.content == "answer"

    transcript = ChatTranscript(
        on_accepted_input=accepted_input,
        on_message_committed=message_committed,
    )
    exchange_id = await transcript.record_accepted_input_and_notify(
        entry("user", "question").message
    )
    await transcript.append(
        entry("assistant", "answer"),
        exchange_id=exchange_id,
        send=sent,
    )

    assert events == [
        ("input", exchange_id, 1),
        ("message", exchange_id, 2),
    ]


@pytest.mark.anyio
async def test_stream_capture_events_follow_successful_stream_commits() -> None:
    events: list[tuple[str, str, str]] = []

    async def stream_started(
        stream_id: str, exchange_id: str | None, message: TranscriptEntry
    ) -> None:
        events.append(("start", stream_id, message.message.content))
        assert exchange_id == transcript.open_exchange_id
        assert len(transcript.read()) == 1

    async def stream_updated(stream_id: str, message: TranscriptEntry) -> None:
        events.append(("update", stream_id, message.message.content))
        assert len(transcript.read()) == 1

    async def stream_finished(
        stream_id: str, status: str, error: str | None
    ) -> None:
        events.append((status, stream_id, error or ""))
        assert transcript.active_stream_id is None

    transcript = ChatTranscript(
        on_stream_started=stream_started,
        on_stream_updated=stream_updated,
        on_stream_finished=stream_finished,
    )
    await start_stream(transcript)
    await transcript.transition_stream(
        stream_id="stream",
        source_segments=[segment("partial")],
        message=entry("assistant", "partial").message,
        operation="append",
        send=sent,
    )
    await transcript.end_stream(
        stream_id="stream",
        status=None,
        error=None,
        send=sent,
    )

    assert events == [
        ("start", "stream", ""),
        ("update", "stream", "partial"),
        ("ok", "stream", ""),
    ]


@pytest.mark.anyio
async def test_failed_stream_transport_emits_no_start_or_update_capture_event() -> (
    None
):
    events: list[str] = []

    async def stream_started(
        _stream_id: str, _exchange_id: str | None, _message: TranscriptEntry
    ) -> None:
        events.append("start")

    async def stream_updated(
        _stream_id: str, _message: TranscriptEntry
    ) -> None:
        events.append("update")

    async def unsent() -> bool:
        return False

    transcript = ChatTranscript(
        on_stream_started=stream_started,
        on_stream_updated=stream_updated,
    )
    assert not await transcript.start_stream(
        stream_id="stream",
        entry=entry("assistant", ""),
        owner_task=None,
        exchange_id=None,
        send=unsent,
    )
    assert events == []

    await start_stream(transcript)
    assert not await transcript.transition_stream(
        stream_id="stream",
        source_segments=[segment("unsent")],
        message=entry("assistant", "unsent").message,
        operation="append",
        send=unsent,
    )
    assert events == ["start"]


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["normal", "failed", "abort"])
async def test_stream_terminal_callback_runs_when_persistence_fails(
    path: str,
) -> None:
    terminal: list[None] = []

    async def fail_finished(
        _stream_id: str, _status: str, _error: str | None
    ) -> None:
        raise RuntimeError("persistence failed")

    transcript = ChatTranscript(
        on_stream_terminal=lambda: terminal.append(None),
        on_stream_finished=fail_finished,
    )
    await start_stream(transcript)

    async def unsent() -> bool:
        return False

    with pytest.raises(RuntimeError, match="persistence failed"):
        if path == "normal":
            await transcript.end_stream(
                stream_id="stream",
                status=None,
                error=None,
                send=sent,
            )
        elif path == "failed":
            await transcript.end_stream(
                stream_id="stream",
                status=None,
                error=None,
                send=unsent,
            )
        else:
            await transcript.abort_stream("stream", status="error")

    assert terminal == [None]
    assert transcript.active_stream_id is None


@pytest.mark.anyio
async def test_transport_failure_emits_no_message_capture_event() -> None:
    captured: list[TranscriptEntry] = []

    async def message_committed(
        _exchange_id: str | None, message: TranscriptEntry
    ) -> None:
        captured.append(message)

    transcript = ChatTranscript(on_message_committed=message_committed)

    async def unsent() -> bool:
        return False

    assert not await transcript.append(
        entry("assistant", "not sent"),
        exchange_id=None,
        send=unsent,
    )
    assert captured == []


@pytest.mark.anyio
async def test_append_commits_the_pre_send_snapshot() -> None:
    transcript = ChatTranscript()
    source = entry("assistant", "prepared", icon="<i>prepared</i>")
    send_started = anyio.Event()
    release_send = anyio.Event()

    async def send() -> bool:
        send_started.set()
        await release_send.wait()
        return True

    async def append() -> None:
        await transcript.append(
            source,
            exchange_id=transcript.open_exchange_id,
            send=send,
        )

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(append)
        await send_started.wait()
        source.message.segments[0].content = "mutated"
        source.icon = "<i>mutated</i>"
        release_send.set()

    committed = transcript.read()[0]
    assert committed.message.content == "prepared"
    assert committed.icon == "<i>prepared</i>"


@pytest.mark.anyio
async def test_complete_append_captures_exchange_before_awaiting_send() -> None:
    transcript = ChatTranscript()
    opening_exchange = transcript.record_accepted_input(
        entry("user", "first").message
    )
    send_started = anyio.Event()
    release_send = anyio.Event()

    async def send() -> bool:
        send_started.set()
        await release_send.wait()
        return True

    async def append_response() -> None:
        await transcript.append(
            entry("assistant", "first response"),
            exchange_id=opening_exchange,
            send=send,
        )

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(append_response)
        await send_started.wait()
        transcript.record_accepted_input(entry("user", "second").message)
        release_send.set()

    assert transcript.read()[2].exchange_id == opening_exchange


@pytest.mark.anyio
async def test_failed_send_leaves_committed_messages_unchanged() -> None:
    transcript = ChatTranscript()
    await transcript.append(
        entry("user", "kept"),
        exchange_id=transcript.open_exchange_id,
        send=sent,
    )

    async def fail() -> bool:
        raise RuntimeError("send failed")

    with pytest.raises(RuntimeError, match="send failed"):
        await transcript.append(
            entry("assistant", "discarded"),
            exchange_id=transcript.open_exchange_id,
            send=fail,
        )

    assert [item.message.content for item in transcript.read()] == ["kept"]


@pytest.mark.anyio
async def test_unsent_message_does_not_commit() -> None:
    transcript = ChatTranscript()

    async def unsent() -> bool:
        return False

    assert not await transcript.append(
        entry("system", "hidden"),
        exchange_id=transcript.open_exchange_id,
        send=unsent,
    )
    assert transcript.read() == ()


@pytest.mark.anyio
async def test_mutations_notify_change() -> None:
    changes: list[None] = []
    transcript = ChatTranscript(on_change=lambda: changes.append(None))

    transcript.record_accepted_input(entry("user", "first").message)
    await transcript.append(
        entry("assistant", "reply"),
        exchange_id=transcript.open_exchange_id,
        send=sent,
    )
    await transcript.clear(send=sent_action)
    transcript.replace([entry("assistant", "restored")])

    assert changes == [None, None, None, None]
    assert [item.message.content for item in transcript.read()] == ["restored"]


def test_accepted_input_opens_a_new_opaque_exchange() -> None:
    transcript = ChatTranscript()

    first = transcript.record_accepted_input(entry("user", "first").message)
    second = transcript.record_accepted_input(entry("user", "second").message)

    assert first != second
    assert transcript.open_exchange_id == second
    assert [item.message.content for item in transcript.read()] == [
        "first",
        "second",
    ]
    assert [item.exchange_id for item in transcript.read()] == [first, second]


@pytest.mark.anyio
async def test_stream_transitions_commit_only_after_their_send() -> None:
    transcript = ChatTranscript()
    await start_stream(transcript)

    async def fail() -> bool:
        raise RuntimeError("chunk failed")

    with pytest.raises(RuntimeError, match="chunk failed"):
        await transcript.transition_stream(
            stream_id="stream",
            source_segments=[segment("discarded")],
            message=entry("assistant", "discarded").message,
            operation="append",
            send=fail,
        )

    assert transcript.stream_segments("stream") == []
    assert transcript.read()[0].message.content == ""


@pytest.mark.anyio
async def test_stream_start_reserves_admission_before_awaiting_send() -> None:
    transcript = ChatTranscript()
    send_started = anyio.Event()
    release_send = anyio.Event()

    async def blocked_send() -> bool:
        send_started.set()
        await release_send.wait()
        return True

    async def start_first_stream() -> None:
        await transcript.start_stream(
            stream_id="first",
            entry=entry("assistant", ""),
            owner_task=None,
            exchange_id=transcript.open_exchange_id,
            send=blocked_send,
        )

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(start_first_stream)
        await send_started.wait()
        with pytest.raises(RuntimeError, match="second message stream"):
            await start_stream(transcript, stream_id="second")
        release_send.set()

    assert transcript.active_stream_id == "first"


@pytest.mark.anyio
async def test_failed_stream_start_rolls_back_its_reservation() -> None:
    transcript = ChatTranscript()

    async def fail() -> bool:
        raise RuntimeError("start failed")

    with pytest.raises(RuntimeError, match="start failed"):
        await transcript.start_stream(
            stream_id="failed",
            entry=entry("assistant", ""),
            owner_task=None,
            exchange_id=transcript.open_exchange_id,
            send=fail,
        )

    assert transcript.active_stream_id is None
    await start_stream(transcript, stream_id="next")


@pytest.mark.anyio
async def test_failed_stream_transition_releases_its_admission() -> None:
    transcript = ChatTranscript()
    await start_stream(transcript)

    async def unsent() -> bool:
        return False

    assert not await transcript.transition_stream(
        stream_id="stream",
        source_segments=[segment("discarded")],
        message=entry("assistant", "discarded").message,
        operation="append",
        send=unsent,
    )
    await transcript.transition_stream(
        stream_id="stream",
        source_segments=[segment("kept")],
        message=entry("assistant", "kept").message,
        operation="append",
        send=sent,
    )

    assert transcript.read()[0].message.content == "kept"


@pytest.mark.anyio
async def test_blocked_complete_append_rejects_stream_start_immediately() -> (
    None
):
    transcript = ChatTranscript()
    send_started = anyio.Event()
    release_send = anyio.Event()

    async def blocked_send() -> bool:
        send_started.set()
        await release_send.wait()
        return True

    async def append_message() -> None:
        await transcript.append(
            entry("assistant", "complete"),
            exchange_id=transcript.open_exchange_id,
            send=blocked_send,
        )

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(append_message)
        await send_started.wait()
        with pytest.raises(RuntimeError, match="another transcript operation"):
            await start_stream(transcript)
        release_send.set()

    await start_stream(transcript)


@pytest.mark.anyio
async def test_blocked_clear_rejects_stream_start_and_replace_immediately() -> (
    None
):
    transcript = ChatTranscript()
    send_started = anyio.Event()
    release_send = anyio.Event()

    async def blocked_send() -> None:
        send_started.set()
        await release_send.wait()

    async def clear() -> None:
        await transcript.clear(send=blocked_send)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(clear)
        await send_started.wait()
        with pytest.raises(RuntimeError, match="another transcript operation"):
            await start_stream(transcript)
        with pytest.raises(RuntimeError, match="another transcript operation"):
            transcript.replace([entry("assistant", "restored")])
        release_send.set()

    await start_stream(transcript)


@pytest.mark.anyio
async def test_clear_preserves_input_accepted_while_transport_is_pending() -> (
    None
):
    transcript = ChatTranscript()
    await transcript.append(
        entry("assistant", "cleared"),
        exchange_id=transcript.open_exchange_id,
        send=sent,
    )
    send_started = anyio.Event()
    release_send = anyio.Event()
    accepted_exchanges: list[str] = []

    async def blocked_send() -> None:
        send_started.set()
        await release_send.wait()

    async def clear() -> None:
        await transcript.clear(send=blocked_send)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(clear)
        await send_started.wait()
        accepted_exchanges.append(
            transcript.record_accepted_input(entry("user", "accepted").message)
        )
        release_send.set()

    assert [item.message.content for item in transcript.read()] == ["accepted"]
    assert transcript.open_exchange_id == accepted_exchanges[0]


@pytest.mark.anyio
async def test_cancelled_complete_append_releases_its_admission() -> None:
    transcript = ChatTranscript()
    send_started = anyio.Event()

    async def blocked_send() -> bool:
        send_started.set()
        await anyio.sleep_forever()
        return False

    async def append_message() -> None:
        await transcript.append(
            entry("assistant", "cancelled"),
            exchange_id=transcript.open_exchange_id,
            send=blocked_send,
        )

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(append_message)
        await send_started.wait()
        task_group.cancel_scope.cancel()

    await start_stream(transcript)


@pytest.mark.anyio
async def test_stream_replacement_commits_mixed_segments_and_nested_checkpoint() -> (
    None
):
    transcript = ChatTranscript()
    await start_stream(transcript)
    await transcript.transition_stream(
        stream_id="stream",
        source_segments=[segment("reasoning", "thinking")],
        message=entry("assistant", "reasoning").message,
        operation="append",
        send=sent,
    )
    transcript.set_stream_checkpoint(
        "stream", [segment("reasoning", "thinking")]
    )
    await transcript.transition_stream(
        stream_id="stream",
        source_segments=[
            segment("reasoning", "thinking"),
            segment("answer"),
        ],
        message=entry("assistant", "reasoninganswer").message,
        operation="replace",
        send=sent,
    )

    committed = transcript.read()[0]
    assert [
        (segment.content, segment.content_type)
        for segment in transcript.stream_segments("stream")
    ] == [("reasoning", "thinking"), ("answer", "markdown")]
    assert committed.message.content == "reasoninganswer"


@pytest.mark.anyio
async def test_stream_replacement_merges_serialized_dependencies() -> None:
    transcript = ChatTranscript()
    await start_stream(transcript)
    await transcript.transition_stream(
        stream_id="stream",
        source_segments=[segment("first")],
        message=StoredMessage.model_validate(
            {
                "role": "assistant",
                "segments": [
                    {
                        "content": "first",
                        "content_type": "markdown",
                        "html_deps": [{"name": "first"}],
                    }
                ],
            }
        ),
        operation="append",
        send=sent,
    )
    await transcript.transition_stream(
        stream_id="stream",
        source_segments=[segment("replacement")],
        message=StoredMessage.model_validate(
            {
                "role": "assistant",
                "segments": [
                    {
                        "content": "replacement",
                        "content_type": "markdown",
                        "html_deps": [{"name": "second"}],
                    }
                ],
            }
        ),
        operation="replace",
        send=sent,
    )

    assert transcript.read()[0].message.html_deps == [
        {"name": "first"},
        {"name": "second"},
    ]


@pytest.mark.anyio
async def test_stream_abort_preserves_sent_partial_and_error_status() -> None:
    transcript = ChatTranscript()
    await start_stream(transcript)
    await transcript.transition_stream(
        stream_id="stream",
        source_segments=[segment("kept")],
        message=entry("assistant", "kept").message,
        operation="append",
        send=sent,
    )

    await transcript.abort_stream(
        "stream", status="error", error="terminal send failed"
    )

    committed = transcript.read()[0]
    assert committed.message.content == "kept"
    assert committed.status == "error"
    assert committed.error == {"message": "terminal send failed"}
    assert transcript.active_stream_id is None


@pytest.mark.anyio
async def test_unsent_stream_end_closes_with_error_status() -> None:
    transcript = ChatTranscript()
    await start_stream(transcript)
    await transcript.transition_stream(
        stream_id="stream",
        source_segments=[segment("kept")],
        message=entry("assistant", "kept").message,
        operation="append",
        send=sent,
    )

    async def unsent() -> bool:
        return False

    assert not await transcript.end_stream(
        stream_id="stream",
        status=None,
        error=None,
        send=unsent,
    )

    committed = transcript.read()[0]
    assert committed.message.content == "kept"
    assert committed.status == "error"
    assert committed.error == {"message": "Could not send message stream end."}
    assert transcript.active_stream_id is None


@pytest.mark.anyio
async def test_stream_captures_its_opening_exchange_after_new_input() -> None:
    transcript = ChatTranscript()
    old_exchange = transcript.record_accepted_input(
        entry("user", "old").message
    )
    await start_stream(transcript)
    transcript.record_accepted_input(entry("user", "new").message)
    await transcript.end_stream(
        stream_id="stream",
        source_segments=[segment("old response")],
        message=entry("assistant", "old response").message,
        operation="append",
        status=None,
        error=None,
        send=sent,
    )

    assert transcript.read()[1].exchange_id == old_exchange
    assert transcript.open_exchange_id != old_exchange


@pytest.mark.anyio
async def test_active_stream_rejects_complete_append_and_second_start() -> None:
    transcript = ChatTranscript()
    await start_stream(transcript)

    with pytest.raises(
        RuntimeError, match="complete message.*stream is active"
    ):
        await transcript.append(
            entry("assistant", "blocked"),
            exchange_id=transcript.open_exchange_id,
            send=sent,
        )
    with pytest.raises(RuntimeError, match="second message stream"):
        await start_stream(transcript, stream_id="other")


@pytest.mark.anyio
async def test_clear_and_restore_reject_active_stream_and_defensive_projection() -> (
    None
):
    transcript = ChatTranscript()
    await start_stream(transcript)
    projection = transcript.read()
    projection[0].message.segments[0].content = "mutated"

    with pytest.raises(RuntimeError, match="clear or restore"):
        await transcript.clear(send=sent_action)
    with pytest.raises(RuntimeError, match="clear or restore"):
        transcript.replace([entry("assistant", "restored")])

    assert transcript.read()[0].message.content == ""
    await transcript.end_stream(
        stream_id="stream",
        status=None,
        error=None,
        send=sent,
    )
    await transcript.clear(send=sent_action)

    assert transcript.read() == ()
    assert transcript.active_stream_id is None
