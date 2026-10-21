# Throttled stream persistence (sa1m): deterministic, event-gated tests
# for the recorder's background snapshot writer.
#
# The controlled store is genuinely asynchronous: its put latency is held
# on an event until the test releases it, which is what proves chunk
# delivery does not pace on storage. This is not a claim that the
# production File store's IO is nonblocking.
#
# Gate timing uses a fake clock injected into the recorder module's
# ``monotonic`` symbol (imported as ``from time import monotonic``), never
# asyncio loop time, and never sleeps.

import asyncio
from typing import Any

import pytest
import shinychat._history_recorder as recorder_module
from shinychat._chat_transcript import ChatTranscript, TranscriptEntry
from shinychat._chat_types import StoredMessage, StoredSegment, StructuredBlock
from shinychat._history_store import (
    ConversationPartition,
    FileConversationStore,
    InMemoryConversationStore,
)
from shinychat._history_types import ConversationRecordV2
from test_history_controller import (
    _drain_stream_writes,
    _FakeChat,
    _make_controller,
    _stored_message,
    part,
)


class _FakeClock:
    def __init__(self, start: float = 100.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    fake = _FakeClock()
    monkeypatch.setattr(recorder_module, "monotonic", fake)
    return fake


class _GatedStore(InMemoryConversationStore):
    """An async store whose put latency is test-controlled by events.

    ``blocked`` holds every put on ``release``; ``puts`` records the
    order/identity of every record handed to the store (foreground and
    background alike); ``events`` orders puts against deletes for the
    resurrection checks.
    """

    def __init__(self) -> None:
        super().__init__()
        self.blocked = False
        self.release = asyncio.Event()
        self.put_entered = asyncio.Event()
        self.puts: list[Any] = []
        self.events: list[str] = []
        self.concurrent = 0
        self.max_concurrent = 0
        self.fail_next: list[BaseException] = []

    async def put(self, partition: ConversationPartition, record: Any) -> None:
        self.concurrent += 1
        self.max_concurrent = max(self.max_concurrent, self.concurrent)
        self.put_entered.set()
        try:
            if self.blocked:
                await self.release.wait()
            if self.fail_next:
                raise self.fail_next.pop(0)
            await super().put(partition, record)
            self.puts.append(record)
            self.events.append(f"put:{record.id}")
        finally:
            self.concurrent -= 1

    async def delete(
        self, partition: ConversationPartition, conv_id: str
    ) -> None:
        await super().delete(partition, conv_id)
        self.events.append(f"delete:{conv_id}")

    def stored(self, conv_id: str) -> ConversationRecordV2:
        record = self._data[part()][conv_id]
        assert isinstance(record, ConversationRecordV2)
        return record


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


def _text(content: str) -> StoredSegment:
    return StoredSegment(content=content, content_type="markdown")


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


async def _open_stream(
    controller: Any, store: _GatedStore
) -> tuple[ChatTranscript, str]:
    """Input + stream start (both foreground), returning the exchange id."""
    transcript = _wire(controller)
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question")
    )
    await _start_stream(transcript, exchange_id)
    return transcript, exchange_id


def _stored_contents(store: _GatedStore, conv_id: str) -> list[str]:
    record = store.stored(conv_id)
    return [
        message.as_stored_message().content
        for node in record.nodes.values()
        for message in node.messages
    ]


@pytest.mark.anyio
async def test_chunks_do_not_pace_on_slow_async_store(
    clock: _FakeClock,
) -> None:
    store = _GatedStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller, store)
    clock.advance(1.0)
    conv_id = recorder.record.id  # type: ignore[union-attr]
    foreground_puts = len(store.puts)

    store.blocked = True
    store.put_entered.clear()
    # The first chunk schedules the single background snapshot and returns
    # without waiting for storage.
    await asyncio.wait_for(
        _chunk(transcript, _assistant_message(_text("one"))), 1
    )
    await asyncio.wait_for(store.put_entered.wait(), 1)
    # Later chunks return promptly even though the put is still in flight.
    await asyncio.wait_for(
        _chunk(transcript, _assistant_message(_text(" two"))), 1
    )
    await asyncio.wait_for(
        _chunk(transcript, _assistant_message(_text(" three"))), 1
    )
    assert store.concurrent == 1
    assert store.max_concurrent == 1
    # No write has completed since the stream opened: the in-flight put is
    # the only background write.
    assert len(store.puts) == foreground_puts

    # Releasing the in-flight write lets the bounded continuation deliver
    # the latest tail once the gate has elapsed (latest-wins: the
    # intermediate "one two" snapshot is never written).
    clock.advance(1.1)
    store.release.set()
    await _drain_stream_writes(recorder)
    assert store.max_concurrent == 1
    assert _stored_contents(store, conv_id) == ["one two three"]


