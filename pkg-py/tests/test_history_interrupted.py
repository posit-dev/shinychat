# Interrupted-stream checkpoints and restore isolation for the v2 exchange
# tree. Every scenario drives the real writer path (ChatTranscript ->
# _ExchangeRecorder) and the real viewer path (HistoryController.switch_to
# and friends) against three stores: InMemory, File, and an aliasing custom
# store that keeps and hands back the exact objects it is given. Puts are
# observed by wrapping the store instance's ``put``; nothing sleeps.

from pathlib import Path
from typing import Any, Callable, NamedTuple, cast

import pytest
from shinychat._history_controller import HistoryController
from shinychat._history_store import (
    ConversationPartition,
    ConversationStore,
    FileConversationStore,
    InMemoryConversationStore,
)
from shinychat._history_types import (
    CapturedMessage,
    ConversationRecordV2,
    new_conversation_record_v2,
)
from test_history_controller import (
    _FakeChat,
    _make_controller,
    _stored_message,
    part,
)
from test_history_stream_persistence import (
    _assistant_message,
    _chunk,
    _sent,
    _start_stream,
    _text,
    _wire,
)

SOURCE_ID = "c_interrupted"
OTHER_ID = "c_other"
Q1 = "q1"
Q1_ALT = "q1_alt"
Q2 = "q2"
PENDING_SIBLING = "pending_sibling"
PENDING_PARENT = "pending_parent"
CHILD = "child"


class _AliasStore(ConversationStore):
    """A custom store that keeps and hands back the exact objects it is given.

    Nothing is copied on the way in or out, so a later mutation of a record
    handed to ``put`` or returned from ``get`` is visible through the store.
    ``InMemoryConversationStore`` aliases in the same way; this store is an
    independent implementation of the store contract, so the aliasing checks
    do not depend on the built-in store's internals.
    """

    def __init__(self) -> None:
        self.records: dict[str, ConversationRecordV2] = {}

    async def list(self, partition: ConversationPartition) -> list[Any]:
        return [
            record.meta(size_bytes=len(record.model_dump_json().encode()))
            for record in self.records.values()
        ]

    async def get(
        self, partition: ConversationPartition, conv_id: str
    ) -> ConversationRecordV2 | None:
        return self.records.get(conv_id)

    async def put(self, partition: ConversationPartition, record: Any) -> None:
        self.records[record.id] = record

    async def delete(
        self, partition: ConversationPartition, conv_id: str
    ) -> None:
        self.records.pop(conv_id, None)


