# HistoryController's session-coupled behavior (switch_to, on_response, etc.)
# is covered by Playwright e2e tests (Task 13). This file tests the pure
# helpers that HistoryController delegates to.

import asyncio
import os
import signal
import subprocess
import sys
import textwrap
import warnings
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, cast
from unittest.mock import AsyncMock

import pytest
from _history_test_helpers import branch_from
from shinychat._chat_transcript import ChatTranscript, TranscriptEntry
from shinychat._chat_types import StoredMessage, StoredSegment
from shinychat._history import (
    HistoryController,
    do_bookmark_with_cleanup,
    extend_record_linear,
)
from shinychat._history_store import (
    ConversationPartition,
    ConversationStore,
    InMemoryConversationStore,
)
from shinychat._history_types import (
    MAX_SCHEMA_VERSION,
    ConversationRecord,
    ConversationRecordV2,
    UnsupportedSchemaVersionError,
    new_conversation_record,
)


def msg(role: str) -> dict[str, object]:
    return {
        "role": role,
        "segments": [{"content": role, "content_type": "markdown"}],
    }


def part(
    *, chat_id: str = "chat", scope: str = "test-scope"
) -> ConversationPartition:
    return ConversationPartition(chat_id=chat_id, scope=scope)


def test_extend_appends_only_new_groups_with_ui_by_role():
    rec = new_conversation_record(title="t")
    groups = [
        [{"role": "user", "content": "q1"}],
        [{"role": "assistant", "content": "a1"}],
    ]
    extend_record_linear(rec, groups, [msg("user"), msg("assistant")])
    assert len(rec.nodes) == 2
    path = rec.path_node_ids()
    assert rec.nodes[path[0]].turns == [{"role": "user", "content": "q1"}]
    assert rec.nodes[path[0]].ui == [msg("user")]
    assert rec.nodes[path[1]].ui == [msg("assistant")]

    groups += [
        [{"role": "user", "content": "q2"}],
        [{"role": "assistant", "content": "a2"}],
    ]
    all_msgs = [msg("user"), msg("assistant"), msg("user"), msg("assistant")]
    extend_record_linear(rec, groups, all_msgs)
    assert len(rec.nodes) == 4
    assert rec.nodes[rec.path_node_ids()[2]].ui == [msg("user")]


def test_extend_groups_tool_exchange_into_single_node():
    user_turn = {
        "role": "user",
        "contents": [{"content_type": "text", "text": "weather?"}],
    }
    asst_req = {
        "role": "assistant",
        "contents": [
            {
                "content_type": "tool_request",
                "id": "x",
                "name": "get_weather",
                "arguments": {},
            }
        ],
    }
    user_res = {
        "role": "user",
        "contents": [
            {"content_type": "tool_result", "id": "x", "value": "Sunny"}
        ],
    }
    asst_final = {
        "role": "assistant",
        "contents": [{"content_type": "text", "text": "It's sunny."}],
    }

    groups = [
        [user_turn],
        [asst_req, user_res, asst_final],
    ]
    msgs = [msg("user"), msg("assistant")]
    rec = new_conversation_record(title="t")
    extend_record_linear(rec, groups, msgs)

    assert len(rec.nodes) == 2
    path = rec.path_node_ids()

    user_node = rec.nodes[path[0]]
    asst_node = rec.nodes[path[1]]

    assert len(user_node.turns) == 1
    assert len(asst_node.turns) == 3
    assert user_node.ui == [msg("user")]
    assert asst_node.ui == [msg("assistant")]

    # path_turns() must flatten back to all 4 original turns
    assert rec.path_turns() == [user_turn, asst_req, user_res, asst_final]


def test_extend_attaches_extra_assistant_msgs_to_last_node():
    rec = new_conversation_record(title="t")
    groups = [
        [{"role": "user", "content": "q"}],
        [{"role": "assistant", "content": "a"}],
    ]
    msgs = [
        msg("user"),
        msg("assistant"),
        msg("assistant"),
    ]
    extend_record_linear(rec, groups, msgs)
    path = rec.path_node_ids()
    assert rec.nodes[path[1]].ui == [msg("assistant"), msg("assistant")]


def test_extend_attaches_late_ui_message_when_turn_groups_already_caught_up():
    # Simulates: append_message() (non-streamed) followed by a streamed
    # reply, both saved to history. Save #1 creates the user/assistant
    # nodes from the turn groups. By save #2, chatlas turns have already
    # caught up (streaming adds no *new* turn group), but a new UI message
    # (the streamed reply) has arrived and must not be dropped.
    rec = new_conversation_record(title="t")
    groups = [
        [{"role": "user", "content": "q"}],
        [{"role": "assistant", "content": "a"}],
    ]
    user_ui = msg("user")
    oob_ui = msg("assistant")
    streamed_ui = msg("assistant")

    # Save #1: two new turn groups, two UI messages.
    extend_record_linear(rec, groups, [user_ui, oob_ui])
    assert len(rec.nodes) == 2

    # Save #2 reconstructs the active path from the whole server transcript.
    extend_record_linear(rec, groups, [user_ui, oob_ui, streamed_ui])

    all_ui = [
        m
        for node_id in rec.path_node_ids()
        for m in (rec.nodes[node_id].ui or [])
    ]
    assert all_ui == [user_ui, oob_ui, streamed_ui]


def test_extend_rebuilds_without_duplicate_ui_when_groups_are_unchanged():
    rec = new_conversation_record(title="t")
    groups = [[{"role": "user", "content": "q"}]]
    message = msg("user")
    extend_record_linear(rec, groups, [message])
    extend_record_linear(rec, groups, [message])
    assert rec.nodes[rec.path_node_ids()[0]].ui == [message]


def test_extend_rebuilds_each_response_under_its_own_user_turn():
    rec = new_conversation_record(title="t")
    groups = [
        [{"role": "user", "content": "q1"}],
        [{"role": "assistant", "content": "a1"}],
        [{"role": "user", "content": "q2"}],
        [{"role": "assistant", "content": "a2"}],
    ]
    q1 = msg("user")
    a1 = msg("assistant")
    q2 = msg("user")
    a2 = msg("assistant")

    extend_record_linear(rec, groups, [q1, a1, q2, a2])

    path = rec.path_node_ids()
    assert rec.nodes[path[0]].ui == [q1]
    assert rec.nodes[path[1]].ui == [a1]
    assert rec.nodes[path[2]].ui == [q2]
    assert rec.nodes[path[3]].ui == [a2]


def test_extend_with_ui_messages_reconstructs_them():
    rec = new_conversation_record(title="t")
    groups = [
        [{"role": "user", "content": "q"}],
        [{"role": "assistant", "content": "a"}],
    ]
    msgs = [msg("user"), msg("assistant")]
    extend_record_linear(rec, groups, msgs)
    assert len(rec.nodes) == 2
    assert [
        message
        for node_id in rec.path_node_ids()
        for message in (rec.nodes[node_id].ui or [])
    ] == msgs


# --- response settlement persistence (unit-level, no Shiny session needed) ---


class _FakeChat:
    def __init__(self) -> None:
        self.set_greeting_calls: list[Any] = []
        self.destructive_preflight_calls = 0
        self.restored_messages: list[dict[str, Any]] = []
        self.restored_icons: list[str | None] = []

    def _messages_for_bookmark(self) -> list[Any]:
        return []

    def _messages_for_history(self) -> list[Any]:
        return self._messages_for_bookmark()

    async def _send_action(self, action: Any) -> None:
        pass

    async def clear_messages(self) -> None:
        pass

    @asynccontextmanager
    async def _destructive_history_mutation(self):
        self.destructive_preflight_calls += 1
        yield

    async def _restore_bookmark_message(
        self, message_dict: Any, *, icon: str | None = None
    ) -> None:
        self.restored_messages.append(message_dict)
        self.restored_icons.append(icon)

    async def set_greeting(self, greeting: Any) -> None:
        self.set_greeting_calls.append(greeting)


class _FakeAdapter:
    def get_turns_json(self) -> list[Any]:
        return [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]

    def get_turns_grouped(self) -> list[list[Any]]:
        return [[t] for t in self.get_turns_json()]

    def set_turns_json(self, turns: list[Any]) -> None:
        pass

    def client_info(self) -> dict[str, Any]:
        return {}


class _RecordingStore(ConversationStore):
    def __init__(self) -> None:
        self.put_calls: list[tuple[ConversationPartition, Any]] = []

    async def put(self, partition: ConversationPartition, record: Any) -> None:
        self.put_calls.append((partition, record))

    async def list(self, partition: ConversationPartition) -> list[Any]:
        return []

    async def get(
        self, partition: ConversationPartition, conv_id: str
    ) -> ConversationRecord | None:
        return None

    async def delete(
        self, partition: ConversationPartition, conv_id: str
    ) -> None:
        pass


class _PartitionCaptureStore(ConversationStore):
    def __init__(self) -> None:
        self.put_partitions: list[ConversationPartition] = []
        self.records: dict[str, ConversationRecord] = {}

    async def list(self, partition: ConversationPartition) -> list[Any]:
        return []

    async def get(
        self, partition: ConversationPartition, conv_id: str
    ) -> ConversationRecord | None:
        return self.records.get(conv_id)

    async def put(
        self, partition: ConversationPartition, record: ConversationRecord
    ) -> None:
        self.put_partitions.append(partition)
        self.records[record.id] = record

    async def delete(
        self, partition: ConversationPartition, conv_id: str
    ) -> None:
        self.records.pop(conv_id, None)


