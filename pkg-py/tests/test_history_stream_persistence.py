# Terminal-only stream persistence: deterministic behavioral tests for the
# exchange recorder.
#
# Contract under test: stream chunks and stream start mutate only the
# recorder's in-memory record. Durable writes happen at foreground boundaries
# (accepted input, explicit save, flush, terminal stream finish, bookmark and
# rename/delete mutations). Each write hands the store a detached deep copy,
# and streamed content of a still-pending exchange is never durable.
#
# Every behavioral test runs against three store backends:
#   - "memory": InMemoryConversationStore
#   - "custom": a custom store that retains the object it is handed and
#     returns that same object on read (an aliasing backend, so any missing
#     detach shows up as a changed stored snapshot)
#   - "file": FileConversationStore, read back through a fresh instance so
#     the assertions see what reached disk, not an in-memory alias.
#
# Write observation is done by wrapping each store's ``put`` the same way for
# all backends, so tests count hand-offs without depending on store internals.

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from shinychat._chat_transcript import ChatTranscript, TranscriptEntry
from shinychat._chat_types import StoredMessage, StoredSegment, StructuredBlock
from shinychat._history_store import (
    ConversationPartition,
    FileConversationStore,
    InMemoryConversationStore,
)
from shinychat._history_types import (
    TURNS_STATE_KEY,
    VALUES_STATE_KEY,
    ConversationRecordV2,
    new_conversation_record_v2,
)
from test_history_controller import (
    _FakeChat,
    _make_controller,
    _stored_message,
    part,
)


class _AliasingStore(InMemoryConversationStore):
    """A custom backend that keeps the exact object it is handed.

    No copy on put and no copy on get: a persist that forgot to detach would
    leave the stored object aliased to the live working record.
    """

    async def put(self, partition: ConversationPartition, record: Any) -> None:
        self._data.setdefault(partition, {})[record.id] = record
        self._meta_cache.pop(partition, None)


class _PutControl:
    """Test handle on every ``put`` a backend receives.

    ``received`` holds each object handed to the store with its model dump at
    hand-off time, so a later mutation of a retained object is detectable.
    ``hold`` blocks the next puts until released; ``failures`` raises queued
    errors in order before the write reaches the backend.
    """

    def __init__(self) -> None:
        self.hold: asyncio.Event | None = None
        self.entered = asyncio.Event()
        self.failures: list[BaseException] = []
        self.received: list[tuple[Any, Any]] = []


def _instrument_puts(
    store: Any, monkeypatch: pytest.MonkeyPatch
) -> _PutControl:
    control = _PutControl()
    original = store.put

    async def put(partition: ConversationPartition, record: Any) -> None:
        control.received.append((record, record.model_dump()))
        control.entered.set()
        if control.hold is not None:
            await control.hold.wait()
        if control.failures:
            raise control.failures.pop(0)
        await original(partition, record)

    monkeypatch.setattr(store, "put", put)
    return control


class _Backend:
    def __init__(
        self, kind: str, store: Any, reader: Any, control: _PutControl
    ):
        self.kind = kind
        self.store = store
        # The store to read saved state back from: the same instance for
        # in-process backends, a fresh disk-backed instance for "file".
        self.reader = reader
        self.control = control


@pytest.fixture(params=["memory", "custom", "file"])
def backend(
    request: pytest.FixtureRequest,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> _Backend:
    kind = request.param
    if kind == "memory":
        store: Any = InMemoryConversationStore()
        reader: Any = store
    elif kind == "custom":
        store = _AliasingStore()
        reader = store
    else:
        store = FileConversationStore(tmp_path)
        reader = FileConversationStore(tmp_path)
    return _Backend(kind, store, reader, _instrument_puts(store, monkeypatch))


def _live(recorder: Any) -> ConversationRecordV2:
    """The active working record, asserting it exists for type checking."""
    assert recorder.record is not None
    return recorder.record


def _wire(controller: Any) -> ChatTranscript:
    recorder = controller._exchange_recorder
    assert recorder is not None
    return ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )


async def _sent() -> bool:
    return True


def _text(content: str) -> StoredSegment:
    return StoredSegment(content=content, content_type="markdown")