@pytest.mark.anyio
async def test_background_snapshot_is_a_detached_deep_copy(
    clock: _FakeClock,
) -> None:
    store = _GatedStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller, store)
    clock.advance(1.0)
    record = recorder.record
    assert record is not None

    store.blocked = True
    store.put_entered.clear()
    await _chunk(transcript, _assistant_message(_text("partial")))
    await asyncio.wait_for(store.put_entered.wait(), 1)
    snapshot_put = recorder._put_task
    assert snapshot_put is not None

    # Mutate the live record while the write is in flight: the snapshot
    # handed to the store must not follow.
    clock.advance(1.1)
    store.release.set()
    await snapshot_put
    first = store.puts[-1]
    assert first is not record
    assert [
        message.as_stored_message().content
        for node in first.nodes.values()
        for message in node.messages
    ] == ["partial"]

    await _chunk(transcript, _assistant_message(_text(" later")))
    await _drain_stream_writes(recorder)
    assert _stored_contents(store, record.id) == ["partial later"]
    # The first snapshot object stays frozen at its own content.
    assert [
        message.as_stored_message().content
        for node in first.nodes.values()
        for message in node.messages
    ] == ["partial"]


@pytest.mark.anyio
async def test_ordinary_chunks_gate_one_per_second_without_timer(
    clock: _FakeClock,
) -> None:
    store = _GatedStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller, store)
    conv_id = recorder.record.id  # type: ignore[union-attr]
    foreground_puts = len(store.puts)

    # Stream start is a foreground write, so an immediate text chunk
    # stays pending rather than causing another write inside the gate.
    await _chunk(transcript, _assistant_message(_text("one")))
    assert len(store.puts) == foreground_puts
    assert recorder._put_task is None

    clock.advance(1.0)
    await _chunk(transcript, _assistant_message(_text(" two")))
    await _drain_stream_writes(recorder)
    assert len(store.puts) == foreground_puts + 1

    # A later chunk inside the gate remains unsaved; no timer starts a put.
    await _chunk(transcript, _assistant_message(_text(" three")))
    assert recorder._pending is recorder_module._StreamPending.DIRTY
    assert recorder._put_task is None
    for _ in range(3):
        await asyncio.sleep(0)
    continuation = recorder._continuation_task
    if continuation is not None:
        await continuation
    assert recorder._put_task is None
    assert len(store.puts) == foreground_puts + 1
    assert _stored_contents(store, conv_id) == ["one two"]

    # After the interval the next chunk's snapshot is eligible and
    # latest-wins: one write carries both pending chunks.
    clock.advance(1.0)
    await _chunk(transcript, _assistant_message(_text(" four")))
    await _drain_stream_writes(recorder)
    assert len(store.puts) == foreground_puts + 2
    assert _stored_contents(store, conv_id) == ["one two three four"]


@pytest.mark.anyio
async def test_tool_request_and_result_chunks_bypass_gate(
    clock: _FakeClock,
) -> None:
    store = _GatedStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript, exchange_id = await _open_stream(controller, store)

    await _chunk(transcript, _assistant_message(_text("one")))
    await _drain_stream_writes(recorder)
    puts_before = len(store.puts)

    # A new tool request inside the gate writes immediately.
    await _chunk(transcript, _assistant_message(_tool_request()))
    await _drain_stream_writes(recorder)
    assert len(store.puts) == puts_before + 1
    stored = store.stored(recorder.record.id)  # type: ignore[union-attr]
    blocks = [
        segment
        for segment in stored.nodes[exchange_id].messages[-1].segments
        if isinstance(segment, dict)
    ]
    assert [block["type"] for block in blocks] == ["tool_request"]

    # A matching tool result inside the gate also writes immediately.
    await _chunk(transcript, _assistant_message(_tool_result()))
    await _drain_stream_writes(recorder)
    assert len(store.puts) == puts_before + 2
    stored = store.stored(recorder.record.id)  # type: ignore[union-attr]
    blocks = [
        segment
        for segment in stored.nodes[exchange_id].messages[-1].segments
        if isinstance(segment, dict)
    ]
    assert [block["type"] for block in blocks] == [
        "tool_request",
        "tool_result",
    ]

    # Trailing text after the unchanged tool blocks is ordinary: no write
    # inside the gate.
    await _chunk(transcript, _assistant_message(_text(" done")))
    assert recorder._pending is recorder_module._StreamPending.DIRTY
    assert recorder._put_task is None
    assert len(store.puts) == puts_before + 2