@pytest.fixture(params=["memory", "file", "alias"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> ConversationStore:
    if request.param == "memory":
        return InMemoryConversationStore()
    if request.param == "file":
        return FileConversationStore(tmp_path)
    return _AliasStore()


async def _stored(
    store: ConversationStore, conv_id: str
) -> ConversationRecordV2:
    record = await store.get(part(), conv_id)
    assert isinstance(record, ConversationRecordV2)
    return record


async def _stored_json(store: ConversationStore, conv_id: str) -> str:
    """A string snapshot, so later mutation of an aliased object shows up."""
    return (await _stored(store, conv_id)).model_dump_json()


def _spy_puts(store: ConversationStore) -> list[str]:
    """Record the id of every record handed to ``store.put`` from now on."""
    puts: list[str] = []
    original: Callable[..., Any] = store.put

    async def spy(partition: ConversationPartition, record: Any) -> None:
        puts.append(record.id)
        await original(partition, record)

    store.put = spy  # type: ignore[method-assign]
    return puts


def _captured(role: str, content: str) -> CapturedMessage:
    return CapturedMessage.from_stored_message(
        _stored_message(role, content), icon=None
    )


def _contents(record: ConversationRecordV2, node_id: str) -> list[str]:
    return [
        message.as_stored_message().content
        for message in record.nodes[node_id].messages
    ]


def _restored_texts(controller: HistoryController) -> list[str]:
    chat = cast(_FakeChat, controller.chat)
    return [
        message["segments"][0]["content"] for message in chat.restored_messages
    ]


def _history_updates(controller: HistoryController) -> list[dict[str, Any]]:
    chat = cast(_FakeChat, controller.chat)
    return [a for a in chat.actions if a["type"] == "history_update"]


async def _end(transcript: Any) -> None:
    await transcript.end_stream(
        stream_id="stream", status=None, error=None, send=_sent
    )


def _interrupted_source() -> ConversationRecordV2:
    """A stored checkpoint whose active leaf is an unfinished request.

    The root is closed, as accepted input closes it. ``Q1`` is a completed
    exchange with an alternate sibling ``Q1_ALT``. ``Q2`` is pending with its
    input and no streamed display: the shape a persisted checkpoint takes
    while its stream is still running.
    """
    record = new_conversation_record_v2(
        title="interrupted", id=SOURCE_ID, client_info={}
    )
    root = record.root_id
    record.nodes[root].status = "ok"
    record.open_exchange(Q1, _stored_message("user", "question one"))
    record.append_message(Q1, _captured("assistant", "answer one"))
    record.nodes[Q1].checkpoint = "valid"
    record.set_active_leaf(root)
    record.open_exchange(Q1_ALT, _stored_message("user", "question alt"))
    record.append_message(Q1_ALT, _captured("assistant", "alt answer"))
    record.nodes[Q1_ALT].checkpoint = "valid"
    record.set_active_leaf(Q1)
    record.open_exchange(Q2, _stored_message("user", "question two"))
    return record


def _other_conversation() -> ConversationRecordV2:
    """A writable empty draft: restoring it is never interrupted."""
    return new_conversation_record_v2(
        title="other", id=OTHER_ID, client_info={}
    )


async def _isolated_viewer(
    store: ConversationStore,
) -> tuple[HistoryController, list[str], str]:
    """A viewer restored onto the interrupted source, with puts observed."""
    await store.put(part(), _interrupted_source())
    await store.put(part(), _other_conversation())
    checkpoint = await _stored_json(store, SOURCE_ID)
    viewer, _ = _make_controller(store=store)
    puts = _spy_puts(store)
    await viewer.switch_to(SOURCE_ID)
    assert viewer._exchange_recorder.source_isolated
    return viewer, puts, checkpoint


@pytest.mark.anyio
async def test_stream_chunks_leave_persisted_checkpoint_until_terminal(
    store: ConversationStore,
) -> None:
    controller, _ = _make_controller(store=store)
    transcript = _wire(controller)
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question")
    )
    await _start_stream(transcript, exchange_id)
    record = controller._exchange_recorder.record
    assert record is not None
    conv_id = record.id
    puts = _spy_puts(store)

    checkpoint = await _stored_json(store, conv_id)
    stored = await _stored(store, conv_id)
    assert stored.nodes[exchange_id].status == "pending"
    assert stored.nodes[exchange_id].messages == []

    await _chunk(transcript, _assistant_message(_text("partial")))
    await _chunk(transcript, _assistant_message(_text(" answer")))
    # The chunks reach only the writer's working record: the previous
    # checkpoint is untouched, including when the store aliases it.
    assert await _stored_json(store, conv_id) == checkpoint
    assert _contents(record, exchange_id) == ["partial answer"]
    # Only the terminal event writes: chunks never reach the store.
    assert puts == []

    await _end(transcript)
    final = await _stored(store, conv_id)
    assert final.nodes[exchange_id].status == "ok"
    assert _contents(final, exchange_id) == ["partial answer"]
    assert puts == [conv_id]


@pytest.mark.anyio
async def test_rename_snapshot_strips_pending_display_but_keeps_live_stream(
    store: ConversationStore,
) -> None:
    controller, _ = _make_controller(store=store)
    transcript = _wire(controller)
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question")
    )
    await _start_stream(transcript, exchange_id)
    await _chunk(transcript, _assistant_message(_text("streamed draft")))
    record = controller._exchange_recorder.record
    assert record is not None

    await controller.rename(record.id, "Renamed")

    stored = await _stored(store, record.id)
    assert stored.title == "Renamed"
    assert stored.nodes[exchange_id].status == "pending"
    assert stored.nodes[exchange_id].messages == []
    assert "streamed draft" not in (await _stored_json(store, record.id))
    assert _contents(record, exchange_id) == ["streamed draft"]