def _tool_request(request_id: str = "r1") -> StructuredBlock:
    return {
        "type": "tool_request",
        "version": 1,
        "request_id": request_id,
        "tool_name": "get_weather",
    }


def _tool_result(request_id: str = "r1") -> StructuredBlock:
    return {
        "type": "tool_result",
        "version": 1,
        "request_id": request_id,
        "tool_name": "get_weather",
        "status": "success",
    }


def _assistant_message(*segments: Any) -> StoredMessage:
    return StoredMessage(role="assistant", segments=list(segments))


async def _open_input(controller: Any) -> tuple[ChatTranscript, str]:
    """Accepted input only (a foreground boundary), no stream started."""
    transcript = _wire(controller)
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question")
    )
    return transcript, exchange_id


async def _start_stream(transcript: ChatTranscript, exchange_id: str) -> None:
    await transcript.start_stream(
        stream_id="stream",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=exchange_id,
        send=_sent,
    )


async def _chunk(transcript: ChatTranscript, message: StoredMessage) -> None:
    await transcript.transition_stream(
        stream_id="stream",
        source_segments=[],
        message=message,
        operation="append",
        send=_sent,
    )


async def _end_stream(transcript: ChatTranscript, status: Any = None) -> None:
    await transcript.end_stream(
        stream_id="stream", status=status, error=None, send=_sent
    )


async def _open_stream(controller: Any) -> tuple[ChatTranscript, str]:
    """Accepted input plus stream start, returning the exchange id."""
    transcript, exchange_id = await _open_input(controller)
    await _start_stream(transcript, exchange_id)
    return transcript, exchange_id


async def _settle() -> None:
    """Yield to the loop so any work scheduled by a call can run.

    Terminal-only persistence schedules nothing, so after this yield the
    store must still show no new hand-off.
    """
    for _ in range(3):
        await asyncio.sleep(0)


async def _saved(backend: _Backend, conv_id: str) -> ConversationRecordV2:
    record = await backend.reader.get(part(), conv_id)
    assert isinstance(record, ConversationRecordV2)
    return record


def _contents(record: ConversationRecordV2) -> list[str]:
    return [
        message.as_stored_message().content
        for node in record.nodes.values()
        for message in node.messages
    ]


def _block_types(record: ConversationRecordV2, node_id: str) -> list[str]:
    return [
        segment["type"]
        for message in record.nodes[node_id].messages
        for segment in message.segments
        if isinstance(segment, dict)
    ]


async def _completed(backend: _Backend) -> tuple[Any, Any, str]:
    """A saved conversation whose one exchange finished with ``answer``."""
    controller, _ = _make_controller(store=backend.store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller)
    await _chunk(transcript, _assistant_message(_text("answer")))
    await _end_stream(transcript)
    assert recorder.record is not None
    return controller, recorder, _live(recorder).id


@pytest.mark.anyio
async def test_stream_start_and_chunks_do_not_write_before_terminal(
    backend: _Backend,
) -> None:
    controller, _ = _make_controller(store=backend.store)
    recorder = controller._exchange_recorder
    transcript, exchange_id = await _open_input(controller)
    assert recorder.record is not None
    conv_id = _live(recorder).id
    written_before_stream = len(backend.control.received)

    await _start_stream(transcript, exchange_id)
    await _chunk(transcript, _assistant_message(_text("one")))
    await _chunk(transcript, _assistant_message(_tool_request()))
    await _chunk(transcript, _assistant_message(_tool_result()))
    await _chunk(transcript, _assistant_message(_text(" done")))
    await _settle()

    # Neither stream start nor any chunk (tool blocks included) hands the
    # store anything; the content lives only in the working record.
    assert len(backend.control.received) == written_before_stream
    assert _contents(_live(recorder)) == ["one done"]

    await _end_stream(transcript)
    assert len(backend.control.received) == written_before_stream + 1
    saved = await _saved(backend, conv_id)
    assert _contents(saved) == ["one done"]
    assert _block_types(saved, exchange_id) == ["tool_request", "tool_result"]
    assert saved.nodes[exchange_id].status == "ok"