@pytest.mark.anyio
async def test_tool_change_queued_inflight_stays_urgent_until_snapshot(
    clock: _FakeClock,
) -> None:
    store = _GatedStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript, exchange_id = await _open_stream(controller, store)
    clock.advance(1.0)

    puts_before = len(store.puts)

    # A tool block arriving while a write is in flight queues urgent work;
    # the follow-up after completion bypasses the gate even though the
    # interval has not elapsed.
    store.blocked = True
    store.put_entered.clear()
    await _chunk(transcript, _assistant_message(_text("one")))
    await asyncio.wait_for(store.put_entered.wait(), 1)
    # An ordinary text chunk while the write is in flight is dirty...
    await _chunk(transcript, _assistant_message(_text(" two")))
    assert recorder._pending is recorder_module._StreamPending.DIRTY
    # ...and a new tool block escalates the same tail to urgent.
    await _chunk(transcript, _assistant_message(_tool_request()))
    assert recorder._pending is recorder_module._StreamPending.URGENT

    store.release.set()
    await _drain_stream_writes(recorder)
    # No clock advance since the in-flight put started, yet the urgent
    # tail was written.
    assert len(store.puts) == puts_before + 2
    stored = store.stored(recorder.record.id)  # type: ignore[union-attr]
    blocks = [
        segment
        for segment in stored.nodes[exchange_id].messages[-1].segments
        if isinstance(segment, dict)
    ]
    assert [block["type"] for block in blocks] == ["tool_request"]


@pytest.mark.anyio
async def test_unchanged_tool_projection_does_not_retrigger_urgency(
    clock: _FakeClock,
) -> None:
    store = _GatedStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller, store)

    # Start with a tool block, persisted urgently.
    await _chunk(transcript, _assistant_message(_tool_request()))
    await _drain_stream_writes(recorder)
    puts_before = len(store.puts)

    # Streaming more text with the same tool projection stays ordinary.
    await _chunk(transcript, _assistant_message(_text("thinking")))
    assert recorder._pending is recorder_module._StreamPending.DIRTY
    assert recorder._put_task is None
    assert len(store.puts) == puts_before


@pytest.mark.anyio
async def test_boundary_drains_inflight_put_without_deadlock(
    clock: _FakeClock,
) -> None:
    store = _GatedStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller, store)
    clock.advance(1.0)
    conv_id = recorder.record.id  # type: ignore[union-attr]

    store.blocked = True
    store.put_entered.clear()
    await _chunk(transcript, _assistant_message(_text("one")))
    await asyncio.wait_for(store.put_entered.wait(), 1)

    # Newer captured content must survive the foreground boundary as well
    # as the original detached background snapshot.
    await _chunk(transcript, _assistant_message(_text(" two")))
    # A boundary save waits for the in-flight background write (the put
    # never needs the recorder lock, so this cannot deadlock), then saves.
    boundary = asyncio.create_task(recorder.save_current())
    await asyncio.sleep(0)
    assert not boundary.done()
    assert store.concurrent == 1
    store.release.set()
    assert await asyncio.wait_for(boundary, 1)
    assert store.max_concurrent == 1
    assert _stored_contents(store, conv_id) == ["one two"]


@pytest.mark.anyio
async def test_boundary_cancellation_retains_running_writer(
    clock: _FakeClock,
) -> None:
    store = _GatedStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller, store)
    clock.advance(1.0)
    conv_id = recorder.record.id  # type: ignore[union-attr]

    store.blocked = True
    store.put_entered.clear()
    await _chunk(transcript, _assistant_message(_text("one")))
    await asyncio.wait_for(store.put_entered.wait(), 1)
    put = recorder._put_task
    assert put is not None

    # Cancelling the draining boundary propagates but must not cancel or
    # disown the independently running write.
    boundary = asyncio.create_task(recorder.save_current())
    await asyncio.sleep(0)
    boundary.cancel()
    with pytest.raises(asyncio.CancelledError):
        await boundary
    assert not put.cancelled()
    assert recorder._put_task is put

    store.release.set()
    await put
    assert _stored_contents(store, conv_id) == ["one"]