def _make_controller(
    store: ConversationStore | None = None,
    save_callbacks: list[Callable[[dict[str, Any]], None]] | None = None,
    *,
    use_exchange_tree: bool = False,
) -> tuple[HistoryController, Any]:
    resolved_store = store if store is not None else _RecordingStore()
    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=resolved_store,
        title_fn=None,
        title_enabled=False,
        client=None,
        save_callbacks=save_callbacks,
        use_exchange_tree=use_exchange_tree,
    )
    controller.partition = part()
    return controller, resolved_store


def _stored_message(role: str, content: str) -> StoredMessage:
    return StoredMessage(
        role=role,  # type: ignore[arg-type]
        segments=[StoredSegment(content=content, content_type="markdown")],
    )


@pytest.mark.anyio
async def test_v2_recorder_persists_one_input_response_and_replays_display():
    store = InMemoryConversationStore()
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None

    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
    )
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "hello")
    )
    await transcript.append(
        TranscriptEntry(
            message=_stored_message("assistant", "hi"),
            icon="<i>bot</i>",
        ),
        exchange_id=exchange_id,
        send=_sent,
    )

    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    assert controller.record is None
    assert record.nodes["n_0000"].status == "ok"
    node = record.nodes[exchange_id]
    assert node.status == "ok"
    assert node.input is not None and node.input.content == "hello"
    assert [message.as_stored_message().content for message in node.messages] == [
        "hi"
    ]

    await controller.on_response()
    assert (await store.get(part(), record.id)) == record

    restored, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
    )
    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    await restored.replay_exchange_record(stored)
    fake_chat = cast(_FakeChat, restored.chat)
    assert [message["role"] for message in fake_chat.restored_messages] == [
        "user",
        "assistant",
    ]
    assert [
        message["segments"][0]["content"]
        for message in fake_chat.restored_messages
    ] == ["hello", "hi"]
    assert fake_chat.restored_icons == [None, "<i>bot</i>"]


@pytest.mark.anyio
async def test_v2_recorder_replaces_stream_projection_on_its_opening_exchange():
    store = InMemoryConversationStore()
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )

    first_exchange = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "first")
    )
    await transcript.start_stream(
        stream_id="stream",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=first_exchange,
        send=_sent,
    )
    await transcript.transition_stream(
        stream_id="stream",
        source_segments=[],
        message=_stored_message("assistant", "partial"),
        operation="append",
        send=_sent,
    )
    second_exchange = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "second")
    )
    await transcript.end_stream(
        stream_id="stream",
        status=None,
        error=None,
        send=_sent,
    )

    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    first = record.nodes[first_exchange]
    assert first.status == "ok"
    assert [message.as_stored_message().content for message in first.messages] == [
        "partial"
    ]
    assert record.nodes[second_exchange].status == "pending"
    assert record.active_leaf == second_exchange
    assert recorder._stream_exchanges == {}


@pytest.mark.anyio
async def test_v2_recorder_persists_pre_input_stream_on_pending_root() -> None:
    store = InMemoryConversationStore()
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )

    await transcript.start_stream(
        stream_id="stream",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=None,
        send=_sent,
    )
    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    root_id = record.active_leaf
    assert root_id is not None
    assert root_id == "n_0000"
    assert record.title == "New chat"
    assert record.nodes[root_id].input is None
    assert record.nodes[root_id].status == "pending"

    await transcript.transition_stream(
        stream_id="stream",
        source_segments=[],
        message=_stored_message("assistant", "before input"),
        operation="append",
        send=_sent,
    )
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question")
    )
    await transcript.end_stream(
        stream_id="stream",
        status=None,
        error=None,
        send=_sent,
    )

    assert record.title == "New chat"
    assert record.active_leaf == exchange_id
    assert record.nodes[root_id].status == "ok"
    assert [message.as_stored_message().content for message in record.nodes[root_id].messages] == [
        "before input"
    ]
    assert record.nodes[exchange_id].input is not None


@pytest.mark.anyio
async def test_v2_recorder_ignores_prepartition_content_without_failing_send():
    store = InMemoryConversationStore()
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
    )
    controller.partition = None
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )

    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "early input")
    )
    assert await transcript.append(
        TranscriptEntry(message=_stored_message("assistant", "initial")),
        exchange_id=None,
        send=_sent,
    )
    assert await transcript.start_stream(
        stream_id="early",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=None,
        send=_sent,
    )
    assert await transcript.transition_stream(
        stream_id="early",
        source_segments=[],
        message=_stored_message("assistant", "partial"),
        operation="append",
        send=_sent,
    )
    assert await transcript.end_stream(
        stream_id="early",
        status=None,
        error=None,
        send=_sent,
    )
    assert recorder.record is None
    assert recorder._stream_exchanges == {}
    conversation_metas = await store.list(part())
    assert conversation_metas == []

    controller.partition = part()
    assert await transcript.start_stream(
        stream_id="persisted",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=None,
        send=_sent,
    )

    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    root_id = record.active_leaf
    assert root_id == "n_0000"
    root = record.nodes[root_id]
    assert root.status == "pending"
    assert root.messages[0].as_stored_message().content == ""
    assert recorder._stream_exchanges == {"persisted": "n_0000"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "error"),
    [
        (None, None),
        ("error", "provider timeout"),
        ("cancelled", None),
    ],
)
async def test_v2_recorder_reopens_terminal_exchange_for_a_new_stream(
    status: str | None, error: str | None
) -> None:
    store = InMemoryConversationStore()
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_finished=recorder.stream_finished,
    )
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question")
    )
    await transcript.start_stream(
        stream_id="first",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=exchange_id,
        send=_sent,
    )
    await transcript.end_stream(
        stream_id="first",
        status=status,  # type: ignore[arg-type]
        error=error,
        send=_sent,
    )
    await transcript.start_stream(
        stream_id="second",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=exchange_id,
        send=_sent,
    )

    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    node = record.nodes[exchange_id]
    assert node.status == "pending"
    assert node.error is None


@pytest.mark.anyio
async def test_v2_recorder_creates_inputless_child_for_unowned_content() -> None:
    store = InMemoryConversationStore()
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
    )

    parent_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question")
    )
    await transcript.append(
        TranscriptEntry(message=_stored_message("assistant", "notice")),
        exchange_id=None,
        send=_sent,
    )

    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    child_id = record.active_leaf
    assert child_id is not None
    assert child_id != parent_id
    child = record.nodes[child_id]
    assert child.parent_id == parent_id
    assert child.input is None
    assert child.status == "ok"
    assert [message.as_stored_message().content for message in child.messages] == [
        "notice"
    ]


@pytest.mark.anyio
async def test_v2_recorder_serializes_blocked_stream_projection_before_new_input():
    class BlockingSnapshotStore(ConversationStore):
        def __init__(self) -> None:
            self.records: dict[str, ConversationRecordV2] = {}
            self.block_next_put = False
            self.blocked = asyncio.Event()
            self.release = asyncio.Event()

        async def list(self, partition: ConversationPartition) -> list[Any]:
            return []

        async def get(
            self, partition: ConversationPartition, conv_id: str
        ) -> ConversationRecordV2 | None:
            return self.records.get(conv_id)

        async def put(
            self, partition: ConversationPartition, record: Any
        ) -> None:
            snapshot = record.model_copy(deep=True)
            if self.block_next_put:
                self.block_next_put = False
                self.blocked.set()
                await self.release.wait()
            self.records[snapshot.id] = snapshot

        async def delete(
            self, partition: ConversationPartition, conv_id: str
        ) -> None:
            self.records.pop(conv_id, None)

    store = BlockingSnapshotStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
    )
    first_exchange = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "first")
    )
    await transcript.start_stream(
        stream_id="stream",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=first_exchange,
        send=_sent,
    )

    store.block_next_put = True
    update = asyncio.create_task(
        transcript.transition_stream(
            stream_id="stream",
            source_segments=[],
            message=_stored_message("assistant", "partial"),
            operation="append",
            send=_sent,
        )
    )
    await store.blocked.wait()
    next_input = asyncio.create_task(
        transcript.record_accepted_input_and_notify(
            _stored_message("user", "second")
        )
    )
    await asyncio.sleep(0)
    assert not next_input.done()

    store.release.set()
    await update
    second_exchange = await next_input

    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    stored = store.records[record.id]
    assert stored.active_leaf == second_exchange
    assert second_exchange in stored.nodes
    assert stored.nodes[first_exchange].messages[-1].as_stored_message().content == (
        "partial"
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "error"),
    [
        ("error", "provider timeout"),
        ("cancelled", None),
    ],
)
async def test_v2_recorder_persists_stream_terminal_status(
    status: str, error: str | None
) -> None:
    store = InMemoryConversationStore()
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )

    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question")
    )
    await transcript.start_stream(
        stream_id="stream",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=exchange_id,
        send=_sent,
    )
    await transcript.transition_stream(
        stream_id="stream",
        source_segments=[],
        message=_stored_message("assistant", "partial"),
        operation="append",
        send=_sent,
    )
    await transcript.end_stream(
        stream_id="stream",
        status=status,  # type: ignore[arg-type]
        error=error,
        send=_sent,
    )

    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    node = record.nodes[exchange_id]
    assert node.status == status
    if error is None:
        assert node.error is None
    else:
        assert node.error is not None
        assert node.error.message == error
    assert [message.as_stored_message().content for message in node.messages] == [
        "partial"
    ]


