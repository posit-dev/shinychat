from __future__ import annotations

import pytest
from shinychat._attachments import Attachment
from shinychat._chat_transcript import ChatTranscript, StreamCandidate
from shinychat._chat_types import (
    ChatMessage,
    ContentType,
    Role,
    StoredMessage,
    StoredSegment,
)


@pytest.mark.anyio
async def test_read_returns_a_copy_isolated_from_internal_state() -> None:
    transcript = ChatTranscript()
    await transcript.append(stored_message("user", "hello"), send=noop_send)

    first_read = transcript.read()
    first_read[0].segments[0].content = "mutated"

    assert transcript.read()[0].segments[0].content == "hello"


@pytest.mark.anyio
async def test_append_copies_the_input_message() -> None:
    transcript = ChatTranscript()
    message = stored_message("user", "hello")

    await transcript.append(message, send=noop_send)
    message.segments[0].content = "mutated-after-append"

    assert transcript.read()[0].segments[0].content == "hello"


@pytest.mark.anyio
async def test_append_sends_before_commit() -> None:
    transcript = ChatTranscript()
    events: list[tuple[str, int]] = []

    async def send() -> None:
        events.append(("send", len(transcript.read())))

    await transcript.append(stored_message("user", "hello"), send=send)

    events.append(("commit", len(transcript.read())))
    assert events == [("send", 0), ("commit", 1)]


@pytest.mark.anyio
async def test_failed_send_keeps_prior_state() -> None:
    transcript = ChatTranscript()
    await transcript.append(stored_message("user", "kept"), send=noop_send)

    async def fail() -> None:
        raise RuntimeError("send failed")

    with pytest.raises(RuntimeError, match="send failed"):
        await transcript.append(
            stored_message("assistant", "discarded"),
            send=fail,
        )

    assert [message.content for message in transcript.read()] == ["kept"]


@pytest.mark.anyio
async def test_append_orders_messages_by_call_sequence() -> None:
    transcript = ChatTranscript()
    await transcript.append(stored_message("user", "first"), send=noop_send)
    await transcript.append(
        stored_message("assistant", "second"), send=noop_send
    )

    assert [message.content for message in transcript.read()] == [
        "first",
        "second",
    ]


@pytest.mark.anyio
async def test_start_admits_a_new_stream() -> None:
    transcript = ChatTranscript()
    await transcript.start(
        chat_message("assistant", ""), stream_id="s1", send=noop_send
    )

    assert transcript.is_active("s1")
    assert transcript.active_stream_id == "s1"
    assert transcript.active_segments == ()


@pytest.mark.anyio
async def test_start_rejects_a_competing_stream() -> None:
    transcript = ChatTranscript()
    await transcript.start(
        chat_message("assistant", ""), stream_id="s1", send=noop_send
    )

    with pytest.raises(
        RuntimeError,
        match="Cannot start a stream while another stream is active",
    ):
        await transcript.start(
            chat_message("assistant", ""), stream_id="s2", send=noop_send
        )


@pytest.mark.anyio
async def test_append_rejects_a_complete_message_while_streaming() -> None:
    transcript = ChatTranscript()
    await transcript.start(
        chat_message("assistant", ""), stream_id="s1", send=noop_send
    )

    with pytest.raises(
        RuntimeError,
        match="Cannot append a complete message while a stream is active",
    ):
        await transcript.append(
            stored_message("assistant", "late"), send=noop_send
        )


@pytest.mark.anyio
async def test_chunk_without_an_active_stream_is_invalid() -> None:
    transcript = ChatTranscript()

    with pytest.raises(
        RuntimeError,
        match="Cannot apply a stream chunk without an active stream",
    ):
        await transcript.chunk(
            chat_message("assistant", "bad"),
            stream_id="s1",
            operation="append",
            send=chunk_send,
        )


@pytest.mark.anyio
async def test_chunk_rejects_a_foreign_stream_identity() -> None:
    transcript = ChatTranscript()
    await transcript.start(
        chat_message("assistant", ""), stream_id="s1", send=noop_send
    )

    with pytest.raises(
        RuntimeError, match="Cannot write to a stream that is not active"
    ):
        await transcript.chunk(
            chat_message("assistant", "bad"),
            stream_id="other",
            operation="append",
            send=chunk_send,
        )


@pytest.mark.anyio
async def test_settle_without_an_active_stream_is_invalid() -> None:
    transcript = ChatTranscript()

    with pytest.raises(
        RuntimeError, match="Cannot end a stream without an active stream"
    ):
        await transcript.settle(stream_id="s1", send=settle_send)


@pytest.mark.anyio
async def test_settle_rejects_a_foreign_stream_identity() -> None:
    transcript = ChatTranscript()
    await transcript.start(
        chat_message("assistant", ""), stream_id="s1", send=noop_send
    )

    with pytest.raises(
        RuntimeError, match="Cannot write to a stream that is not active"
    ):
        await transcript.settle(stream_id="other", send=settle_send)