@pytest.mark.anyio
@pytest.mark.parametrize("boundary_kind", ["input", "finish"])
async def test_cancelled_drain_preserves_boundary_mutations_for_file_flush(
    clock: _FakeClock,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    boundary_kind: str,
) -> None:
    store = FileConversationStore(tmp_path)
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript = _wire(controller)
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question")
    )
    await _start_stream(transcript, exchange_id)
    record = recorder.record
    assert record is not None
    clock.advance(1.0)
    entered = asyncio.Event()
    release = asyncio.Event()
    original_put = store.put

    async def held_put(partition: Any, snapshot: Any) -> None:
        entered.set()
        await release.wait()
        await original_put(partition, snapshot)

    monkeypatch.setattr(store, "put", held_put)
    await _chunk(transcript, _assistant_message(_text("partial")))
    put = recorder._put_task
    assert put is not None
    try:
        await asyncio.wait_for(entered.wait(), 1)
        if boundary_kind == "input":
            operation = transcript.record_accepted_input_and_notify(
                _stored_message("user", "second input")
            )
        else:
            operation = transcript.end_stream(
                stream_id="stream", status=None, error=None, send=_sent
            )
        boundary = asyncio.create_task(operation)
        await asyncio.sleep(0)
        if boundary_kind == "input":
            assert [
                node.input.content
                for node in record.nodes.values()
                if node.input is not None
            ] == ["question", "second input"]
        else:
            assert record.nodes[exchange_id].status == "ok"
        boundary.cancel()
        with pytest.raises(asyncio.CancelledError):
            await boundary
        assert recorder._put_task is put
        assert not put.cancelled()
    finally:
        release.set()
        await asyncio.wait_for(asyncio.shield(put), 1)

    assert await recorder.flush_pending()
    # A separate store verifies the record actually saved on disk, not an
    # aliased in-memory copy of the boundary-mutated live record.
    stored = await FileConversationStore(tmp_path).get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    assert [
        message.as_stored_message().content
        for message in stored.nodes[exchange_id].messages
    ] == ["partial"]
    if boundary_kind == "input":
        assert [
            node.input.content
            for node in stored.nodes.values()
            if node.input is not None
        ] == ["question", "second input"]
    else:
        assert stored.nodes[exchange_id].status == "ok"


@pytest.mark.anyio
async def test_background_failure_logged_once_after_boundary_repair(
    clock: _FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = _GatedStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller, store)
    clock.advance(1.0)
    conv_id = recorder.record.id  # type: ignore[union-attr]

    await _chunk(transcript, _assistant_message(_text("one")))
    await _drain_stream_writes(recorder)
    puts_before = len(store.puts)

    # The next background snapshot fails; further background writes halt
    # until a boundary drains the carrier.
    store.fail_next.append(RuntimeError("disk full"))
    clock.advance(1.1)
    await _chunk(transcript, _assistant_message(_text(" two")))
    put = recorder._put_task
    assert put is not None
    with pytest.raises(RuntimeError, match="disk full"):
        await put
    assert recorder._put_task is put  # retained as the error carrier

    # Chunks still arrive and stay unsaved, with no new background write.
    await _chunk(transcript, _assistant_message(_text(" three")))
    assert recorder._put_task is put
    assert len(store.puts) == puts_before

    assert await recorder.save_current()
    # The latest state is durable and the recovered failure is reported
    # once, without making a successful operation look like a failed commit.
    assert _stored_contents(store, conv_id) == ["one two three"]
    assert not await recorder.flush_pending()
    assert await recorder.save_current()
    assert len(caplog.records) == 1
    assert caplog.records[0].exc_info is not None
    assert str(caplog.records[0].exc_info[1]) == "disk full"
    assert _stored_contents(store, conv_id) == ["one two three"]


@pytest.mark.anyio
async def test_boundary_failure_before_completion_callback_retains_tail(
    clock: _FakeClock,
) -> None:
    store = _GatedStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller, store)
    conv_id = recorder.record.id  # type: ignore[union-attr]
    clock.advance(1.0)
    store.fail_next.append(RuntimeError("transient background"))
    await _chunk(transcript, _assistant_message(_text("one")))

    # Both tasks are ready: the put fails, then this boundary observes it
    # before the put's completion callback runs. Error delivery must not
    # rely on that callback to mark the failed snapshot unsaved.
    boundary = asyncio.create_task(recorder.save_current())
    assert await boundary

    assert _stored_contents(store, conv_id) == ["one"]
    assert not await recorder.flush_pending()