@pytest.mark.anyio
async def test_stream_recorder_failure_does_not_rollback_sent_transcript():
    class FailingStore(InMemoryConversationStore):
        fail = False

        async def put(
            self, partition: ConversationPartition, record: Any
        ) -> None:
            if self.fail:
                raise RuntimeError("durability failure")
            await super().put(partition, record)

    store = FailingStore()
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question")
    )
    await transcript.start_stream(
        stream_id="stream",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=exchange_id,
        send=_sent,
    )

    store.fail = True
    with pytest.raises(RuntimeError, match="durability failure"):
        await transcript.transition_stream(
            stream_id="stream",
            source_segments=[],
            message=_stored_message("assistant", "sent partial"),
            operation="append",
            send=_sent,
        )

    assert transcript.read()[-1].message.content == "sent partial"
    assert transcript.active_stream_id == "stream"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("checkpoint", "expected_content", "expected_status", "expected_error"),
    [
        ("pre-input-start", [""], "pending", None),
        ("input", [], "pending", None),
        ("start", [""], "pending", None),
        ("update-one", ["first"], "pending", None),
        ("update-two", ["first second"], "pending", None),
        ("ok", ["first second"], "ok", None),
        ("error", ["first second"], "error", "provider timeout"),
        ("cancelled", ["first second"], "cancelled", None),
    ],
)
async def test_stream_capture_survives_process_kill_and_file_store_reload(
    tmp_path: Any,
    checkpoint: str,
    expected_content: list[str],
    expected_status: str,
    expected_error: str | None,
) -> None:
    from shinychat._history_store import FileConversationStore

    source_root = str(
        (Path(__file__).resolve().parents[1] / "src").resolve()
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = (
        source_root
        if not env.get("PYTHONPATH")
        else source_root + os.pathsep + env["PYTHONPATH"]
    )
    child = textwrap.dedent(
        """
        import asyncio
        import os
        import signal
        import sys
        from types import SimpleNamespace

        from shinychat._chat_transcript import ChatTranscript, TranscriptEntry
        from shinychat._chat_types import StoredMessage, StoredSegment
        from shinychat._history import _ExchangeRecorder
        from shinychat._history_store import ConversationPartition, FileConversationStore

        def message(role, content):
            return StoredMessage(
                role=role,
                segments=[StoredSegment(content=content, content_type="markdown")],
            )

        async def sent():
            return True

        async def run():
            store = FileConversationStore(sys.argv[1])
            controller = SimpleNamespace(
                partition=ConversationPartition(chat_id="kill", scope="scope"),
                adapter=SimpleNamespace(client_info=lambda: {}),
                store=store,
            )
            recorder = _ExchangeRecorder(controller)
            transcript = ChatTranscript(
                on_accepted_input=recorder.accepted_input,
                on_stream_started=recorder.stream_started,
                on_stream_updated=recorder.stream_updated,
                on_stream_finished=recorder.stream_finished,
            )
            if sys.argv[2] == "pre-input-start":
                await transcript.start_stream(
                    stream_id="stream",
                    entry=TranscriptEntry(message=message("assistant", "")),
                    owner_task=None,
                    exchange_id=None,
                    send=sent,
                )
                os.kill(os.getpid(), signal.SIGKILL)
            exchange_id = await transcript.record_accepted_input_and_notify(
                message("user", "question")
            )
            if sys.argv[2] == "input":
                os.kill(os.getpid(), signal.SIGKILL)
            await transcript.start_stream(
                stream_id="stream",
                entry=TranscriptEntry(message=message("assistant", "")),
                owner_task=None,
                exchange_id=exchange_id,
                send=sent,
            )
            if sys.argv[2] == "start":
                os.kill(os.getpid(), signal.SIGKILL)
            await transcript.transition_stream(
                stream_id="stream",
                source_segments=[],
                message=message("assistant", "first"),
                operation="append",
                send=sent,
            )
            if sys.argv[2] == "update-one":
                os.kill(os.getpid(), signal.SIGKILL)
            await transcript.transition_stream(
                stream_id="stream",
                source_segments=[],
                message=message("assistant", " second"),
                operation="append",
                send=sent,
            )
            if sys.argv[2] == "update-two":
                os.kill(os.getpid(), signal.SIGKILL)
            status = None if sys.argv[2] == "ok" else sys.argv[2]
            error = "provider timeout" if status == "error" else None
            await transcript.end_stream(
                stream_id="stream",
                status=status,
                error=error,
                send=sent,
            )
            os.kill(os.getpid(), signal.SIGKILL)

        asyncio.run(run())
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", child, str(tmp_path), checkpoint],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == -signal.SIGKILL, result.stderr
    store = FileConversationStore(tmp_path)
    metas = await store.list(ConversationPartition(chat_id="kill", scope="scope"))
    assert len(metas) == 1
    record = await store.get(
        ConversationPartition(chat_id="kill", scope="scope"), metas[0].id
    )
    assert isinstance(record, ConversationRecordV2)
    if checkpoint == "pre-input-start":
        assert record.title == "New chat"
        node = record.nodes["n_0000"]
        assert node.input is None
    else:
        node = next(node for node in record.nodes.values() if node.input is not None)
    assert node.status == expected_status
    assert (
        [message.as_stored_message().content for message in node.messages]
        == expected_content
    )
    assert (
        node.error is None
        if expected_error is None
        else node.error is not None and node.error.message == expected_error
    )


async def _sent() -> bool:
    return True


@pytest.mark.anyio
async def test_exchange_recorder_is_default_off_and_uses_v1_save_path():
    controller, store = _make_controller()

    assert controller._exchange_recorder is None
    await controller.on_response()

    assert len(store.put_calls) == 1
    assert isinstance(store.put_calls[0][1], ConversationRecord)


@pytest.mark.anyio
async def test_replay_ui_clears_greeting():
    controller, _store = _make_controller()
    record = new_conversation_record(title="t")

    await controller.replay_ui(record)

    fake_chat = cast(Any, controller.chat)
    assert fake_chat.set_greeting_calls == [None]


@pytest.mark.anyio
async def test_notify_settled_calls_on_settled_hook():
    controller, _store = _make_controller()
    calls: list[bool] = []

    async def _on_settled(restored: bool) -> None:
        calls.append(restored)

    controller.on_settled = _on_settled
    await controller.notify_settled(True)
    await controller.notify_settled(False)

    assert calls == [True, False]


@pytest.mark.anyio
async def test_notify_settled_no_op_when_hook_unset():
    controller, _store = _make_controller()
    # Must not raise when nothing has registered a hook.
    await controller.notify_settled(True)


@pytest.mark.anyio
async def test_new_chat_notifies_settled_false():
    controller, _store = _make_controller()
    calls: list[bool] = []

    async def _on_settled(restored: bool) -> None:
        calls.append(restored)

    controller.on_settled = _on_settled
    await controller.new_chat()

    assert calls == [False]


@pytest.mark.anyio
async def test_controller_passes_partition_to_custom_store():
    store = _PartitionCaptureStore()
    controller, _store = _make_controller(store=store)
    controller.partition = ConversationPartition(
        chat_id="ns-chat", scope="browser-1"
    )

    await controller.on_response()

    assert store.put_partitions == [
        ConversationPartition(chat_id="ns-chat", scope="browser-1")
    ]


@pytest.mark.anyio
async def test_same_scope_different_chat_ids_are_isolated():
    store = InMemoryConversationStore()

    controller_a, _store_a = _make_controller(store=store)
    controller_a.partition = ConversationPartition(
        chat_id="chat-a", scope="browser-1"
    )
    await controller_a.on_response()
    assert controller_a.record is not None

    controller_b, _store_b = _make_controller(store=store)
    controller_b.partition = ConversationPartition(
        chat_id="chat-b", scope="browser-1"
    )

    assert (
        await store.get(controller_a.partition, controller_a.record.id)
        is not None
    )
    assert (
        await store.get(controller_b.partition, controller_a.record.id) is None
    )
    assert await store.list(controller_b.partition) == []


@pytest.mark.anyio
async def test_namespaced_chat_ids_are_distinct_partitions():
    store = InMemoryConversationStore()
    ns1 = ConversationPartition(chat_id="mod1-chat", scope="browser-1")
    ns2 = ConversationPartition(chat_id="mod2-chat", scope="browser-1")
    rec = new_conversation_record(title="module one")

    await store.put(ns1, rec)

    assert await store.get(ns1, rec.id) is rec
    assert await store.get(ns2, rec.id) is None


@pytest.mark.anyio
async def test_each_response_settlement_captures_current_app_state():
    controller, store = _make_controller()
    accent = "info"

    controller._save_callbacks.append(
        lambda values: values.update({"accent": accent})
    )

    await controller.on_response()
    assert controller.record is not None
    assert controller.record.values["accent"] == "info"

    accent = "danger"
    await controller.on_response()

    assert len(store.put_calls) == 2
    assert controller.record.values["accent"] == "danger"


class _ReplayFakeChat(_FakeChat):
    """Fake chat whose server-owned message store reflects the latest replay."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[Any] = []

    def _messages_for_bookmark(self) -> list[Any]:
        return self.messages

    async def clear_messages(self) -> None:
        self.messages = []

    async def _restore_bookmark_message(
        self, message_dict: Any, *, icon: str | None = None
    ) -> None:
        self.messages.append(message_dict)


class _OwnerHistoryFakeChat(_FakeChat):
    def _messages_for_bookmark(self) -> list[Any]:
        return [msg("user"), msg("assistant")]

    def _messages_for_history(self) -> list[Any]:
        return [
            {
                "role": "user",
                "segments": [
                    {"content": "accepted", "content_type": "markdown"}
                ],
            },
            {
                "role": "assistant",
                "segments": [
                    {"content": "emitted", "content_type": "markdown"}
                ],
            },
        ]


@pytest.mark.anyio
async def test_on_response_persists_server_owned_messages():
    controller, _store = _make_controller()
    controller.chat = _OwnerHistoryFakeChat()  # type: ignore[assignment]

    await controller.on_response()

    assert controller.record is not None
    stored = [
        message
        for node_id in controller.record.path_node_ids()
        for message in (controller.record.nodes[node_id].ui or [])
    ]
    assert stored == controller.chat._messages_for_history()


@pytest.mark.anyio
async def test_replay_ui_reconstructs_saved_server_transcript():
    controller, store = _make_controller()
    chat = _ReplayFakeChat()
    controller.chat = chat  # type: ignore[assignment]

    chat.messages = [msg("user"), msg("assistant")]
    await controller.on_response()
    assert len(store.put_calls) == 1
    record = controller.record
    assert record is not None
    saved_ui = [
        m
        for nid in record.path_node_ids()
        for m in (record.nodes[nid].ui or [])
    ]

    await controller.replay_ui(record)
    assert chat.messages == saved_ui, "replay must reconstruct the full UI"


@pytest.mark.anyio
async def test_explicit_save_returns_false_without_active_record():
    controller, store = _make_controller()

    assert await controller.save() is False
    assert store.put_calls == []


@pytest.mark.anyio
async def test_explicit_save_captures_state_without_counting_response():
    saved_values: list[dict[str, Any]] = []

    def capture(values: dict[str, Any]) -> None:
        values["artifact"] = {"version": 2}
        saved_values.append(dict(values))

    controller, store = _make_controller(save_callbacks=[capture])
    await controller.on_response()
    assert controller.record is not None
    response_count = controller.record.response_count
    put_count = len(store.put_calls)

    assert await controller.save() is True
    assert controller.record.response_count == response_count
    assert controller.record.values == {"artifact": {"version": 2}}
    assert len(saved_values) == 2
    assert len(store.put_calls) == put_count + 1
    assert controller._title_task is None


@pytest.mark.anyio
async def test_explicit_save_does_not_start_title_generation():
    title_calls: list[list[dict[str, Any]]] = []

    async def title_fn(turns: list[dict[str, Any]]) -> str:
        title_calls.append(turns)
        return "Generated title"

    controller, _store = _make_controller()
    controller.title_enabled = True
    controller.title_fn = title_fn
    await controller.on_response()
    assert controller.record is not None
    assert controller.record.response_count == 1
    assert controller._title_task is None

    assert await controller.save() is True
    assert controller._title_task is None
    assert title_calls == []


@pytest.mark.anyio
async def test_explicit_save_runs_history_lifecycle_after_persist():
    controller, _store = _make_controller()
    await controller.on_response()
    events: list[str] = []

    original_put = controller._put_record

    async def put(
        partition: ConversationPartition, record: ConversationRecord
    ) -> None:
        await original_put(partition, record)
        events.append("put")

    async def bookmark(record: ConversationRecord) -> None:
        events.append("bookmark")

    controller._put_record = put
    controller.on_response_saved = bookmark
    controller._evict_if_needed = AsyncMock(
        side_effect=lambda: events.append("evict")
    )
    controller.send_history_update = AsyncMock(
        side_effect=lambda: events.append("history")
    )
    controller._send_sibling_metadata = AsyncMock(
        side_effect=lambda: events.append("siblings")
    )

    assert await controller.save() is True
    assert events == ["put", "evict", "bookmark", "history", "siblings"]


# --- on_url_change (URL-mode navigation) ------------------------------------


class _NavFakeChat(_FakeChat):
    def __init__(self) -> None:
        super().__init__()
        self.actions: list[dict[str, Any]] = []
        self.cleared = 0

    async def _send_action(self, action: Any) -> None:
        self.actions.append(dict(action))

    async def clear_messages(self) -> None:
        self.cleared += 1

    async def _restore_bookmark_message(
        self, message_dict: Any, *, icon: str | None = None
    ) -> None:
        pass


class _NavFakeAdapter(_FakeAdapter):
    def __init__(self) -> None:
        self.set_calls: list[list[Any]] = []

    def set_turns_json(self, turns: list[Any]) -> None:
        self.set_calls.append(turns)


class _NavStore(_RecordingStore):
    def __init__(self) -> None:
        super().__init__()
        self.records: dict[str, Any] = {}
        self.deleted: list[str] = []

    async def get(self, partition: ConversationPartition, conv_id: str) -> Any:
        return self.records.get(conv_id)

    async def delete(
        self, partition: ConversationPartition, conv_id: str
    ) -> None:
        self.deleted.append(conv_id)
        self.records.pop(conv_id, None)


def _make_nav_controller(
    *, with_url_mode: bool = False
) -> tuple[HistoryController, _NavStore, _NavFakeChat]:
    store = _NavStore()
    chat = _NavFakeChat()
    controller = HistoryController(
        chat=chat,  # type: ignore[arg-type]
        adapter=_NavFakeAdapter(),  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = part()
    if with_url_mode:

        async def _update_url(conv_id: str | None) -> None:
            url = f"?conv={conv_id}" if conv_id is not None else None
            await controller.send_navigate(url, conv_id)

        controller.on_active_id_change = _update_url
    return controller, store, chat


def _nav_actions(chat: _NavFakeChat) -> list[dict[str, Any]]:
    return [a for a in chat.actions if a["type"] == "history_navigate"]


@pytest.mark.anyio
async def test_switch_to_swaps_in_session():
    controller, store, chat = _make_nav_controller()
    target = new_conversation_record(title="other")
    store.records[target.id] = target

    await controller.switch_to(target.id)

    assert _nav_actions(chat) == []
    assert chat.cleared == 1
    assert controller.record is target


@pytest.mark.anyio
async def test_active_stream_rejects_history_switch_before_partial_mutation():
    controller, store, chat = _make_nav_controller()
    active = new_conversation_record(title="active")
    target = new_conversation_record(title="target")
    controller.record = active
    store.records[target.id] = target

    @asynccontextmanager
    async def reject_active_stream():
        raise RuntimeError(
            "Cannot clear or restore messages while a message stream is active."
        )
        yield

    chat._destructive_history_mutation = reject_active_stream  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="stream is active"):
        await controller.switch_to(target.id)

    assert controller.record is active
    assert store.put_calls == []
    assert cast(_NavFakeAdapter, controller.adapter).set_calls == []
    assert chat.cleared == 0


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["new_chat", "delete", "replay_ui"])
async def test_active_stream_rejects_destructive_history_paths_before_mutation(
    operation: str,
):
    controller, store, chat = _make_nav_controller()
    active = new_conversation_record(title="active")
    controller.record = active
    store.records[active.id] = active

    @asynccontextmanager
    async def reject_active_stream():
        raise RuntimeError(
            "Cannot clear or restore messages while a message stream is active."
        )
        yield

    chat._destructive_history_mutation = reject_active_stream  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="stream is active"):
        if operation == "new_chat":
            await controller.new_chat()
        elif operation == "delete":
            await controller.delete(active.id)
        else:
            await controller.replay_ui(active)

    assert controller.record is active
    assert store.records[active.id] is active
    assert cast(_NavFakeAdapter, controller.adapter).set_calls == []
    assert chat.cleared == 0


