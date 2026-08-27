from __future__ import annotations

import anyio
import pytest
from shinychat._chat_transcript import ChatTranscript, TranscriptEntry
from shinychat._chat_types import ChatMessage, StoredMessage


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


@pytest.mark.anyio
async def test_read_returns_a_defensive_copy() -> None:
    transcript = ChatTranscript()
    await transcript.append(
        entry("user", "hello", icon="<i>user</i>"), send=sent
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

    await transcript.append(sent_message, send=send)
    events.append(("commit", len(transcript.read())))

    assert events == [("send", 0), ("commit", 1)]


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
        await transcript.append(source, send=send)

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
async def test_failed_send_leaves_committed_messages_unchanged() -> None:
    transcript = ChatTranscript()
    await transcript.append(entry("user", "kept"), send=sent)

    async def fail() -> bool:
        raise RuntimeError("send failed")

    with pytest.raises(RuntimeError, match="send failed"):
        await transcript.append(entry("assistant", "discarded"), send=fail)

    assert [item.message.content for item in transcript.read()] == ["kept"]


@pytest.mark.anyio
async def test_unsent_message_does_not_commit() -> None:
    transcript = ChatTranscript()

    async def unsent() -> bool:
        return False

    assert not await transcript.append(entry("system", "hidden"), send=unsent)
    assert transcript.read() == ()


@pytest.mark.anyio
async def test_mutations_notify_change() -> None:
    changes: list[None] = []
    transcript = ChatTranscript(on_change=lambda: changes.append(None))

    transcript.record_accepted_input(entry("user", "first").message)
    await transcript.append(entry("assistant", "reply"), send=sent)
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