@pytest.mark.anyio
async def test_terminal_boundary_repairs_file_before_reporting_background_error(
    clock: _FakeClock,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = FileConversationStore(tmp_path)
    app_values = {"region": "all"}
    controller, _ = _make_controller(
        store=store,
        save_callbacks=[lambda values: values.update(app_values)],
    )
    recorder = controller._exchange_recorder
    transcript = _wire(controller)
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question")
    )
    await _start_stream(transcript, exchange_id)
    record = recorder.record
    assert record is not None
    original_put = store.put
    background_error = RuntimeError("transient background")
    fail_next = True

    async def fail_once(partition: Any, snapshot: Any) -> None:
        nonlocal fail_next
        if fail_next:
            fail_next = False
            raise background_error
        await original_put(partition, snapshot)

    monkeypatch.setattr(store, "put", fail_once)
    clock.advance(1.0)
    await _chunk(transcript, _assistant_message(_text("answer")))
    put = recorder._put_task
    assert put is not None
    with pytest.raises(RuntimeError, match="transient background"):
        await put
    app_values["region"] = "west"

    await transcript.end_stream(
        stream_id="stream", status=None, error=None, send=_sent
    )
    assert any(
        entry.exc_info is not None and entry.exc_info[1] is background_error
        for entry in caplog.records
    )
    stored = await FileConversationStore(tmp_path).get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    assert stored.nodes[exchange_id].status == "ok"
    assert [
        message.as_stored_message().content
        for message in stored.nodes[exchange_id].messages
    ] == ["answer"]
    assert stored.nodes[exchange_id].state["shinychat:values"].data == {
        "region": "west"
    }
    assert not await recorder.flush_pending()


@pytest.mark.anyio
async def test_bookmark_repair_keeps_live_and_durable_pointer_and_referenced_state(
    clock: _FakeClock,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import shinychat._history as history_module

    store = FileConversationStore(tmp_path)
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript = _wire(controller)
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question")
    )
    await _start_stream(transcript, exchange_id)
    record = recorder.record
    assert record is not None
    record.bookmark_state_id = "old-state"
    assert await recorder.save_current()
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
    original_put = store.put
    background_error = RuntimeError("background snapshot failed")
    fail_next = True

    async def fail_once(partition: Any, snapshot: Any) -> None:
        nonlocal fail_next
        if fail_next:
            fail_next = False
            raise background_error
        await original_put(partition, snapshot)

    try:
        await asyncio.wait_for(entered.wait(), 1)
        monkeypatch.setattr(store, "put", fail_once)
        clock.advance(1.0)
        await _chunk(transcript, _assistant_message(_text("partial")))
        put = recorder._put_task
        assert put is not None
        with pytest.raises(RuntimeError, match="background snapshot failed"):
            await put
    finally:
        release.set()
    await asyncio.wait_for(mint, 1)

    stored = await FileConversationStore(tmp_path).get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    assert stored.bookmark_state_id == record.bookmark_state_id == "new-state"
    assert deleted == ["old-state"]
    assert stored.bookmark_state_id not in deleted
    assert not await recorder.flush_pending()
    assert any(
        entry.exc_info is not None and entry.exc_info[1] is background_error
        for entry in caplog.records
    )


@pytest.mark.anyio
async def test_cancelled_background_put_is_reported_once_then_save_can_retry(
    clock: _FakeClock,
) -> None:
    store = _GatedStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller, store)
    conv_id = recorder.record.id  # type: ignore[union-attr]
    clock.advance(1.0)
    store.fail_next.append(asyncio.CancelledError("backend stopped"))
    await _chunk(transcript, _assistant_message(_text("answer")))
    await asyncio.sleep(0)
    put = recorder._put_task
    assert put is not None and put.cancelled()

    with pytest.raises(asyncio.CancelledError):
        await recorder.save_current()
    assert recorder._put_task is None
    assert await recorder.save_current()
    assert _stored_contents(store, conv_id) == ["answer"]