@pytest.mark.anyio
async def test_switch_to_url_mode_sends_navigate():
    controller, store, chat = _make_nav_controller(with_url_mode=True)
    target = new_conversation_record(title="other")
    store.records[target.id] = target

    await controller.switch_to(target.id)

    navs = _nav_actions(chat)
    assert len(navs) == 1
    assert navs[0]["url"] == f"?conv={target.id}"
    assert navs[0]["active_id"] == target.id
    assert chat.cleared == 1
    assert controller.record is target


@pytest.mark.anyio
async def test_switch_to_nonexistent_id_raises():
    controller, _store, _chat = _make_nav_controller()

    with pytest.raises(RuntimeError, match="no longer exists"):
        await controller.switch_to("does-not-exist")


class _UnsupportedSchemaVersionStore(ConversationStore):
    """Custom store whose get() returns a record from a newer, unsupported
    schema version -- simulates a downgrade against a store written by a
    future version of shinychat."""

    async def list(self, partition: ConversationPartition) -> list[Any]:
        return []

    async def get(
        self, partition: ConversationPartition, conv_id: str
    ) -> ConversationRecord | None:
        rec = new_conversation_record(title="from the future")
        rec.id = conv_id
        cast(Any, rec).schema_version = MAX_SCHEMA_VERSION + 1
        return rec

    async def put(self, partition: ConversationPartition, record: Any) -> None:
        pass

    async def delete(
        self, partition: ConversationPartition, conv_id: str
    ) -> None:
        pass


@pytest.mark.anyio
async def test_switch_to_rejects_record_with_unsupported_schema_version():
    store = _UnsupportedSchemaVersionStore()
    controller, _store = _make_controller(store=store)

    with pytest.raises(UnsupportedSchemaVersionError):
        await controller.switch_to("c_future")

    assert controller.record is None