@pytest.mark.anyio
async def test_terminal_snapshot_is_detached_from_live_record(
    backend: _Backend,
) -> None:
    controller, _ = _make_controller(store=backend.store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller)
    assert recorder.record is not None
    conv_id = _live(recorder).id
    await _chunk(transcript, _assistant_message(_text("partial")))
    title = _live(recorder).title

    await _end_stream(transcript)
    snapshot, frozen = backend.control.received[-1]
    assert snapshot is not recorder.record

    # A later edit to the live record must not move the object already
    # handed to the store, nor what the store holds.
    _live(recorder).title = "Edited after terminal"
    assert snapshot.model_dump() == frozen
    assert (await _saved(backend, conv_id)).title == title


@pytest.mark.anyio
async def test_later_chunks_leave_earlier_terminal_snapshot_unchanged(
    backend: _Backend,
) -> None:
    controller, _ = _make_controller(store=backend.store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller)
    assert recorder.record is not None
    conv_id = _live(recorder).id
    await _chunk(transcript, _assistant_message(_text("one")))
    await _end_stream(transcript)
    first, first_frozen = backend.control.received[-1]

    second_exchange = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "second")
    )
    await _start_stream(transcript, second_exchange)
    written = len(backend.control.received)
    await _chunk(transcript, _assistant_message(_text(" two")))
    await _settle()

    # The second stream's chunks neither write nor disturb the first snapshot.
    assert len(backend.control.received) == written
    assert first.model_dump() == first_frozen
    assert _contents(await _saved(backend, conv_id)) == ["one"]

    await _end_stream(transcript)
    assert len(backend.control.received) == written + 1
    assert first.model_dump() == first_frozen
    assert _contents(await _saved(backend, conv_id)) == ["one", " two"]


@pytest.mark.anyio
async def test_accepted_input_persists_exchange_metadata_without_streamed_content(
    backend: _Backend,
) -> None:
    controller, _ = _make_controller(store=backend.store)
    recorder = controller._exchange_recorder
    transcript, exchange_id = await _open_input(controller)
    assert recorder.record is not None
    conv_id = _live(recorder).id

    saved = await _saved(backend, conv_id)
    saved_input = saved.nodes[exchange_id].input
    assert saved_input is not None
    assert saved_input.content == "question"
    assert saved.nodes[exchange_id].status == "pending"

    await _start_stream(transcript, exchange_id)
    await _chunk(transcript, _assistant_message(_text("partial")))
    assert _contents(_live(recorder)) == ["partial"]
    assert _contents(await _saved(backend, conv_id)) == []


@pytest.mark.anyio
async def test_flush_mid_stream_ignores_pending_exchange(
    backend: _Backend,
) -> None:
    controller, _ = _make_controller(store=backend.store)
    recorder = controller._exchange_recorder
    transcript, exchange_id = await _open_stream(controller)
    assert recorder.record is not None
    conv_id = _live(recorder).id
    await _chunk(transcript, _assistant_message(_text("partial")))

    await recorder.flush_pending()

    # The leaf is pending, so no model capture runs and the streamed text is
    # not made durable: the persisted exchange stays a pending shell.
    saved = await _saved(backend, conv_id)
    assert saved.nodes[exchange_id].status == "pending"
    assert saved.nodes[exchange_id].messages == []
    assert TURNS_STATE_KEY not in saved.nodes[exchange_id].state
    assert _contents(_live(recorder)) == ["partial"]


@pytest.mark.anyio
async def test_flush_at_completed_position_captures_model_only_without_app_callbacks(
    backend: _Backend,
) -> None:
    save_calls: list[dict[str, Any]] = []
    controller, _ = _make_controller(
        store=backend.store, save_callbacks=[save_calls.append]
    )
    recorder = controller._exchange_recorder
    chat = controller.chat
    assert isinstance(chat, _FakeChat)
    transcript, _ = await _open_stream(controller)
    assert recorder.record is not None
    conv_id = _live(recorder).id
    await _chunk(transcript, _assistant_message(_text("answer")))
    await _end_stream(transcript)
    save_calls.clear()
    chat.actions.clear()

    assert await recorder.flush_pending()

    # Model-only capture at a coherent completed exchange: the app-state
    # callbacks do not run and no client messages are sent.
    assert save_calls == []
    assert chat.actions == []
    assert _contents(await _saved(backend, conv_id)) == ["answer"]