@pytest.mark.anyio
async def test_restored_unfinished_request_isolates_to_completed_leaf(
    store: ConversationStore,
) -> None:
    writer, _ = _make_controller(store=store)
    transcript = _wire(writer)
    first = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question one")
    )
    await _start_stream(transcript, first)
    await _chunk(transcript, _assistant_message(_text("answer one")))
    await _end(transcript)
    second = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question two")
    )
    await _start_stream(transcript, second)
    await _chunk(transcript, _assistant_message(_text("partial two")))
    record = writer._exchange_recorder.record
    assert record is not None
    checkpoint = await _stored_json(store, record.id)

    viewer, _ = _make_controller(store=store)
    puts = _spy_puts(store)
    await viewer.switch_to(record.id)

    recorder = viewer._exchange_recorder
    assert recorder.source_isolated
    assert recorder.read_only
    assert recorder.record is not None
    assert recorder.record.active_leaf == first
    assert _restored_texts(viewer) == ["question one", "answer one"]
    update = _history_updates(viewer)[-1]
    assert update["active_read_only"] is True
    assert update["active_read_only_reason"] == "interrupted"
    assert await _stored_json(store, record.id) == checkpoint
    assert puts == []


@pytest.mark.anyio
async def test_isolated_viewer_rename_of_active_source_is_rejected(
    store: ConversationStore,
) -> None:
    viewer, puts, checkpoint = await _isolated_viewer(store)

    with pytest.raises(RuntimeError, match="interrupted"):
        await viewer.rename(SOURCE_ID, "Renamed")

    assert await _stored_json(store, SOURCE_ID) == checkpoint
    assert puts == []


@pytest.mark.anyio
async def test_isolated_viewer_navigation_moves_view_but_not_store(
    store: ConversationStore,
) -> None:
    viewer, puts, checkpoint = await _isolated_viewer(store)

    await viewer.handle_navigate(0, "next", request_id="navigate")

    recorder = viewer._exchange_recorder
    assert recorder.record is not None
    assert recorder.record.active_leaf == Q1_ALT
    assert _restored_texts(viewer) == ["question alt", "alt answer"]
    assert await _stored_json(store, SOURCE_ID) == checkpoint
    assert puts == []


@pytest.mark.anyio
async def test_isolated_viewer_save_is_refused_without_put(
    store: ConversationStore,
) -> None:
    viewer, puts, checkpoint = await _isolated_viewer(store)

    assert await viewer.save() is False

    assert await _stored_json(store, SOURCE_ID) == checkpoint
    assert puts == []


@pytest.mark.anyio
async def test_isolated_viewer_new_chat_does_not_put_source(
    store: ConversationStore,
) -> None:
    viewer, puts, checkpoint = await _isolated_viewer(store)

    await viewer.new_chat()

    assert viewer._exchange_recorder.record is None
    assert not viewer._exchange_recorder.read_only
    assert await _stored_json(store, SOURCE_ID) == checkpoint
    assert puts == []


@pytest.mark.anyio
async def test_isolated_viewer_switch_away_and_back_keeps_source_unwritten(
    store: ConversationStore,
) -> None:
    viewer, puts, checkpoint = await _isolated_viewer(store)

    await viewer.switch_to(OTHER_ID)

    recorder = viewer._exchange_recorder
    assert recorder.record is not None
    assert recorder.record.id == OTHER_ID
    assert not recorder.source_isolated
    assert not recorder.read_only
    assert await _stored_json(store, SOURCE_ID) == checkpoint
    assert puts == []

    # Leaving the empty writable draft saves it (model state only); the
    # isolated source is re-read, still isolated, and never written.
    await viewer.switch_to(SOURCE_ID)
    assert viewer._exchange_recorder.source_isolated
    assert await _stored_json(store, SOURCE_ID) == checkpoint
    assert puts == [OTHER_ID]


@pytest.mark.anyio
async def test_isolated_viewer_session_end_flush_does_not_put_source(
    store: ConversationStore,
) -> None:
    viewer, puts, checkpoint = await _isolated_viewer(store)

    # Session end runs the recorder flush, then cancels pending work.
    assert await viewer._exchange_recorder.flush_pending() is False
    viewer.cancel_pending()

    assert await _stored_json(store, SOURCE_ID) == checkpoint
    assert puts == []


@pytest.mark.anyio
async def test_inactive_rename_of_unresolved_source_rejects_without_mutation(
    store: ConversationStore,
) -> None:
    viewer, puts, checkpoint = await _isolated_viewer(store)
    await viewer.switch_to(OTHER_ID)

    with pytest.raises(RuntimeError, match="interrupted"):
        await viewer.rename(SOURCE_ID, "Renamed")

    assert await _stored_json(store, SOURCE_ID) == checkpoint
    assert puts == []