@pytest.mark.anyio
async def test_rename_rejects_record_with_unsupported_schema_version_before_writing():
    # The controller must check schema_version on every write, not just every
    # read -- a custom store's put() should never see an incompatible record
    # (issue #322).
    controller, store = _make_controller()
    controller.record = new_conversation_record(title="t")
    cast(Any, controller.record).schema_version = MAX_SCHEMA_VERSION + 1

    with pytest.raises(UnsupportedSchemaVersionError):
        await controller.rename(controller.record.id, "new title")

    assert store.put_calls == []


@pytest.mark.anyio
async def test_new_chat_url_mode_sends_navigate_null():
    controller, _store, chat = _make_nav_controller(with_url_mode=True)

    await controller.new_chat()

    navs = _nav_actions(chat)
    assert navs == [
        {"type": "history_navigate", "url": None, "active_id": None}
    ]
    assert chat.cleared == 1


@pytest.mark.anyio
async def test_send_navigate_can_request_hard_reload():
    controller, _store, chat = _make_nav_controller()

    await controller.send_navigate("?_state_id_=abc123", "c123", reload=True)

    navs = _nav_actions(chat)
    assert navs == [
        {
            "type": "history_navigate",
            "url": "?_state_id_=abc123",
            "active_id": "c123",
            "reload": True,
        }
    ]


@pytest.mark.anyio
async def test_new_chat_browser_mode_no_navigate():
    controller, _store, chat = _make_nav_controller()

    await controller.new_chat()

    assert _nav_actions(chat) == []
    assert chat.cleared == 1


@pytest.mark.anyio
async def test_delete_active_url_mode_sends_navigate_null():
    controller, store, chat = _make_nav_controller(with_url_mode=True)
    active = new_conversation_record(title="doomed")
    store.records[active.id] = active
    # Activate through the shared op so record and active ID move together,
    # as every real code path does.
    await controller.activate_record(active)

    await controller.delete(active.id)

    assert store.deleted == [active.id]
    navs = _nav_actions(chat)
    assert navs == [
        {
            "type": "history_navigate",
            "url": f"?conv={active.id}",
            "active_id": active.id,
        },
        {"type": "history_navigate", "url": None, "active_id": None},
    ]


@pytest.mark.anyio
async def test_delete_inactive_does_not_navigate():
    controller, store, chat = _make_nav_controller(with_url_mode=True)
    other = new_conversation_record(title="other")
    store.records[other.id] = other

    await controller.delete(other.id)

    assert store.deleted == [other.id]
    assert _nav_actions(chat) == []


@pytest.mark.anyio
async def test_on_response_first_save_url_mode_sends_navigate():
    controller, _store, chat = _make_nav_controller(with_url_mode=True)

    await controller.on_response()

    assert controller.record is not None
    navs = _nav_actions(chat)
    assert len(navs) == 1
    assert navs[0]["url"] == f"?conv={controller.record.id}"


# --- retitle ------------------------------------------------------------------


def _make_retitle_controller(
    title_fn: Any = None,
    raw_client: Any = None,
) -> tuple[HistoryController, _RecordingStore]:
    store = _RecordingStore()
    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=title_fn,
        title_enabled=True,
        client=raw_client,
    )
    controller.partition = part()
    return controller, store


@pytest.mark.anyio
async def test_retitle_updates_title_and_persists():
    controller, store = _make_retitle_controller(
        title_fn=lambda turns: "Generated Title",
    )
    controller.record = new_conversation_record(title="fallback")

    await controller.retitle([{"role": "user", "content": "hi"}])

    assert controller.record.title == "Generated Title"
    assert controller.record.title_source == "llm"
    assert len(store.put_calls) == 1


@pytest.mark.anyio
async def test_retitle_noop_when_record_is_none():
    controller, store = _make_retitle_controller(
        title_fn=lambda turns: "should not be used",
    )

    await controller.retitle([])

    assert store.put_calls == []


# --- bookmark callback cleanup ------------------------------------------------


class _BookmarkStub:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.cancel_calls = 0
        self.on_bookmarked_calls = 0

    def on_bookmarked(self, fn: Any) -> Any:
        self.on_bookmarked_calls += 1

        def cancel() -> None:
            self.cancel_calls += 1

        return cancel

    async def do_bookmark(self) -> None:
        if self.fail:
            raise RuntimeError("bookmark failed")


@pytest.mark.anyio
async def test_do_bookmark_with_cleanup_cancels_on_success():
    bookmark = _BookmarkStub()

    async def _on_bookmarked(url: str) -> None:
        pass

    await do_bookmark_with_cleanup(bookmark, _on_bookmarked)

    assert bookmark.on_bookmarked_calls == 1
    assert bookmark.cancel_calls == 1


@pytest.mark.anyio
async def test_do_bookmark_with_cleanup_cancels_on_failure():
    bookmark = _BookmarkStub(fail=True)

    async def _on_bookmarked(url: str) -> None:
        pass

    with pytest.raises(RuntimeError, match="bookmark failed"):
        await do_bookmark_with_cleanup(bookmark, _on_bookmarked)

    assert bookmark.on_bookmarked_calls == 1
    assert bookmark.cancel_calls == 1


@pytest.mark.anyio
async def test_retitle_noop_when_user_already_renamed():
    controller, store = _make_retitle_controller(
        title_fn=lambda turns: "should not be used",
    )
    controller.record = new_conversation_record(title="My Title")
    controller.record.title_source = "user"

    await controller.retitle([])

    assert controller.record.title == "My Title"
    assert store.put_calls == []


@pytest.mark.anyio
async def test_retitle_noop_when_generate_returns_none():
    controller, store = _make_retitle_controller(
        title_fn=lambda turns: None,
    )
    controller.record = new_conversation_record(title="fallback")

    await controller.retitle([])

    assert controller.record.title == "fallback"
    assert controller.record.title_source is None
    assert store.put_calls == []


@pytest.mark.anyio
async def test_retitle_noop_when_conversation_switched_during_generation():
    original = new_conversation_record(title="original")
    replacement = new_conversation_record(title="replacement")

    controller, store = _make_retitle_controller()

    async def slow_title(turns: Any) -> str:
        # Simulate the conversation switching while the LLM call is in flight
        controller.record = replacement
        return "Title for original"

    controller.title_fn = slow_title
    controller.record = original

    await controller.retitle([])

    assert original.title == "original", "must not update the old record"
    assert controller.record is replacement
    assert store.put_calls == []


@pytest.mark.anyio
async def test_retitle_noop_when_user_renames_during_generation():
    record = new_conversation_record(title="fallback")

    controller, store = _make_retitle_controller()

    async def slow_title(turns: Any) -> str:
        # Simulate the user renaming while the LLM call is in flight
        record.title_source = "user"
        record.title = "User's Title"
        return "LLM Title"

    controller.title_fn = slow_title
    controller.record = record

    await controller.retitle([])

    assert record.title == "User's Title"
    assert record.title_source == "user"
    assert store.put_calls == []


# --- deferred titling trigger --------------------------------------------------


class _GrowingFakeAdapter:
    """Like _FakeAdapter, but turns grow across calls to simulate multiple
    real responses (_FakeAdapter always returns the same fixed 2 turns)."""

    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []

    def get_turns_json(self) -> list[Any]:
        return list(self.turns)

    def get_turns_grouped(self) -> list[list[Any]]:
        return [[t] for t in self.turns]

    def set_turns_json(self, turns: list[Any]) -> None:
        self.turns = list(turns)

    def client_info(self) -> dict[str, Any]:
        return {}


def _make_deferred_title_controller(
    title_fn: Any = None,
) -> tuple[HistoryController, _RecordingStore, _GrowingFakeAdapter]:
    store = _RecordingStore()
    adapter = _GrowingFakeAdapter()
    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=adapter,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=title_fn,
        title_enabled=True,
        client=None,
    )
    controller.partition = part()
    return controller, store, adapter


@pytest.mark.anyio
async def test_title_stays_fallback_after_first_response():
    controller, _store, adapter = _make_deferred_title_controller(
        title_fn=lambda turns: "Generated Title",
    )
    adapter.turns = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]

    await controller.on_response()

    assert controller.record is not None
    assert controller.record.response_count == 1
    assert controller.record.title_source is None
    assert controller._title_task is None


@pytest.mark.anyio
async def test_titling_fires_after_second_response_exactly_once():
    controller, _store, adapter = _make_deferred_title_controller(
        title_fn=lambda turns: "Generated Title",
    )
    adapter.turns = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    await controller.on_response()
    task_after_first_response = controller._title_task
    assert task_after_first_response is None

    adapter.turns += [
        {"role": "user", "content": "more"},
        {"role": "assistant", "content": "sure"},
    ]
    await controller.on_response()

    assert controller.record is not None
    assert controller.record.response_count == 2
    title_task = controller._title_task
    assert title_task is not None
    await title_task
    assert controller.record.title == "Generated Title"
    assert controller.record.title_source == "llm"


@pytest.mark.anyio
async def test_rename_between_first_and_second_response_blocks_auto_titling():
    controller, _store, adapter = _make_deferred_title_controller(
        title_fn=lambda turns: "Generated Title",
    )
    adapter.turns = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    await controller.on_response()
    assert controller.record is not None
    await controller.rename(controller.record.id, "My Title")

    adapter.turns += [
        {"role": "user", "content": "more"},
        {"role": "assistant", "content": "sure"},
    ]
    await controller.on_response()

    assert controller.record is not None
    assert controller._title_task is None
    assert controller.record.title == "My Title"
    assert controller.record.title_source == "user"