@pytest.mark.anyio
async def test_flush_without_record_writes_nothing(backend: _Backend) -> None:
    controller, _ = _make_controller(store=backend.store)
    recorder = controller._exchange_recorder

    assert not await recorder.flush_pending()
    assert backend.control.received == []


@pytest.mark.anyio
async def test_flush_on_read_only_record_writes_nothing(
    backend: _Backend,
) -> None:
    controller, _ = _make_controller(store=backend.store)
    recorder = controller._exchange_recorder
    record = new_conversation_record_v2(
        title="Saved", id="c_read_only", client_info={}
    )
    await backend.store.put(part(), record)
    recorder.install_restored_record(record, read_only=True)
    written = len(backend.control.received)

    assert not await recorder.flush_pending()
    assert len(backend.control.received) == written


@pytest.mark.anyio
@pytest.mark.parametrize("entry", ["save", "flush"])
async def test_failed_foreground_save_reports_error_and_retry_persists(
    backend: _Backend,
    entry: str,
) -> None:
    _, recorder, conv_id = await _completed(backend)
    title_before = _live(recorder).title
    _live(recorder).title = "Edited"
    backend.control.failures.append(RuntimeError("disk full"))
    save = recorder.save_current if entry == "save" else recorder.flush_pending

    with pytest.raises(RuntimeError, match="disk full"):
        await save()
    # The failed write left the previously saved state in place.
    assert (await _saved(backend, conv_id)).title == title_before

    assert await save()
    saved = await _saved(backend, conv_id)
    assert saved.title == "Edited"
    assert _contents(saved) == ["answer"]


@pytest.mark.anyio
async def test_cancelled_foreground_save_releases_lock_and_retry_persists(
    backend: _Backend,
) -> None:
    _, recorder, conv_id = await _completed(backend)
    title_before = _live(recorder).title
    _live(recorder).title = "Edited"
    backend.control.hold = asyncio.Event()
    backend.control.entered.clear()

    save = asyncio.create_task(recorder.save_current())
    await asyncio.wait_for(backend.control.entered.wait(), 1)
    save.cancel()
    with pytest.raises(asyncio.CancelledError):
        await save

    # The cancelled write never reached the backend, and the record stays
    # live for the next boundary.
    assert recorder.record is not None
    assert (await _saved(backend, conv_id)).title == title_before
    backend.control.hold = None
    assert await asyncio.wait_for(recorder.save_current(), 1)
    assert (await _saved(backend, conv_id)).title == "Edited"