@pytest.mark.anyio
async def test_inactive_delete_of_unresolved_source_rejects_without_mutation(
    store: ConversationStore,
) -> None:
    viewer, puts, checkpoint = await _isolated_viewer(store)
    await viewer.switch_to(OTHER_ID)

    with pytest.raises(RuntimeError, match="interrupted"):
        await viewer.delete(SOURCE_ID)

    assert await _stored_json(store, SOURCE_ID) == checkpoint
    assert puts == []


@pytest.mark.anyio
async def test_inactive_rename_of_writable_conversation_still_persists(
    store: ConversationStore,
) -> None:
    viewer, puts, _ = await _isolated_viewer(store)

    await viewer.rename(OTHER_ID, "Renamed other")

    stored = await _stored(store, OTHER_ID)
    assert stored.title == "Renamed other"
    assert stored.title_source == "user"
    assert puts == [OTHER_ID]


@pytest.mark.anyio
async def test_original_writer_terminal_persists_after_viewer_new_chat(
    store: ConversationStore,
) -> None:
    writer, _ = _make_controller(store=store)
    transcript = _wire(writer)
    first = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question one")
    )
    await _start_stream(transcript, first)
    await _chunk(transcript, _assistant_message(_text("answer one")))
    await _end(transcript)
    second = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question two")
    )
    await _start_stream(transcript, second)
    await _chunk(transcript, _assistant_message(_text("partial two")))
    record = writer._exchange_recorder.record
    assert record is not None

    viewer, _ = _make_controller(store=store)
    await viewer.switch_to(record.id)
    assert viewer._exchange_recorder.source_isolated
    await viewer.new_chat()
    assert viewer._exchange_recorder.record is None

    # The original writer still owns its live stream; its terminal write lands.
    await _chunk(transcript, _assistant_message(_text(" final two")))
    await _end(transcript)

    stored = await _stored(store, record.id)
    assert stored.nodes[second].status == "ok"
    assert _contents(stored, second) == ["partial two final two"]
    assert not writer._exchange_recorder.source_isolated
    assert viewer._exchange_recorder.record is None


class _Shape(NamedTuple):
    record: ConversationRecordV2
    leaf: str
    isolated: bool
    texts: list[str]


def _draft_root() -> _Shape:
    """An empty pending root is a draft, not an accepted request."""
    record = new_conversation_record_v2(
        title="draft", id="c_shape", client_info={}
    )
    return _Shape(record, record.root_id, False, [])


def _pending_root_with_input() -> _Shape:
    record = new_conversation_record_v2(
        title="draft", id="c_shape", client_info={}
    )
    root = record.root_id
    record.nodes[root].input = _stored_message("user", "unsent request")
    record.nodes[root].checkpoint = "candidate"
    return _Shape(record, root, True, [])


def _pending_root_with_streamed_display() -> _Shape:
    record = new_conversation_record_v2(
        title="draft", id="c_shape", client_info={}
    )
    root = record.root_id
    record.append_stream_message(root, _captured("assistant", "no request"))
    return _Shape(record, root, True, [])


def _completed_first_exchange() -> ConversationRecordV2:
    record = new_conversation_record_v2(
        title="shape", id="c_shape", client_info={}
    )
    record.nodes[record.root_id].status = "ok"
    record.open_exchange(Q1, _stored_message("user", "question one"))
    record.append_message(Q1, _captured("assistant", "answer one"))
    record.nodes[Q1].checkpoint = "valid"
    return record


def _pending_inputless_leaf() -> _Shape:
    record = _completed_first_exchange()
    leaf = record.open_inputless_exchange()
    record.append_stream_message(leaf, _captured("assistant", "unfinished"))
    return _Shape(record, Q1, True, ["question one", "answer one"])


def _completed_leaf_with_pending_ancestor() -> _Shape:
    record = new_conversation_record_v2(
        title="shape", id="c_shape", client_info={}
    )
    record.nodes[record.root_id].status = "ok"
    record.open_exchange(
        PENDING_PARENT, _stored_message("user", "pending parent")
    )
    record.open_exchange(CHILD, _stored_message("user", "child"))
    record.append_message(CHILD, _captured("assistant", "child answer"))
    record.nodes[CHILD].checkpoint = "valid"
    return _Shape(
        record, CHILD, False, ["pending parent", "child", "child answer"]
    )


def _completed_leaf_with_pending_sibling() -> _Shape:
    record = _completed_first_exchange()
    root = record.root_id
    record.set_active_leaf(root)
    record.open_exchange(
        PENDING_SIBLING, _stored_message("user", "pending sibling")
    )
    record.set_active_leaf(Q1)
    return _Shape(record, Q1, False, ["question one", "answer one"])