@pytest.mark.anyio
async def test_titling_fires_on_second_response_across_sessions():
    store = InMemoryConversationStore()
    adapter1 = _GrowingFakeAdapter()
    controller1 = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=adapter1,  # type: ignore[arg-type]
        store=store,
        title_fn=lambda turns: "Generated Title",
        title_enabled=True,
        client=None,
    )
    controller1.partition = part()
    adapter1.turns = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    await controller1.on_response()
    assert controller1.record is not None
    conv_id = controller1.record.id
    assert controller1._title_task is None

    # Simulate a brand-new session: fresh controller, same backing store,
    # loads the persisted (1-response) conversation before continuing it.
    adapter2 = _GrowingFakeAdapter()
    adapter2.turns = list(adapter1.turns)
    controller2 = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=adapter2,  # type: ignore[arg-type]
        store=store,
        title_fn=lambda turns: "Generated Title",
        title_enabled=True,
        client=None,
    )
    controller2.partition = part()
    controller2.record = await store.get(part(), conv_id)

    adapter2.turns += [
        {"role": "user", "content": "more"},
        {"role": "assistant", "content": "sure"},
    ]
    await controller2.on_response()

    title_task = controller2._title_task
    assert title_task is not None
    await title_task
    assert controller2.record is not None
    assert controller2.record.title == "Generated Title"
    assert controller2.record.title_source == "llm"


# --- save/restore callbacks --------------------------------------------------


def _make_fake_chat() -> _FakeChat:
    return _FakeChat()


@pytest.mark.anyio
async def test_save_callback_fires_and_values_stored(tmp_path: Any) -> None:
    """on_save callback populates record.values."""
    from shinychat._history_store import FileConversationStore

    save_calls: list[dict[str, Any]] = []
    save_cbs: list[Any] = []

    def my_save(values: dict[str, Any]) -> None:
        values["x"] = 42
        save_calls.append(dict(values))

    save_cbs.append(my_save)

    store = FileConversationStore(tmp_path)
    adapter = _FakeAdapter()
    controller = HistoryController(
        chat=_make_fake_chat(),  # type: ignore[arg-type]
        adapter=adapter,  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=object(),
        save_callbacks=save_cbs,
        restore_callbacks=[],
    )
    controller.partition = part(scope="alice")

    await controller.on_response()

    assert len(save_calls) == 1
    assert save_calls[0]["x"] == 42
    assert controller.record is not None
    assert controller.record.values.get("x") == 42


@pytest.mark.anyio
async def test_restore_callback_fires_on_switch(tmp_path: Any) -> None:
    """on_restore callback receives stored values on switch_to."""
    from shinychat._history_store import FileConversationStore
    from shinychat._history_types import new_conversation_record

    restored: list[tuple[dict[str, Any], str]] = []
    restore_cbs: list[Any] = []

    store = FileConversationStore(tmp_path)
    adapter = _NavFakeAdapter()
    chat = _NavFakeChat()
    controller = HistoryController(
        chat=chat,  # type: ignore[arg-type]
        adapter=adapter,  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=object(),
        save_callbacks=[],
        restore_callbacks=restore_cbs,
    )
    controller.partition = part(scope="alice")

    def on_restore(values: dict[str, Any]) -> None:
        assert controller.record is not None
        restored.append((dict(values), controller.record.id))

    restore_cbs.append(on_restore)

    # Create a record with values directly in the store (not via on_response,
    # which would immediately re-capture and overwrite our values).
    target = new_conversation_record(title="old")
    target.values = {"x": 99}
    await store.put(part(scope="alice"), target)

    # Simulate having a different current conversation
    other = new_conversation_record(title="current")
    await store.put(part(scope="alice"), other)
    controller.record = other

    await controller.switch_to(target.id)

    assert restored == [({"x": 99}, target.id)]


# ---------------------------------------------------------------------------
# _evict_if_needed
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_evict_if_needed_noop_when_no_limit():
    store = InMemoryConversationStore()
    rec = new_conversation_record(title="t")
    await store.put(part(scope="alice"), rec)

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
        max_store_bytes=None,
    )
    controller.partition = part(scope="alice")

    await controller._evict_if_needed()
    assert len(await store.list(part(scope="alice"))) == 1


@pytest.mark.anyio
async def test_evict_if_needed_noop_when_under_limit():
    store = InMemoryConversationStore()
    rec = new_conversation_record(title="t")
    await store.put(part(scope="alice"), rec)

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
        max_store_bytes=100
        * 1024
        * 1024,  # 100 MB — well above any test record
    )
    controller.partition = part(scope="alice")

    await controller._evict_if_needed()
    assert len(await store.list(part(scope="alice"))) == 1


@pytest.mark.anyio
async def test_evict_if_needed_removes_oldest_preserves_active():
    store = InMemoryConversationStore()

    rec1 = new_conversation_record(title="oldest")
    rec2 = new_conversation_record(title="middle")
    rec3 = new_conversation_record(title="newest")
    rec2.created_at = rec2.created_at + timedelta(seconds=1)
    rec3.created_at = rec3.created_at + timedelta(seconds=2)
    for rec in [rec1, rec2, rec3]:
        await store.put(part(scope="alice"), rec)

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
        max_store_bytes=1,  # 1 byte: ensures all non-active records are evicted
    )
    controller.partition = part(scope="alice")
    controller.record = rec3  # newest is active

    await controller._evict_if_needed()

    remaining = {m.id for m in await store.list(part(scope="alice"))}
    assert rec1.id not in remaining
    assert rec2.id not in remaining
    assert rec3.id in remaining


@pytest.mark.anyio
async def test_evict_if_needed_calls_list_once_and_never_total_size():
    # Regression: total_size() used to be re-called (a full-scope sweep) on
    # every eviction iteration. The running total should now come entirely
    # from a single list() call's per-record size_bytes.
    store = InMemoryConversationStore()
    rec1 = new_conversation_record(title="oldest")
    rec2 = new_conversation_record(title="middle")
    rec3 = new_conversation_record(title="newest")
    rec2.created_at = rec2.created_at + timedelta(seconds=1)
    rec3.created_at = rec3.created_at + timedelta(seconds=2)
    for rec in [rec1, rec2, rec3]:
        await store.put(part(scope="alice"), rec)

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
        max_store_bytes=1,
    )
    controller.partition = part(scope="alice")
    controller.record = rec3

    list_spy = AsyncMock(wraps=store.list)
    total_size_spy = AsyncMock(wraps=store.total_size)
    store.list = list_spy  # type: ignore[method-assign]
    store.total_size = total_size_spy  # type: ignore[method-assign]

    await controller._evict_if_needed()

    assert list_spy.call_count == 1
    assert total_size_spy.call_count == 0


@pytest.mark.anyio
async def test_evict_if_needed_warns_once_when_active_alone_exceeds_budget():
    store = InMemoryConversationStore()
    rec = new_conversation_record(title="big")
    rec.append_linear([{"role": "user", "content": "x" * 1000}])
    await store.put(part(scope="alice"), rec)

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
        max_store_bytes=1,
    )
    controller.partition = part(scope="alice")
    controller.record = rec  # active; nothing else to evict

    with pytest.warns(UserWarning, match="remains over"):
        await controller._evict_if_needed()

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await controller._evict_if_needed()  # must not warn a second time


@pytest.mark.anyio
async def test_evict_one_deletes_from_store():
    store = InMemoryConversationStore()
    rec = new_conversation_record(title="old")
    await store.put(part(scope="alice"), rec)

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
        max_store_bytes=None,
    )
    controller.partition = part(scope="alice")

    await controller._evict_one(rec.id)

    assert await store.get(part(scope="alice"), rec.id) is None


# ---------------------------------------------------------------------------
# Controller lifecycle hooks: on_response_saved, on_pre_switch, on_evict
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_on_response_saved_fires_when_new_data_is_saved():
    controller, store = _make_controller()
    fired: list[str] = []
    turns = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]

    class _GrowingAdapter(_FakeAdapter):
        def get_turns_json(self) -> list[Any]:
            return turns

    async def hook(record: Any) -> None:
        fired.append(record.id)

    controller.adapter = _GrowingAdapter()  # type: ignore[assignment]
    controller.on_response_saved = hook

    await controller.on_response()
    turns.extend(
        [
            {"role": "user", "content": "more"},
            {"role": "assistant", "content": "sure"},
        ]
    )
    await controller.on_response()

    assert len(fired) == 2
    assert fired[0] == fired[1]  # same conversation id both times


@pytest.mark.anyio
async def test_switch_new_and_delete_do_not_settle_response_for_another_record():
    controller, store, _chat = _make_nav_controller()
    active = new_conversation_record(title="active")
    target = new_conversation_record(title="target")
    store.records[target.id] = target
    controller.record = active
    settled: list[str] = []

    async def on_response_saved(record: ConversationRecord) -> None:
        settled.append(record.id)

    controller.on_response_saved = on_response_saved

    await controller.switch_to(target.id)
    await controller.new_chat()
    await controller.delete(active.id)

    assert settled == []