@pytest.mark.anyio
async def test_failed_restore_reset_discards_unsaved_stream_tail(
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _ = _make_controller(store=backend.store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller)
    assert recorder.record is not None
    conv_id = _live(recorder).id
    await _chunk(transcript, _assistant_message(_text("partial")))
    monkeypatch.setattr(controller, "_notify_restore_failure", AsyncMock())

    with pytest.warns(UserWarning, match="restore failed"):
        await controller._clear_failed_restore(RuntimeError("restore failed"))
    assert recorder.record is None

    written = len(backend.control.received)
    await _end_stream(transcript)
    await _settle()
    assert len(backend.control.received) == written
    assert _contents(await _saved(backend, conv_id)) == []


@pytest.mark.anyio
async def test_delete_of_unfinished_conversation_is_refused_and_stream_still_persists(
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _ = _make_controller(store=backend.store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller)
    active = recorder.record
    assert active is not None
    conv_id = active.id
    await _chunk(transcript, _assistant_message(_text("partial")))
    evict = AsyncMock()
    monkeypatch.setattr(controller, "on_evict", evict)

    # A stored record with an unfinished exchange is refused by delete: the
    # refusal happens before eviction or removal, so the record and the
    # live stream are untouched.
    with pytest.raises(RuntimeError, match="Cannot delete an interrupted"):
        await controller.delete(conv_id)
    evict.assert_not_awaited()
    assert await backend.reader.get(part(), conv_id) is not None
    assert recorder.record is active

    await _end_stream(transcript)
    assert _contents(await _saved(backend, conv_id)) == ["partial"]


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["delete", "rename"])
@pytest.mark.parametrize("current_failure", [False, True])
async def test_unrelated_mutation_uses_its_own_outcome_and_leaves_stream_intact(
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    current_failure: bool,
) -> None:
    controller, _ = _make_controller(store=backend.store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller)
    active = recorder.record
    assert active is not None
    other = new_conversation_record_v2(
        id="c_other", title="Other", client_info={}
    )
    await backend.store.put(part(), other)
    await _chunk(transcript, _assistant_message(_text("partial")))

    current_error = RuntimeError("requested operation failed")
    if current_failure:
        if operation == "delete":
            monkeypatch.setattr(
                backend.store, "delete", AsyncMock(side_effect=current_error)
            )
        else:
            backend.control.failures.append(current_error)
    action = (
        controller.delete(other.id)
        if operation == "delete"
        else controller.rename(other.id, "Renamed")
    )
    if current_failure:
        with pytest.raises(RuntimeError) as caught:
            await action
        assert caught.value is current_error
    else:
        await action

    stored_other = await backend.reader.get(part(), other.id)
    if not current_failure and operation == "delete":
        assert stored_other is None
    else:
        assert isinstance(stored_other, ConversationRecordV2)
        assert stored_other.title == ("Other" if current_failure else "Renamed")
    assert recorder.record is active

    await _end_stream(transcript)
    assert _contents(await _saved(backend, active.id)) == ["partial"]


@pytest.mark.anyio
async def test_terminal_persists_latest_app_values_and_status(
    backend: _Backend,
) -> None:
    app_values = {"region": "all"}
    controller, _ = _make_controller(
        store=backend.store,
        save_callbacks=[lambda values: values.update(app_values)],
    )
    recorder = controller._exchange_recorder
    transcript, exchange_id = await _open_stream(controller)
    assert recorder.record is not None
    conv_id = _live(recorder).id
    await _chunk(transcript, _assistant_message(_text("answer")))

    app_values["region"] = "west"
    await _end_stream(transcript)

    saved = await _saved(backend, conv_id)
    assert saved.nodes[exchange_id].status == "ok"
    assert _contents(saved) == ["answer"]
    assert saved.nodes[exchange_id].state[VALUES_STATE_KEY].data == {
        "region": "west"
    }


@pytest.mark.anyio
async def test_bookmark_persist_keeps_pointer_live_and_streamed_tail_undurable(
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shinychat._history as history_module

    controller, _ = _make_controller(store=backend.store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller)
    await _chunk(transcript, _assistant_message(_text("one")))
    await _end_stream(transcript)
    record = recorder.record
    assert record is not None
    conv_id = record.id
    record.bookmark_state_id = "old-state"
    assert await recorder.save_current()
    second = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "second")
    )
    await _start_stream(transcript, second)
    entered = asyncio.Event()
    release = asyncio.Event()
    deleted: list[str] = []

    class HeldBookmark:
        callback: Any = None

        def on_bookmarked(self, callback: Any) -> Any:
            self.callback = callback

            def cancel() -> None:
                self.callback = None

            return cancel

        async def do_bookmark(self) -> None:
            entered.set()
            await release.wait()
            await self.callback("?_state_id_=new-state")

    async def delete_state(state_id: str) -> None:
        deleted.append(state_id)

    monkeypatch.setattr(history_module, "delete_bookmark_state", delete_state)
    hooks = history_module._bookmark_restore_hooks(controller, HeldBookmark())
    assert hooks.on_response_saved is not None
    mint = asyncio.ensure_future(hooks.on_response_saved(record))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await _chunk(transcript, _assistant_message(_text("partial")))
    finally:
        release.set()
    await asyncio.wait_for(mint, 1)

    saved = await _saved(backend, conv_id)
    assert saved.bookmark_state_id == record.bookmark_state_id == "new-state"
    assert deleted == ["old-state"]
    # The bookmark write persisted the pointer but not the unfinished tail.
    assert _contents(saved) == ["one"]