@pytest.mark.anyio
@pytest.mark.parametrize(
    "build",
    [
        _draft_root,
        _pending_root_with_input,
        _pending_root_with_streamed_display,
        _pending_inputless_leaf,
        _completed_leaf_with_pending_ancestor,
        _completed_leaf_with_pending_sibling,
    ],
    ids=[
        "draft-root-writable",
        "pending-root-input-isolated",
        "pending-root-display-isolated",
        "pending-inputless-leaf-isolated",
        "completed-leaf-pending-ancestor-writable",
        "completed-leaf-pending-sibling-writable",
    ],
)
async def test_restore_isolates_only_unresolved_active_leaf(
    store: ConversationStore,
    build: Callable[[], _Shape],
) -> None:
    shape = build()
    await store.put(part(), shape.record)
    viewer, _ = _make_controller(store=store)

    await viewer.switch_to(shape.record.id)

    recorder = viewer._exchange_recorder
    assert recorder.source_isolated is shape.isolated
    assert recorder.read_only is shape.isolated
    assert recorder.record is not None
    assert recorder.record.active_leaf == shape.leaf
    assert _restored_texts(viewer) == shape.texts


@pytest.mark.anyio
async def test_prepare_exchange_restore_reports_isolation_as_third_value() -> (
    None
):
    controller, _ = _make_controller(store=InMemoryConversationStore())
    source = _interrupted_source()

    nodes, _plan, isolated = controller._prepare_exchange_restore(
        source.model_copy(deep=True)
    )
    assert isolated is True
    assert nodes == (source.root_id, Q1)

    draft = _draft_root().record
    draft_nodes, _draft_plan, draft_isolated = (
        controller._prepare_exchange_restore(draft.model_copy(deep=True))
    )
    assert draft_isolated is False
    assert draft_nodes == (draft.root_id,)


@pytest.mark.anyio
async def test_bookmark_to_completed_node_keeps_unresolved_source_isolated(
    store: ConversationStore,
) -> None:
    # The stored active leaf is unfinished, but the bookmark selects a
    # completed sibling: the source is still unresolved, so the restore is
    # isolated and read-only, and nothing is written back.
    await store.put(part(), _interrupted_source())
    checkpoint = await _stored_json(store, SOURCE_ID)
    target = await _stored(store, SOURCE_ID)
    viewer, _ = _make_controller(store=store)
    puts = _spy_puts(store)

    await viewer._restore_initial_exchange_record(target, node_id=Q1_ALT)

    recorder = viewer._exchange_recorder
    assert recorder.source_isolated
    assert recorder.read_only
    assert recorder.record is not None
    assert recorder.record.active_leaf == Q1_ALT
    assert _restored_texts(viewer) == ["question alt", "alt answer"]
    assert await _stored_json(store, SOURCE_ID) == checkpoint
    assert puts == []


@pytest.mark.anyio
async def test_leaving_writable_draft_saves_model_state_without_app_values(
    store: ConversationStore,
) -> None:
    await store.put(part(), _interrupted_source())
    await store.put(part(), _other_conversation())
    on_save_calls: list[str] = []

    def on_save(values: dict[str, Any]) -> None:
        on_save_calls.append("save")
        values["region"] = "west"

    viewer, _ = _make_controller(store=store, save_callbacks=[on_save])
    await viewer.switch_to(OTHER_ID)
    puts = _spy_puts(store)

    await viewer.switch_to(SOURCE_ID)

    # App values are captured only by explicit or boundary saves, never when
    # leaving a conversation: the model-only node-close save runs instead.
    assert on_save_calls == []
    assert puts == [OTHER_ID]


@pytest.mark.anyio
async def test_isolated_viewer_delete_of_active_source_is_rejected_after_store_completes(
    store: ConversationStore,
) -> None:
    viewer, puts, _ = await _isolated_viewer(store)
    # The store's copy completes after this viewer was restored: the viewer's
    # own isolation still refuses to delete the source it is showing.
    completed = _interrupted_source()
    completed.append_message(Q2, _captured("assistant", "final two"))
    completed.finish_exchange(Q2, "ok", None)
    await store.put(part(), completed)
    puts.clear()

    with pytest.raises(RuntimeError, match="interrupted"):
        await viewer.delete(SOURCE_ID)

    assert (await _stored(store, SOURCE_ID)).nodes[Q2].status == "ok"
    assert puts == []