@pytest.mark.anyio
async def test_chunk_appends_and_coalesces_matching_segments() -> None:
    transcript = ChatTranscript()
    await transcript.start(
        chat_message("assistant", ""), stream_id="s1", send=noop_send
    )
    await transcript.chunk(
        chat_message("assistant", "hello"),
        stream_id="s1",
        operation="append",
        send=chunk_send,
    )
    await transcript.chunk(
        chat_message("assistant", " world"),
        stream_id="s1",
        operation="append",
        send=chunk_send,
    )

    assert [segment.content for segment in transcript.active_segments] == [
        "hello world"
    ]


@pytest.mark.anyio
async def test_chunk_replace_resets_to_the_checkpoint() -> None:
    transcript = ChatTranscript()
    await transcript.start(
        chat_message("assistant", ""), stream_id="s1", send=noop_send
    )
    await transcript.chunk(
        chat_message("assistant", "draft"),
        stream_id="s1",
        operation="append",
        send=chunk_send,
    )
    await transcript.chunk(
        chat_message("assistant", "final", content_type="html"),
        stream_id="s1",
        operation="replace",
        send=chunk_send,
    )

    segments = transcript.active_segments
    assert [segment.content for segment in segments] == ["final"]
    assert segments[0].content_type == "html"


@pytest.mark.anyio
async def test_settle_commits_the_returned_message_and_clears_active_state() -> (
    None
):
    transcript = ChatTranscript()
    await transcript.start(
        chat_message("assistant", ""), stream_id="s1", send=noop_send
    )
    await transcript.chunk(
        chat_message("assistant", "hello"),
        stream_id="s1",
        operation="append",
        send=chunk_send,
    )
    await transcript.settle(stream_id="s1", send=settle_send)

    assert [message.content for message in transcript.read()] == ["hello"]
    assert transcript.active_stream_id is None
    assert transcript.active_segments == ()
    assert transcript.active_projection is None
    assert not transcript.is_active("s1")


@pytest.mark.anyio
async def test_settle_sends_before_commit() -> None:
    transcript = ChatTranscript()
    await transcript.start(
        chat_message("assistant", ""), stream_id="s1", send=noop_send
    )
    events: list[tuple[str, int]] = []

    async def send(candidate: StreamCandidate) -> StoredMessage:
        events.append(("send", len(transcript.read())))
        return candidate_to_stored(candidate)

    await transcript.settle(stream_id="s1", send=send)
    events.append(("commit", len(transcript.read())))

    assert events == [("send", 0), ("commit", 1)]


@pytest.mark.anyio
async def test_settle_failure_keeps_the_stream_active_and_prior_state() -> None:
    transcript = ChatTranscript()
    await transcript.append(stored_message("user", "kept"), send=noop_send)
    await transcript.start(
        chat_message("assistant", ""), stream_id="s1", send=noop_send
    )

    async def fail(candidate: StreamCandidate) -> StoredMessage:
        raise RuntimeError("settle failed")

    with pytest.raises(RuntimeError, match="settle failed"):
        await transcript.settle(stream_id="s1", send=fail)

    assert [message.content for message in transcript.read()] == ["kept"]
    assert transcript.is_active("s1")


@pytest.mark.anyio
async def test_abort_clears_the_matching_active_stream() -> None:
    transcript = ChatTranscript()
    await transcript.start(
        chat_message("assistant", ""), stream_id="s1", send=noop_send
    )

    transcript.abort("s1")

    assert not transcript.is_active("s1")
    assert transcript.active_stream_id is None
    assert transcript.active_segments == ()


@pytest.mark.anyio
async def test_abort_is_a_noop_for_a_foreign_stream_identity() -> None:
    transcript = ChatTranscript()
    await transcript.start(
        chat_message("assistant", ""), stream_id="s1", send=noop_send
    )

    transcript.abort("other")

    assert transcript.is_active("s1")


@pytest.mark.anyio
async def test_clear_resets_messages_active_state_and_increments_generation() -> (
    None
):
    transcript = ChatTranscript()
    await transcript.append(stored_message("user", "hi"), send=noop_send)
    await transcript.start(
        chat_message("assistant", ""), stream_id="s1", send=noop_send
    )
    initial_generation = transcript.generation

    await transcript.clear(send=noop_send)

    assert transcript.read() == ()
    assert transcript.active_stream_id is None
    assert transcript.generation == initial_generation + 1


@pytest.mark.anyio
async def test_exit_context_restores_the_previous_checkpoint_within_a_generation() -> (
    None
):
    transcript = ChatTranscript()
    await transcript.start(
        chat_message("assistant", ""), stream_id="s1", send=noop_send
    )
    await transcript.chunk(
        chat_message("assistant", "outer"),
        stream_id="s1",
        operation="append",
        send=chunk_send,
    )

    context = transcript.enter_context()
    await transcript.chunk(
        chat_message("assistant", " nested"),
        stream_id="s1",
        operation="append",
        send=chunk_send,
    )
    transcript.exit_context(context)

    await transcript.chunk(
        chat_message("assistant", "replaced"),
        stream_id="s1",
        operation="replace",
        send=chunk_send,
    )

    assert [segment.content for segment in transcript.active_segments] == [
        "replaced"
    ]