@pytest.mark.anyio
async def test_failed_repair_reports_foreground_error_and_retains_tail(
    clock: _FakeClock,
) -> None:
    store = _GatedStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller, store)
    conv_id = recorder.record.id  # type: ignore[union-attr]
    clock.advance(1.0)
    background_error = RuntimeError("background failed")
    foreground_error = RuntimeError("repair failed")
    store.fail_next.extend([background_error, foreground_error])
    await _chunk(transcript, _assistant_message(_text("answer")))
    put = recorder._put_task
    assert put is not None
    with pytest.raises(RuntimeError, match="background failed"):
        await put

    with pytest.raises(RuntimeError) as caught:
        await recorder.save_current()
    assert caught.value is foreground_error
    assert caught.value.__cause__ is background_error
    assert await recorder.flush_pending()
    assert _stored_contents(store, conv_id) == ["answer"]


@pytest.mark.anyio
async def test_delete_observes_write_error_before_bookmark_eviction(
    clock: _FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock

    store = _GatedStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller, store)
    conv_id = recorder.record.id  # type: ignore[union-attr]
    clock.advance(1.0)
    store.fail_next.append(RuntimeError("background failed"))
    await _chunk(transcript, _assistant_message(_text("answer")))
    put = recorder._put_task
    assert put is not None
    with pytest.raises(RuntimeError, match="background failed"):
        await put
    evict = AsyncMock()
    monkeypatch.setattr(controller, "on_evict", evict)

    with pytest.raises(RuntimeError, match="background failed"):
        await controller.delete(conv_id)
    evict.assert_not_called()
    assert await store.get(part(), conv_id) is not None

    await controller.delete(conv_id)
    evict.assert_awaited_once_with(conv_id)
    assert await store.get(part(), conv_id) is None


@pytest.mark.anyio
async def test_failed_foreground_save_retains_dirty_tail_for_final_flush(
    clock: _FakeClock,
) -> None:
    store = _GatedStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller, store)
    clock.advance(1.0)
    conv_id = recorder.record.id  # type: ignore[union-attr]

    await _chunk(transcript, _assistant_message(_text("one")))
    await _drain_stream_writes(recorder)

    # A gated tail exists when the foreground save fails; the failure
    # raises but the tail stays pending for the final flush.
    clock.advance(1.1)
    await _chunk(transcript, _assistant_message(_text(" two")))
    await _drain_stream_writes(recorder)
    clock.advance(0.2)
    await _chunk(transcript, _assistant_message(_text(" three")))
    assert recorder._pending is recorder_module._StreamPending.DIRTY

    store.fail_next.append(RuntimeError("transient"))
    with pytest.raises(RuntimeError, match="transient"):
        await recorder.save_current()
    assert recorder._pending is recorder_module._StreamPending.DIRTY

    assert await recorder.flush_pending()
    assert _stored_contents(store, conv_id) == ["one two three"]


@pytest.mark.anyio
async def test_flush_pending_writes_only_unsaved_tail_without_side_effects(
    clock: _FakeClock,
) -> None:
    store = _GatedStore()
    save_calls: list[dict[str, Any]] = []
    controller, _ = _make_controller(
        store=store, save_callbacks=[save_calls.append]
    )
    recorder = controller._exchange_recorder
    chat = controller.chat
    assert isinstance(chat, _FakeChat)

    # No record at all: nothing to flush, no write.
    assert not await recorder.flush_pending()
    assert store.puts == []

    transcript, _ = await _open_stream(controller, store)
    clock.advance(1.0)
    conv_id = recorder.record.id  # type: ignore[union-attr]
    save_calls.clear()
    chat.actions.clear()

    # Everything saved: the flush writes nothing and returns False.
    await _chunk(transcript, _assistant_message(_text("one")))
    await _drain_stream_writes(recorder)
    puts_before = len(store.puts)
    assert not await recorder.flush_pending()
    assert len(store.puts) == puts_before

    # A gated tail is written directly: no app-state capture callbacks, no
    # publication, no client messages.
    await _chunk(transcript, _assistant_message(_text(" two")))
    assert recorder._pending is recorder_module._StreamPending.DIRTY
    actions_before = list(chat.actions)
    assert await recorder.flush_pending()
    assert _stored_contents(store, conv_id) == ["one two"]
    assert save_calls == []
    assert chat.actions == actions_before