@pytest.mark.anyio
async def test_on_pre_switch_true_skips_in_session_swap():
    controller, store, chat = _make_nav_controller()
    target = new_conversation_record(title="other")
    store.records[target.id] = target
    pre_switch_calls: list[str] = []

    async def hook(rec: Any) -> bool:
        pre_switch_calls.append(rec.id)
        return True  # signal: skip in-session swap

    controller.on_pre_switch = hook

    await controller.switch_to(target.id)

    assert pre_switch_calls == [target.id]
    # In-session swap was skipped: client turns NOT updated, UI NOT cleared
    assert chat.cleared == 0
    # record not changed because we returned True (navigation handled by hook)
    assert controller.record is None


@pytest.mark.anyio
async def test_on_pre_switch_false_allows_in_session_swap():
    controller, store, chat = _make_nav_controller()
    target = new_conversation_record(title="other")
    store.records[target.id] = target
    pre_switch_calls: list[str] = []

    async def hook(rec: Any) -> bool:
        pre_switch_calls.append(rec.id)
        return False  # allow normal in-session swap

    controller.on_pre_switch = hook

    await controller.switch_to(target.id)

    assert pre_switch_calls == [target.id]
    assert chat.cleared == 1
    assert controller.record is target


# --- on_evict hook -----------------------------------------------------------


@pytest.mark.anyio
async def test_on_evict_fires_before_store_delete_in_evict_one():
    store = InMemoryConversationStore()
    rec = new_conversation_record(title="old")
    await store.put(part(scope="alice"), rec)

    order: list[str] = []

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = part(scope="alice")

    async def hook(conv_id: str) -> None:
        # Record must still exist in store when the hook fires
        still_there = await store.get(part(scope="alice"), conv_id)
        order.append("hook_before" if still_there is not None else "hook_after")

    controller.on_evict = hook

    await controller._evict_one(rec.id)

    assert order == ["hook_before"]
    assert await store.get(part(scope="alice"), rec.id) is None