@pytest.mark.anyio
async def test_exit_context_ignores_a_stale_checkpoint_after_generation_changes() -> (
    None
):
    transcript = ChatTranscript()
    await transcript.start(
        chat_message("assistant", ""), stream_id="s1", send=noop_send
    )
    await transcript.chunk(
        chat_message("assistant", "outer"),
        stream_id="s1",
        operation="append",
        send=chunk_send,
    )
    transcript.enter_context()
    await transcript.chunk(
        chat_message("assistant", " nested"),
        stream_id="s1",
        operation="append",
        send=chunk_send,
    )
    stale_context = transcript.enter_context()

    transcript.abort("s1")
    await transcript.clear(send=noop_send)
    transcript.exit_context(stale_context)

    await transcript.start(
        chat_message("assistant", ""), stream_id="s2", send=noop_send
    )
    await transcript.chunk(
        chat_message("assistant", "final"),
        stream_id="s2",
        operation="replace",
        send=chunk_send,
    )

    assert [segment.content for segment in transcript.active_segments] == [
        "final"
    ]


@pytest.mark.anyio
async def test_replace_replaces_all_messages() -> None:
    transcript = ChatTranscript()
    await transcript.append(stored_message("user", "discard"), send=noop_send)

    await transcript.replace(
        [stored_message("assistant", "restored")], send=noop_send
    )

    assert [message.content for message in transcript.read()] == ["restored"]


@pytest.mark.anyio
async def test_replace_allows_a_missing_send_callback() -> None:
    transcript = ChatTranscript()

    await transcript.replace([stored_message("assistant", "restored")])

    assert [message.content for message in transcript.read()] == ["restored"]


@pytest.mark.anyio
async def test_replace_copies_the_input_messages() -> None:
    transcript = ChatTranscript()
    message = stored_message("assistant", "restored")

    await transcript.replace([message])
    message.segments[0].content = "mutated-after-replace"

    assert transcript.read()[0].segments[0].content == "restored"


@pytest.mark.anyio
async def test_on_change_runs_only_for_settled_message_changes() -> None:
    calls: list[None] = []
    transcript = ChatTranscript(on_change=lambda: calls.append(None))

    await transcript.append(stored_message("user", "hi"), send=noop_send)
    assert len(calls) == 1

    await transcript.start(
        chat_message("assistant", ""), stream_id="s1", send=noop_send
    )
    await transcript.chunk(
        chat_message("assistant", "partial"),
        stream_id="s1",
        operation="append",
        send=chunk_send,
    )
    assert len(calls) == 1

    await transcript.settle(stream_id="s1", send=settle_send)
    assert len(calls) == 2

    await transcript.clear(send=noop_send)
    assert len(calls) == 3

    await transcript.replace([stored_message("user", "x")], send=noop_send)
    assert len(calls) == 4


@pytest.mark.anyio
async def test_stream_candidate_carries_attachments_from_start_through_settle() -> (
    None
):
    transcript = ChatTranscript()
    attachment = Attachment.from_data(b"hi", "text/plain", name="a.txt")
    message = ChatMessage(
        content="", role="assistant", attachments=[attachment]
    )

    await transcript.start(message, stream_id="s1", send=noop_send)
    await transcript.chunk(
        chat_message("assistant", "hello"),
        stream_id="s1",
        operation="append",
        send=chunk_send,
    )

    captured: list[StoredMessage] = []

    async def capture(candidate: StreamCandidate) -> StoredMessage:
        settled = candidate_to_stored(candidate)
        captured.append(settled)
        return settled

    await transcript.settle(stream_id="s1", send=capture)

    assert captured[0].attachments == [attachment]


def stored_message(
    role: Role, content: str, content_type: ContentType = "markdown"
) -> StoredMessage:
    return StoredMessage(
        role=role,
        segments=[StoredSegment(content=content, content_type=content_type)],
    )


def chat_message(
    role: Role, content: str, content_type: ContentType = "markdown"
) -> ChatMessage:
    return ChatMessage(content=content, role=role, content_type=content_type)


async def noop_send() -> None:
    return None


def candidate_to_stored(candidate: StreamCandidate) -> StoredMessage:
    return StoredMessage(
        role=candidate.role,
        segments=[
            StoredSegment(
                content=segment.content, content_type=segment.content_type
            )
            for segment in candidate.segments
        ],
        attachments=list(candidate.attachments),
    )


async def chunk_send(candidate: StreamCandidate) -> StoredMessage | None:
    return candidate_to_stored(candidate)


async def settle_send(candidate: StreamCandidate) -> StoredMessage:
    return candidate_to_stored(candidate)