@pytest.mark.anyio
async def test_flush_pending_recovers_then_reports_background_failure(
    clock: _FakeClock,
) -> None:
    store = _GatedStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller, store)
    clock.advance(1.0)
    conv_id = recorder.record.id  # type: ignore[union-attr]

    await _chunk(transcript, _assistant_message(_text("one")))
    await _drain_stream_writes(recorder)

    store.fail_next.append(RuntimeError("transient background"))
    clock.advance(1.1)
    await _chunk(transcript, _assistant_message(_text(" two")))
    put = recorder._put_task
    assert put is not None
    with pytest.raises(RuntimeError, match="transient background"):
        await put

    # The final flush still attempts the latest snapshot (recovery), then
    # reports the earlier background failure.
    with pytest.raises(RuntimeError, match="transient background"):
        await recorder.flush_pending()
    assert _stored_contents(store, conv_id) == ["one two"]

    # A final IO error of the flush itself propagates.
    clock.advance(0.1)
    await _chunk(transcript, _assistant_message(_text(" three")))
    store.fail_next.append(RuntimeError("final io"))
    with pytest.raises(RuntimeError, match="final io"):
        await recorder.flush_pending()


@pytest.mark.anyio
async def test_active_delete_drains_put_and_cannot_resurrect(
    clock: _FakeClock,
) -> None:
    store = _GatedStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller, store)
    clock.advance(1.0)
    conv_id = recorder.record.id  # type: ignore[union-attr]

    store.blocked = True
    store.put_entered.clear()
    await _chunk(transcript, _assistant_message(_text("one")))
    await asyncio.wait_for(store.put_entered.wait(), 1)

    # The delete drains the in-flight snapshot first: the write completes
    # before the delete, never after it.
    delete = asyncio.create_task(controller.delete(conv_id))
    await asyncio.sleep(0)
    assert not delete.done()
    store.release.set()
    await asyncio.wait_for(delete, 1)

    assert store.events == [
        f"put:{conv_id}",
        f"put:{conv_id}",
        f"put:{conv_id}",
        f"delete:{conv_id}",
    ]
    assert await store.get(part(), conv_id) is None
    # No follow-up write resurrects the record.
    await _drain_stream_writes(recorder)
    assert await store.get(part(), conv_id) is None


@pytest.mark.anyio
async def test_delete_after_restore_reset_drains_old_snapshot_before_removal(
    clock: _FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock

    store = _GatedStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller, store)
    conv_id = recorder.record.id  # type: ignore[union-attr]
    clock.advance(1.0)
    store.blocked = True
    store.put_entered.clear()
    await _chunk(transcript, _assistant_message(_text("partial")))
    await asyncio.wait_for(store.put_entered.wait(), 1)
    put = recorder._put_task
    assert put is not None
    monkeypatch.setattr(controller, "_notify_restore_failure", AsyncMock())
    with pytest.warns(UserWarning, match="restore failed"):
        await controller._clear_failed_restore(RuntimeError("restore failed"))
    assert recorder.record is None

    delete = asyncio.create_task(controller.delete(conv_id))
    try:
        await asyncio.sleep(0)
        assert not delete.done()
        assert store.events[-1] != f"delete:{conv_id}"
    finally:
        store.release.set()
        await asyncio.wait_for(asyncio.shield(put), 1)
        await asyncio.wait_for(delete, 1)
    assert await store.get(part(), conv_id) is None
    assert store.events[-1] == f"delete:{conv_id}"


@pytest.mark.anyio
async def test_discard_pending_cancels_continuation_but_keeps_started_put(
    clock: _FakeClock,
) -> None:
    store = _GatedStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript, _ = await _open_stream(controller, store)
    clock.advance(1.0)

    store.blocked = True
    store.put_entered.clear()
    await _chunk(transcript, _assistant_message(_text("one")))
    await asyncio.wait_for(store.put_entered.wait(), 1)
    put = recorder._put_task
    assert put is not None
    await _chunk(transcript, _assistant_message(_text(" two")))
    assert recorder._pending is recorder_module._StreamPending.DIRTY

    # Synchronous teardown drops the unscheduled tail; the started put is
    # never cancelled.
    controller.cancel_pending()
    assert recorder._pending is recorder_module._StreamPending.NONE
    assert recorder._put_task is put
    assert not put.cancelled()

    puts_before = len(store.puts)
    store.release.set()
    await put
    for _ in range(3):
        await asyncio.sleep(0)
    continuation = recorder._continuation_task
    if continuation is not None:
        await continuation
    # The discarded tail never schedules another write.
    assert len(store.puts) == puts_before + 1
    assert recorder._put_task is None