@pytest.mark.anyio
async def test_on_evict_fires_before_store_delete_in_delete():
    store = InMemoryConversationStore()
    rec = new_conversation_record(title="old")
    await store.put(part(scope="alice"), rec)

    order: list[str] = []

    controller = HistoryController(
        chat=_NavFakeChat(),  # type: ignore[arg-type]
        adapter=_NavFakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = part(scope="alice")

    async def hook(conv_id: str) -> None:
        still_there = await store.get(part(scope="alice"), conv_id)
        order.append("hook_before" if still_there is not None else "hook_after")

    controller.on_evict = hook

    await controller.delete(rec.id)

    assert order == ["hook_before"]
    assert await store.get(part(scope="alice"), rec.id) is None


# ---------------------------------------------------------------------------
# handle_navigate / handle_edit
# ---------------------------------------------------------------------------


class _TrackingChat:
    def __init__(self) -> None:
        self.messages_: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self.cleared: bool = False
        self.set_greeting_calls: list[Any] = []

    def _messages_for_bookmark(self) -> list[dict[str, Any]]:
        return list(self.messages_)

    async def _send_action(self, action: Any) -> None:
        self.actions.append(action)

    async def clear_messages(self) -> None:
        self.messages_ = []
        self.cleared = True

    @asynccontextmanager
    async def _destructive_history_mutation(self):
        yield

    async def _restore_bookmark_message(self, message_dict: Any) -> None:
        self.messages_.append(message_dict)

    async def set_greeting(self, greeting: Any) -> None:
        self.set_greeting_calls.append(greeting)


class _TrackingAdapter:
    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []

    def get_turns_json(self) -> list[dict[str, Any]]:
        return list(self.turns)

    def get_turns_grouped(self) -> list[list[dict[str, Any]]]:
        return [[t] for t in self.turns]

    def set_turns_json(self, turns: list[dict[str, Any]]) -> None:
        self.turns = list(turns)

    def client_info(self) -> dict[str, str]:
        return {}


def _make_branched_controller() -> tuple[
    HistoryController, _TrackingChat, _TrackingAdapter, _RecordingStore
]:
    chat = _TrackingChat()
    adapter = _TrackingAdapter()
    store = _RecordingStore()
    controller = HistoryController(
        chat=chat,  # type: ignore[arg-type]
        adapter=adapter,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = part()

    # Build a branched record:
    # n_0001(user:q1) -> n_0002(asst:a1) -> n_0003(user:q2) -> n_0004(asst:a2)
    #                                     -> n_0005(user:q2-edited) -> n_0006(asst:a2-new)
    rec = new_conversation_record(title="t")
    rec.append_linear([{"role": "user", "content": "q1"}], ui=[msg("user")])
    rec.append_linear(
        [{"role": "assistant", "content": "a1"}], ui=[msg("assistant")]
    )
    rec.append_linear([{"role": "user", "content": "q2"}], ui=[msg("user")])
    rec.append_linear(
        [{"role": "assistant", "content": "a2"}], ui=[msg("assistant")]
    )
    # Branch at n_0002: create sibling of n_0003
    branch_from(
        rec,
        "n_0002",
        [{"role": "user", "content": "q2-edited"}],
        ui=[msg("user")],
    )
    branch_from(
        rec,
        "n_0005",
        [{"role": "assistant", "content": "a2-new"}],
        ui=[msg("assistant")],
    )
    # Active path: [n_0001, n_0002, n_0005, n_0006]
    controller.record = rec
    adapter.turns = rec.path_turns()
    return controller, chat, adapter, store


@pytest.mark.anyio
async def test_handle_navigate_switches_to_prev_sibling():
    controller, chat, adapter, store = _make_branched_controller()

    # Message index 2 = n_0005 (the edited user message, sibling 2/2)
    # Navigate "prev" -> switch to n_0003's branch
    await controller.handle_navigate(2, "prev")

    assert controller.record is not None
    assert controller.record.current_leaf == "n_0004"
    assert [t["content"] for t in adapter.turns] == ["q1", "a1", "q2", "a2"]
    assert chat.cleared
    assert len(chat.messages_) == 4
    assert len(store.put_calls) == 1


@pytest.mark.anyio
async def test_handle_navigate_switches_to_next_sibling():
    controller, chat, adapter, store = _make_branched_controller()

    await controller.handle_navigate(2, "prev")
    chat.cleared = False
    store.put_calls.clear()

    # Now message index 2 = n_0003 (sibling 1/2); "next" -> back to n_0005's branch
    await controller.handle_navigate(2, "next")

    assert controller.record is not None
    assert controller.record.current_leaf == "n_0006"
    assert [t["content"] for t in adapter.turns] == [
        "q1",
        "a1",
        "q2-edited",
        "a2-new",
    ]


@pytest.mark.anyio
async def test_handle_navigate_noop_at_boundary():
    controller, chat, adapter, store = _make_branched_controller()

    # n_0005 is already the last sibling; "next" should be a no-op
    await controller.handle_navigate(2, "next")

    assert not chat.cleared
    assert store.put_calls == []


@pytest.mark.anyio
async def test_handle_navigate_invalid_direction_is_noop():
    controller, chat, adapter, store = _make_branched_controller()
    await controller.handle_navigate(2, "invalid")
    assert not chat.cleared
    assert store.put_calls == []


def _make_triple_branched_controller() -> tuple[
    HistoryController, _TrackingChat, _TrackingAdapter, _RecordingStore
]:
    """Same shape as _make_branched_controller, but the user message at the
    fork point has been edited twice -- three siblings at one fork point,
    not two -- to exercise a path no existing fixture covers."""
    chat = _TrackingChat()
    adapter = _TrackingAdapter()
    store = _RecordingStore()
    controller = HistoryController(
        chat=chat,  # type: ignore[arg-type]
        adapter=adapter,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = part()

    # n_0001(user:q1) -> n_0002(asst:a1) -> n_0003(user:q2)      -> n_0004(asst:a2)
    #                                     -> n_0005(user:q2-e1)  -> n_0006(asst:a2-e1)
    #                                     -> n_0007(user:q2-e2)  -> n_0008(asst:a2-e2)
    rec = new_conversation_record(title="t")
    rec.append_linear([{"role": "user", "content": "q1"}], ui=[msg("user")])
    rec.append_linear(
        [{"role": "assistant", "content": "a1"}], ui=[msg("assistant")]
    )
    rec.append_linear([{"role": "user", "content": "q2"}], ui=[msg("user")])
    rec.append_linear(
        [{"role": "assistant", "content": "a2"}], ui=[msg("assistant")]
    )
    branch_from(
        rec, "n_0002", [{"role": "user", "content": "q2-e1"}], ui=[msg("user")]
    )
    branch_from(
        rec,
        "n_0005",
        [{"role": "assistant", "content": "a2-e1"}],
        ui=[msg("assistant")],
    )
    branch_from(
        rec, "n_0002", [{"role": "user", "content": "q2-e2"}], ui=[msg("user")]
    )
    branch_from(
        rec,
        "n_0007",
        [{"role": "assistant", "content": "a2-e2"}],
        ui=[msg("assistant")],
    )
    # Active path: [n_0001, n_0002, n_0007, n_0008]
    controller.record = rec
    adapter.turns = rec.path_turns()
    return controller, chat, adapter, store


@pytest.mark.anyio
async def test_handle_navigate_cycles_through_three_siblings():
    controller, chat, adapter, store = _make_triple_branched_controller()

    # Message index 2 = n_0007 (3rd/last sibling, "q2-e2"). "prev" -> n_0005 ("q2-e1").
    await controller.handle_navigate(2, "prev")
    assert controller.record is not None
    assert controller.record.current_leaf == "n_0006"
    assert [t["content"] for t in adapter.turns] == [
        "q1",
        "a1",
        "q2-e1",
        "a2-e1",
    ]

    # From n_0005 (1st sibling), "prev" -> n_0003 ("q2", the original).
    await controller.handle_navigate(2, "prev")
    assert controller.record.current_leaf == "n_0004"
    assert [t["content"] for t in adapter.turns] == ["q1", "a1", "q2", "a2"]

    # n_0003 is the first sibling: "prev" here must be a no-op.
    store.put_calls.clear()
    await controller.handle_navigate(2, "prev")
    assert controller.record.current_leaf == "n_0004"
    assert store.put_calls == []

    # "next" twice walks back through n_0005 to n_0007, without corrupting
    # either earlier branch's content.
    await controller.handle_navigate(2, "next")
    assert controller.record.current_leaf == "n_0006"
    assert [t["content"] for t in adapter.turns] == [
        "q1",
        "a1",
        "q2-e1",
        "a2-e1",
    ]

    await controller.handle_navigate(2, "next")
    assert controller.record.current_leaf == "n_0008"
    assert [t["content"] for t in adapter.turns] == [
        "q1",
        "a1",
        "q2-e2",
        "a2-e2",
    ]

    # n_0007 is the last (3rd) sibling: "next" here must be a no-op.
    store.put_calls.clear()
    await controller.handle_navigate(2, "next")
    assert controller.record.current_leaf == "n_0008"
    assert store.put_calls == []


@pytest.mark.anyio
async def test_handle_edit_truncates_and_signals_resubmit():
    controller, chat, adapter, store = _make_branched_controller()
    chat.messages_ = [
        msg("user"),
        msg("assistant"),
        msg("user"),
        msg("assistant"),
    ]

    # Edit message at index 2 (n_0005) -> truncate to n_0002, signal resubmit
    await controller.handle_edit(2, "q2-re-edited")

    assert controller.record is not None
    assert controller.record.current_leaf == "n_0002"
    assert [t["content"] for t in adapter.turns] == ["q1", "a1"]
    assert chat.cleared
    assert len(chat.messages_) == 2
    update_actions = [
        a for a in chat.actions if a.get("type") == "update_input"
    ]
    assert len(update_actions) == 1
    assert update_actions[0]["value"] == "q2-re-edited"
    assert update_actions[0]["submit"] is True


@pytest.mark.anyio
async def test_handle_edit_first_message_truncates_to_root():
    controller, chat, adapter, store = _make_branched_controller()
    chat.messages_ = [
        msg("user"),
        msg("assistant"),
        msg("user"),
        msg("assistant"),
    ]

    await controller.handle_edit(0, "new-greeting")

    assert controller.record is not None
    assert controller.record.current_leaf is None
    assert adapter.turns == []
    assert chat.messages_ == []
    update_actions = [
        a for a in chat.actions if a.get("type") == "update_input"
    ]
    assert update_actions[0]["value"] == "new-greeting"


@pytest.mark.anyio
async def test_handle_edit_forks_from_a_multi_turn_tool_call_node():
    """Edit a message whose parent node is a grouped tool-call exchange
    (assistant-request/user-result/assistant-final stored as one node, one
    UI message) -- verifies node_id_for_message_index still maps to the
    right UI-facing message, and that truncating to that node preserves
    every turn in the group, not just its last one."""
    chat = _TrackingChat()
    adapter = _TrackingAdapter()
    store = _RecordingStore()
    controller = HistoryController(
        chat=chat,  # type: ignore[arg-type]
        adapter=adapter,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = part()

    # n_0001(user:weather?)                                  ui=[msg(user)]
    # n_0002(asst_req, user_result, asst_final -- one group)  ui=[msg(assistant)]
    # n_0003(user:thanks)                                     ui=[msg(user)]
    # n_0004(asst:you're welcome)                             ui=[msg(assistant)]
    rec = new_conversation_record(title="t")
    rec.append_linear(
        [{"role": "user", "content": "weather?"}], ui=[msg("user")]
    )
    rec.append_linear(
        [
            {"role": "assistant", "content": "tool_request"},
            {"role": "user", "content": "tool_result"},
            {"role": "assistant", "content": "sunny"},
        ],
        ui=[msg("assistant")],
    )
    rec.append_linear([{"role": "user", "content": "thanks"}], ui=[msg("user")])
    rec.append_linear(
        [{"role": "assistant", "content": "you're welcome"}],
        ui=[msg("assistant")],
    )
    controller.record = rec
    adapter.turns = rec.path_turns()
    chat.messages_ = [
        msg("user"),
        msg("assistant"),
        msg("user"),
        msg("assistant"),
    ]

    # Message index 2 = n_0003 ("thanks"); its parent is n_0002, the
    # 3-turn tool-call node.
    await controller.handle_edit(2, "thanks a lot")

    assert controller.record.current_leaf == "n_0002"
    # All 4 turns from n_0001 + n_0002 must survive -- not just n_0002's
    # last turn -- since path_turns() flattens per-node, not per-turn.
    assert [t["content"] for t in adapter.turns] == [
        "weather?",
        "tool_request",
        "tool_result",
        "sunny",
    ]
    assert chat.cleared
    assert len(chat.messages_) == 2  # n_0001's + n_0002's UI messages
    update_actions = [
        a for a in chat.actions if a.get("type") == "update_input"
    ]
    assert update_actions[0]["value"] == "thanks a lot"
    assert update_actions[0]["submit"] is True


@pytest.mark.anyio
async def test_handle_edit_with_attachments_forwards_them_with_set_mode():
    controller, chat, adapter, store = _make_branched_controller()
    chat.messages_ = [
        msg("user"),
        msg("assistant"),
        msg("user"),
        msg("assistant"),
    ]
    attachments = [
        {
            "mime": "image/png",
            "data_url": "data:image/png;base64,AAAA",
            "name": "pic.png",
            "size": 3,
        }
    ]

    await controller.handle_edit(2, "q2-re-edited", attachments)

    update_actions = [
        a for a in chat.actions if a.get("type") == "update_input"
    ]
    assert len(update_actions) == 1
    assert update_actions[0]["attachment_mode"] == "set"
    assert update_actions[0]["attachments"] == [
        {
            "mime": "image/png",
            "data_url": "data:image/png;base64,AAAA",
            "name": "pic.png",
            "size": 3,
        }
    ]


@pytest.mark.anyio
async def test_handle_edit_without_attachments_omits_attachment_fields():
    controller, chat, adapter, store = _make_branched_controller()
    chat.messages_ = [
        msg("user"),
        msg("assistant"),
        msg("user"),
        msg("assistant"),
    ]

    await controller.handle_edit(2, "q2-re-edited")

    update_actions = [
        a for a in chat.actions if a.get("type") == "update_input"
    ]
    assert "attachments" not in update_actions[0]
    assert "attachment_mode" not in update_actions[0]


@pytest.mark.anyio
async def test_handle_edit_rejects_unsupported_attachment_type():
    controller, chat, adapter, store = _make_branched_controller()
    chat.messages_ = [
        msg("user"),
        msg("assistant"),
        msg("user"),
        msg("assistant"),
    ]
    bad_attachments = [
        {
            "mime": "application/x-executable",
            "data_url": "data:application/x-executable;base64,AAA",
            "name": "bad.exe",
            "size": 3,
        }
    ]

    with pytest.raises(ValueError, match="unsupported MIME type"):
        await controller.handle_edit(2, "edited", bad_attachments)


@pytest.mark.anyio
async def test_switch_to_resends_sibling_metadata_for_branched_conversation():
    chat = _TrackingChat()
    adapter = _TrackingAdapter()
    store = InMemoryConversationStore()
    controller = HistoryController(
        chat=chat,  # type: ignore[arg-type]
        adapter=adapter,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = part()

    # Same branched shape as _make_branched_controller:
    # n_0001(user:q1) -> n_0002(asst:a1) -> n_0003(user:q2) -> n_0004(asst:a2)
    #                                     -> n_0005(user:q2-edited) -> n_0006(asst:a2-new)
    rec = new_conversation_record(title="branched")
    rec.append_linear([{"role": "user", "content": "q1"}], ui=[msg("user")])
    rec.append_linear(
        [{"role": "assistant", "content": "a1"}], ui=[msg("assistant")]
    )
    rec.append_linear([{"role": "user", "content": "q2"}], ui=[msg("user")])
    rec.append_linear(
        [{"role": "assistant", "content": "a2"}], ui=[msg("assistant")]
    )
    branch_from(
        rec,
        "n_0002",
        [{"role": "user", "content": "q2-edited"}],
        ui=[msg("user")],
    )
    branch_from(
        rec,
        "n_0005",
        [{"role": "assistant", "content": "a2-new"}],
        ui=[msg("assistant")],
    )
    await store.put(part(), rec)

    other = new_conversation_record(title="other")
    await store.put(part(), other)

    controller.record = rec
    adapter.turns = rec.path_turns()

    # Switch to a different conversation, then back -- simulates starting a
    # new chat and returning to the conversation with edited/branched messages.
    await controller.switch_to(other.id)
    chat.actions.clear()
    await controller.switch_to(rec.id)

    sibling_actions = [
        a for a in chat.actions if a["type"] == "update_siblings"
    ]
    assert len(sibling_actions) == 1
    # n_0005 (message index 2) is the active branch's fork point: 2nd of 2 siblings.
    assert sibling_actions[0]["data"] == {2: {"index": 1, "total": 2}}
