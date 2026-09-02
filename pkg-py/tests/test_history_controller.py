# HistoryController's session-coupled behavior (switch_to, on_response, etc.)
# is covered by Playwright e2e tests (Task 13). This file tests the pure
# helpers that HistoryController delegates to.

import asyncio
import copy
import os
import signal
import subprocess
import sys
import textwrap
import warnings
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Literal, cast
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from _history_test_helpers import branch_from
from pydantic import BaseModel
from shiny import Inputs, reactive
from shiny.module import ResolvedId
from shiny.session import session_context
from shinychat import Chat
from shinychat._attachments import Attachment
from shinychat._chat_transcript import ChatTranscript, TranscriptEntry
from shinychat._chat_types import ChatMessage, StoredMessage, StoredSegment
from shinychat._history import (
    HistoryController,
    HistoryInputIds,
    HistoryOptions,
    StatePathContext,
    do_bookmark_with_cleanup,
    extend_record_linear,
)
from shinychat._history_client import TurnsAdapter
from shinychat._history_store import (
    ConversationPartition,
    ConversationStore,
    FileConversationStore,
    InMemoryConversationStore,
)
from shinychat._history_types import (
    MAX_SCHEMA_VERSION,
    CapturedMessage,
    ConversationRecord,
    ConversationRecordV2,
    StateEntry,
    UnsupportedSchemaVersionError,
    new_conversation_record,
    new_conversation_record_v2,
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


class _InactiveMessageStream:
    def status(self) -> str:
        return "success"


class _FakeChat:
    def __init__(self) -> None:
        self.actions: list[dict[str, Any]] = []
        self.set_greeting_calls: list[Any] = []
        self.destructive_preflight_calls = 0
        self.restored_messages: list[dict[str, Any]] = []
        self.restored_icons: list[str | None] = []
        self.messages: list[Any] = []
        self.clear_messages_calls = 0
        self.published_inputs: list[StoredMessage] = []
        self._transcript = ChatTranscript()
        self.latest_message_stream = _InactiveMessageStream()

    def _messages_for_bookmark(self) -> list[Any]:
        return self.messages

    def _messages_for_history(self) -> list[Any]:
        return self._messages_for_bookmark()

    async def _send_action(self, action: Any) -> None:
        self.actions.append(action)

    async def clear_messages(self) -> None:
        self.clear_messages_calls += 1
        self.messages.clear()
        self._transcript.replace([])

    @asynccontextmanager
    async def _destructive_history_mutation(self, *, block_input: bool = False):
        del block_input
        self.destructive_preflight_calls += 1
        yield

    async def _restore_bookmark_message(
        self, message_dict: Any, *, icon: str | None = None
    ) -> None:
        self.restored_messages.append(message_dict)
        self.restored_icons.append(icon)

    async def set_greeting(self, greeting: Any) -> None:
        self.set_greeting_calls.append(greeting)

    def _publish_accepted_user_input(self, message: StoredMessage) -> None:
        self.published_inputs.append(message)


class _RealChatSession:
    ns = ResolvedId("")
    app: object = None
    id = "history-switch-input-session"

    def __init__(self) -> None:
        self.input = Inputs({}, ns=ResolvedId)

    async def send_custom_message(self, _type: str, _message: Any) -> None:
        pass

    def _process_ui(self, ui: Any) -> dict[str, Any]:
        return {"html": str(ui), "deps": []}

    def _send_message_sync(self, message: Any) -> None:
        pass

    async def _unhandled_error(self, error: Any) -> None:
        pass

    def on_ended(self, _callback: object) -> Callable[[], None]:
        return lambda: None

    def on_destroy(self, _callback: object) -> None:
        pass

    def _increment_busy_count(self) -> None:
        pass

    def _decrement_busy_count(self) -> None:
        pass


class _RealHistorySession(_RealChatSession):
    def __init__(self) -> None:
        super().__init__()
        self.bookmark = type(
            "Bookmark",
            (),
            {
                "exclude": [],
                "store": "disable",
                "_restore_context": None,
            },
        )()

    def is_stub_session(self) -> bool:
        return False

    def root_scope(self) -> "_RealHistorySession":
        return self


class _SameFlushHistoryClient:
    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []
        self.stream_calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.stream_started = asyncio.Event()
        self.release_stream = asyncio.Event()

    def get_turns(self) -> list[dict[str, Any]]:
        return list(self.turns)

    def set_turns(self, turns: list[dict[str, Any]]) -> None:
        self.turns = list(turns)

    async def stream_async(
        self, text: str, *contents: Any, **kwargs: Any
    ) -> Any:
        self.stream_calls.append((text, contents, kwargs))

        async def response() -> Any:
            self.stream_started.set()
            await self.release_stream.wait()
            if False:
                yield None

        return response()


class _FakeAdapter:
    def __init__(self, *, chatlas: bool = False) -> None:
        self.chatlas = chatlas
        self.turns: list[dict[str, Any]] = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        self.system_turns: list[dict[str, Any]] = [
            {"role": "system", "content": "be precise"},
            *self.turns,
        ]

    def get_turns_json(
        self, *, include_system_prompt: bool = False
    ) -> list[dict[str, Any]]:
        turns = getattr(
            self,
            "turns",
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ],
        )
        if include_system_prompt:
            return list(
                getattr(
                    self,
                    "system_turns",
                    [{"role": "system", "content": "be precise"}, *turns],
                )
            )
        return list(turns)

    def is_chatlas(self) -> bool:
        return getattr(self, "chatlas", False)

    def get_turns_grouped(self) -> list[list[Any]]:
        return [[t] for t in self.get_turns_json()]

    def set_turns_json(self, turns: list[Any]) -> None:
        self.turns = list(turns)

    def client_info(self) -> dict[str, Any]:
        return {}


class _TrackingFakeAdapter(_FakeAdapter):
    def __init__(self, *, chatlas: bool = False) -> None:
        super().__init__(chatlas=chatlas)
        self.set_calls: list[list[dict[str, Any]]] = []

    def set_turns_json(self, turns: list[Any]) -> None:
        self.set_calls.append(list(turns))
        super().set_turns_json(turns)


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
    adapter: _FakeAdapter | None = None,
) -> tuple[HistoryController, Any]:
    resolved_store = store if store is not None else _RecordingStore()
    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=adapter or _FakeAdapter(),  # type: ignore[arg-type]
        store=resolved_store,
        title_fn=None,
        title_enabled=False,
        client=None,
        save_callbacks=save_callbacks,
        use_exchange_tree=use_exchange_tree,
    )
    controller.partition = part()
    return controller, resolved_store


@pytest.mark.anyio
async def test_history_update_advertises_completion_v1() -> None:
    controller, _ = _make_controller()

    await controller.send_history_update()

    assert cast(_FakeChat, controller.chat).actions == [
        {
            "type": "history_update",
            "enabled": True,
            "conversations": [],
            "active_id": None,
            "transition_protocol": "completion-v1",
        }
    ]


@pytest.mark.anyio
async def test_v2_history_update_advertises_completion_v2() -> None:
    controller, _ = _make_controller(use_exchange_tree=True)

    await controller.send_history_update()

    assert cast(_FakeChat, controller.chat).actions == [
        {
            "type": "history_update",
            "enabled": True,
            "conversations": [],
            "active_id": None,
            "transition_protocol": "completion-v2",
        }
    ]


def _stored_message(role: str, content: str) -> StoredMessage:
    return StoredMessage(
        role=role,  # type: ignore[arg-type]
        segments=[StoredSegment(content=content, content_type="markdown")],
    )


@pytest.mark.parametrize(
    "turn",
    [
        {2: "two"},
        {"outer": [{"inner": {3: "three"}}]},
    ],
)
def test_v2_recorder_rejects_non_string_mapping_keys_recursively(
    turn: dict[Any, Any],
):
    from shinychat._history import _ExchangeRecorder

    with pytest.raises(ValueError, match="Non-string mapping key"):
        _ExchangeRecorder._canonical_turns([turn])


def test_v2_recorder_string_key_reordering_keeps_a_stable_prefix():
    from shinychat._history import _ExchangeRecorder

    _, baseline = _ExchangeRecorder._canonical_turns(
        [{"one": "one", "two": {"nested": "value"}}]
    )
    _, current = _ExchangeRecorder._canonical_turns(
        [
            {"two": {"nested": "value"}, "one": "one"},
            {"role": "assistant", "content": "later"},
        ]
    )

    assert current[: len(baseline)] == baseline


def test_v2_recorder_rejects_non_json_turn_values():
    from shinychat._history import _ExchangeRecorder

    with pytest.raises(TypeError):
        _ExchangeRecorder._canonical_turns([{"value": object()}])


@pytest.mark.anyio
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
async def test_v2_recorder_rejects_nonfinite_turn_values_before_file_store(
    tmp_path: Path, value: float
):
    from shinychat._history_store import FileConversationStore

    adapter = _FakeAdapter()
    adapter.turns = [{"value": value}]
    store = FileConversationStore(tmp_path)
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
        adapter=adapter,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    with pytest.raises(ValueError, match="Out of range float values"):
        await transcript.record_accepted_input_and_notify(
            _stored_message("user", "one")
        )

    assert await store.list(part()) == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "turn",
    [
        {2: "two"},
        {"outer": [{"inner": {3: "three"}}]},
    ],
)
async def test_v2_recorder_rejects_non_string_keys_before_file_store(
    tmp_path: Path, turn: dict[Any, Any]
):
    from shinychat._history_store import FileConversationStore

    adapter = _FakeAdapter()
    adapter.turns = [turn]
    store = FileConversationStore(tmp_path)
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
        adapter=adapter,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    with pytest.raises(ValueError, match="Non-string mapping key"):
        await transcript.record_accepted_input_and_notify(
            _stored_message("user", "one")
        )

    assert await store.list(part()) == []


@pytest.mark.anyio
async def test_chatlas_lazy_second_stream_is_rejected_before_turn_mutation():
    chatlas = pytest.importorskip("chatlas")

    provider = MagicMock()
    provider.name = "deterministic"
    provider.model = "deterministic"
    client = chatlas.Chat(provider)
    transcript = ChatTranscript()

    first_exchange = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "first")
    )
    first_response = await client.stream_async("first")
    assert client.get_turns() == []
    assert provider.chat_perform_async.call_count == 0

    await transcript.start_stream(
        stream_id="first-stream",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=first_exchange,
        send=_sent,
    )

    second_exchange = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "second")
    )
    second_response = await client.stream_async("second")
    assert client.get_turns() == []

    with pytest.raises(
        RuntimeError,
        match="Cannot start a second message stream",
    ):
        await transcript.start_stream(
            stream_id="second-stream",
            entry=TranscriptEntry(message=_stored_message("assistant", "")),
            owner_task=None,
            exchange_id=second_exchange,
            send=_sent,
        )

    assert client.get_turns() == []
    assert provider.chat_perform_async.call_count == 0

    await transcript.end_stream(
        stream_id="first-stream",
        status=None,
        error=None,
        send=_sent,
    )
    await first_response.aclose()
    await second_response.aclose()


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
    assert [
        message.as_stored_message().content for message in node.messages
    ] == ["hi"]

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
async def test_v2_active_rename_survives_later_capture_in_file_store(
    tmp_path: Path,
) -> None:
    from shinychat._history_store import FileConversationStore

    store = FileConversationStore(tmp_path)
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
    )

    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question")
    )
    assert recorder.record is not None
    await controller.rename(recorder.record.id, "Renamed")
    await transcript.append(
        TranscriptEntry(message=_stored_message("assistant", "answer")),
        exchange_id=exchange_id,
        send=_sent,
    )

    stored = await store.get(part(), recorder.record.id)
    assert isinstance(stored, ConversationRecordV2)
    assert stored.title == "Renamed"
    assert stored.title_source == "user"
    assert [
        message.as_stored_message().content
        for message in stored.nodes[exchange_id].messages
    ] == ["answer"]


@pytest.mark.anyio
async def test_v2_inactive_rename_does_not_affect_active_recorder_capture() -> (
    None
):
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    inactive = new_conversation_record_v2(
        title="inactive",
        id="c_inactive",
        client_info={},
    )
    await store.put(part(), inactive)
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
    )

    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "active question")
    )
    assert recorder.record is not None
    active_id = recorder.record.id

    await controller.rename(inactive.id, "Renamed inactive")
    await transcript.append(
        TranscriptEntry(message=_stored_message("assistant", "active answer")),
        exchange_id=exchange_id,
        send=_sent,
    )

    stored_inactive = await store.get(part(), inactive.id)
    stored_active = await store.get(part(), active_id)
    assert isinstance(stored_inactive, ConversationRecordV2)
    assert isinstance(stored_active, ConversationRecordV2)
    assert stored_inactive.title == "Renamed inactive"
    assert stored_inactive.title_source == "user"
    assert stored_active.title == "active question"
    assert [
        message.as_stored_message().content
        for message in stored_active.nodes[exchange_id].messages
    ] == ["active answer"]

    await controller.rename("c_missing", "Missing")
    assert await store.get(part(), "c_missing") is None


@pytest.mark.anyio
async def test_v2_values_capture_response_save_switch_new_and_restore() -> None:
    store = InMemoryConversationStore()
    current_value = "response"
    saved_values: list[str] = []
    restored_values: list[dict[str, Any]] = []

    def save_callback(values: dict[str, Any]) -> None:
        values["value"] = current_value
        saved_values.append(current_value)

    controller, _ = _make_controller(
        store=store,
        save_callbacks=[save_callback],
        use_exchange_tree=True,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None

    def restore_callback(values: dict[str, Any]) -> None:
        assert recorder.record is target
        restored_values.append(dict(values))

    controller._restore_callbacks.append(restore_callback)
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "source")
    )
    assert recorder.record is not None
    source_id = recorder.record.id

    await controller.on_response()
    source = await store.get(part(), source_id)
    assert isinstance(source, ConversationRecordV2)
    assert source.values == {"value": "response"}

    current_value = "save"
    assert await controller.save()
    assert source.values == {"value": "save"}

    target = new_conversation_record_v2(
        title="target",
        id="c_target",
        client_info={},
    )
    target.values = {"restored": "target"}
    await store.put(part(), target)

    current_value = "switch"
    await controller.switch_to(target.id)
    assert source.values == {"value": "switch"}
    assert restored_values == [{"restored": "target"}]

    current_value = "new"
    await controller.new_chat()
    assert target.values == {"value": "new"}
    assert saved_values == ["response", "save", "switch", "new"]


@pytest.mark.anyio
async def test_v2_initial_programmatic_message_persists_and_publishes_metadata():
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_message_committed=recorder.message_committed,
    )
    controller.send_history_update = AsyncMock()  # type: ignore[method-assign]

    assert await transcript.append(
        TranscriptEntry(message=_stored_message("assistant", "notice")),
        exchange_id=None,
        send=_sent,
    )

    assert recorder.record is not None
    stored = await store.get(part(), recorder.record.id)
    assert isinstance(stored, ConversationRecordV2)
    assert [
        message.as_stored_message().content
        for node in stored.nodes.values()
        for message in node.messages
    ] == ["notice"]
    controller.send_history_update.assert_awaited_once()


@pytest.mark.anyio
async def test_v2_initial_programmatic_stream_persists_without_chunk_metadata():
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )
    controller.send_history_update = AsyncMock()  # type: ignore[method-assign]

    assert await transcript.start_stream(
        stream_id="stream",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=None,
        send=_sent,
    )

    assert recorder.record is not None
    stored = await store.get(part(), recorder.record.id)
    assert isinstance(stored, ConversationRecordV2)
    controller.send_history_update.assert_awaited_once()

    assert await transcript.transition_stream(
        stream_id="stream",
        source_segments=[],
        message=_stored_message("assistant", "partial"),
        operation="append",
        send=_sent,
    )
    stored = await store.get(part(), recorder.record.id)
    assert isinstance(stored, ConversationRecordV2)
    assert [
        message.as_stored_message().content
        for node in stored.nodes.values()
        for message in node.messages
    ] == ["partial"]
    controller.send_history_update.assert_awaited_once()

    assert await transcript.end_stream(
        stream_id="stream",
        status=None,
        error=None,
        send=_sent,
    )
    stored = await store.get(part(), recorder.record.id)
    assert isinstance(stored, ConversationRecordV2)
    controller.send_history_update.assert_awaited_once()


@pytest.mark.anyio
async def test_v2_stream_chunks_are_durable_without_metadata_until_terminal(
    tmp_path: Path,
) -> None:
    from shinychat._history_store import FileConversationStore

    store = FileConversationStore(tmp_path)
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
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
    controller.send_history_update = AsyncMock()  # type: ignore[method-assign]

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

    stored = await store.get(part(), recorder.record.id)  # type: ignore[union-attr]
    assert isinstance(stored, ConversationRecordV2)
    assert [
        message.as_stored_message().content
        for message in stored.nodes[exchange_id].messages
    ] == ["partial"]
    controller.send_history_update.assert_not_awaited()

    await transcript.end_stream(
        stream_id="stream",
        status=None,
        error=None,
        send=_sent,
    )
    controller.send_history_update.assert_not_awaited()

    await controller.on_response()
    controller.send_history_update.assert_awaited_once()


@pytest.mark.anyio
async def test_v2_restore_marks_exact_record_published_after_callback() -> None:
    controller, _ = _make_controller(use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    target = _restore_target()
    published: list[str | None] = []

    async def active_id_callback(record_id: str | None) -> None:
        assert recorder.record is target
        assert recorder._active_id_published_for is None
        published.append(record_id)

    controller._active_id.set("c_previous")
    controller.on_active_id_change = active_id_callback

    await controller.replay_exchange_record(target)

    assert published == [target.id]
    assert recorder._active_id_published_for is target

    await recorder.message_committed(
        None,
        TranscriptEntry(message=_stored_message("assistant", "continued")),
    )
    assert published == [target.id]


@pytest.mark.anyio
async def test_v2_active_rename_waits_for_recorder_capture_lock() -> None:
    class BlockingStore(InMemoryConversationStore):
        def __init__(self) -> None:
            super().__init__()
            self.block_id: str | None = None
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def put(
            self, partition: ConversationPartition, record: Any
        ) -> None:
            if record.id == self.block_id:
                self.block_id = None
                self.entered.set()
                await self.release.wait()
            await super().put(partition, record)

    store = BlockingStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
    )
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question")
    )
    assert recorder.record is not None
    source = recorder.record
    target = new_conversation_record_v2(
        title="target",
        id="c_target",
        client_info={},
    )
    await store.put(part(), target)

    store.block_id = source.id
    switch = asyncio.create_task(controller.switch_to(target.id))
    await store.entered.wait()
    rename = asyncio.create_task(controller.rename(source.id, "Renamed source"))
    await asyncio.sleep(0)
    assert not rename.done()

    store.release.set()
    await switch
    await rename

    stored_source = await store.get(part(), source.id)
    stored_target = await store.get(part(), target.id)
    assert isinstance(stored_source, ConversationRecordV2)
    assert isinstance(stored_target, ConversationRecordV2)
    assert stored_source.title == "Renamed source"
    assert stored_target.title == "target"
    assert recorder.record is target
    assert controller._active_id_now() == target.id


@pytest.mark.anyio
async def test_v2_switch_reloads_target_after_inactive_rename() -> None:
    class SnapshotStore(InMemoryConversationStore):
        def __init__(self) -> None:
            super().__init__()
            self.blocked_target: str | None = None
            self.target_lookup_entered = asyncio.Event()
            self.release_target_lookup = asyncio.Event()

        async def get(
            self, partition: ConversationPartition, conv_id: str
        ) -> Any:
            record = await super().get(partition, conv_id)
            snapshot = (
                record.model_copy(deep=True) if record is not None else None
            )
            if conv_id == self.blocked_target:
                self.blocked_target = None
                self.target_lookup_entered.set()
                await self.release_target_lookup.wait()
            return snapshot

        async def put(
            self, partition: ConversationPartition, record: Any
        ) -> None:
            await super().put(partition, record.model_copy(deep=True))

    store = SnapshotStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    source = new_conversation_record_v2(
        title="source",
        id="c_source",
        client_info={},
    )
    target = new_conversation_record_v2(
        title="target",
        id="c_target",
        client_info={},
    )
    recorder.record = source
    controller._active_id.set(source.id)
    await store.put(part(), source)
    await store.put(part(), target)

    store.blocked_target = target.id
    switch = asyncio.create_task(controller.switch_to(target.id))
    await store.target_lookup_entered.wait()
    await controller.rename(target.id, "Renamed target")
    store.release_target_lookup.set()
    await switch

    await recorder.message_committed(
        None,
        TranscriptEntry(message=_stored_message("assistant", "captured")),
    )

    stored_target = await store.get(part(), target.id)
    assert isinstance(stored_target, ConversationRecordV2)
    assert recorder.record is not None
    assert recorder.record.title == "Renamed target"
    assert stored_target.title == "Renamed target"


@pytest.mark.anyio
async def test_v2_restore_materializes_turn_path_once_and_resets_baseline():
    adapter = _TrackingFakeAdapter()
    controller, _ = _make_controller(
        use_exchange_tree=True,
        adapter=adapter,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = new_conversation_record_v2(
        title="restore",
        id="c_restore",
        client_info={},
    )
    root = record.nodes["n_0000"]
    root.state["shinychat:turns"] = StateEntry(
        kind="unsupported",
        version=2,
        mode="snapshot",
        data=[{"role": "system", "content": "superseded"}],
    )
    record.open_exchange("n_0001", _stored_message("user", "first"))
    record.nodes["n_0001"].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[{"role": "user", "content": "first"}],
    )
    snapshot_node = record.open_inputless_exchange()
    record.nodes[snapshot_node].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[{"role": "assistant", "content": "replacement"}],
    )
    leaf = record.open_inputless_exchange()
    record.nodes[leaf].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[{"role": "user", "content": "after snapshot"}],
    )

    await controller.replay_exchange_record(record)

    expected = [
        {"role": "assistant", "content": "replacement"},
        {"role": "user", "content": "after snapshot"},
    ]
    assert adapter.set_calls == [expected]
    assert adapter.turns == expected
    assert recorder.record is record
    assert controller.record is None

    adapter.turns.append({"role": "assistant", "content": "next delta"})
    await recorder.accepted_input("n_0004", _stored_message("user", "next"))
    captured = record.nodes[leaf].state["shinychat:turns"]
    assert captured.mode == "delta"
    assert captured.data == [
        {"role": "user", "content": "after snapshot"},
        {"role": "assistant", "content": "next delta"},
    ]


@pytest.mark.anyio
async def test_v2_restore_live_bootstrap_skips_only_root_snapshot():
    adapter = _TrackingFakeAdapter()
    adapter.turns = [{"role": "system", "content": "live"}]
    controller, _ = _make_controller(
        use_exchange_tree=True,
        adapter=adapter,
    )
    controller.restore_bootstrap = "live"
    record = new_conversation_record_v2(
        title="restore",
        id="c_live",
        client_info={},
    )
    record.nodes["n_0000"].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[{"role": "system", "content": "recorded root"}],
    )
    record.open_exchange("n_0001", _stored_message("user", "first"))
    record.nodes["n_0001"].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[{"role": "user", "content": "first"}],
    )
    snapshot_node = record.open_inputless_exchange()
    record.nodes[snapshot_node].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[{"role": "assistant", "content": "later snapshot"}],
    )

    await controller.replay_exchange_record(record)

    assert adapter.set_calls == [
        [{"role": "assistant", "content": "later snapshot"}]
    ]


@pytest.mark.anyio
async def test_v2_restore_live_bootstrap_waits_for_admission_and_recorder_lock():
    class _ObservedRestoreLock:
        def __init__(self) -> None:
            self._lock = asyncio.Lock()
            self.restore_attempted = asyncio.Event()
            self.restore_acquired = asyncio.Event()

        async def acquire(self) -> bool:
            return await self._lock.acquire()

        def release(self) -> None:
            self._lock.release()

        def locked(self) -> bool:
            return self._lock.locked()

        async def __aenter__(self) -> "_ObservedRestoreLock":
            self.restore_attempted.set()
            await self._lock.acquire()
            self.restore_acquired.set()
            return self

        async def __aexit__(self, *args: Any) -> None:
            self._lock.release()

    adapter = _TrackingFakeAdapter()
    adapter.turns = [{"role": "system", "content": "before admission"}]
    controller, _ = _make_controller(
        use_exchange_tree=True,
        adapter=adapter,
    )
    controller.restore_bootstrap = "live"
    recorder = controller._exchange_recorder
    assert recorder is not None
    observed_lock = _ObservedRestoreLock()
    recorder._lock = observed_lock  # type: ignore[assignment]
    original_get_turns = adapter.get_turns_json
    capture_after_restore_lock: list[bool] = []

    def get_turns_json(
        *, include_system_prompt: bool = False
    ) -> list[dict[str, Any]]:
        capture_after_restore_lock.append(
            observed_lock.restore_acquired.is_set()
        )
        return original_get_turns(include_system_prompt=include_system_prompt)

    adapter.get_turns_json = get_turns_json  # type: ignore[method-assign]
    record = new_conversation_record_v2(
        title="restore",
        id="c_live",
        client_info={},
    )
    record.nodes["n_0000"].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[{"role": "system", "content": "recorded root"}],
    )
    entered_admission = asyncio.Event()
    release_admission = asyncio.Event()
    fake_chat = cast(_FakeChat, controller.chat)

    @asynccontextmanager
    async def blocked_admission():
        entered_admission.set()
        await release_admission.wait()
        yield

    fake_chat._destructive_history_mutation = blocked_admission  # type: ignore[method-assign]
    await recorder._lock.acquire()
    try:
        restore_task = asyncio.create_task(
            controller.replay_exchange_record(record)
        )
        await entered_admission.wait()
        assert adapter.set_calls == []

        release_admission.set()
        await observed_lock.restore_attempted.wait()
        adapter.turns = [{"role": "system", "content": "after admission"}]
        assert adapter.set_calls == []

        observed_lock.release()
        await restore_task
    finally:
        if observed_lock.locked():
            observed_lock.release()

    assert capture_after_restore_lock == [True]
    assert adapter.set_calls == [
        [{"role": "system", "content": "after admission"}]
    ]


@pytest.mark.anyio
async def test_v2_switch_uses_restore_transaction_and_controller_active_id():
    adapter = _TrackingFakeAdapter()
    store = InMemoryConversationStore()
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
        adapter=adapter,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    existing = new_conversation_record_v2(
        title="existing",
        id="c_existing",
        client_info={},
    )
    target = new_conversation_record_v2(
        title="target",
        id="c_target",
        client_info={},
    )
    target.nodes["n_0000"].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[{"role": "system", "content": "restored"}],
    )
    target.open_exchange("n_0001", _stored_message("user", "restore me"))
    await store.put(part(), target)
    recorder.record = existing
    controller._active_id.set(existing.id)

    await controller.switch_to(target.id)

    fake_chat = cast(_FakeChat, controller.chat)
    assert recorder.record is target
    assert [
        message["segments"][0]["content"]
        for message in fake_chat.restored_messages
    ] == ["restore me"]
    assert adapter.set_calls == [[{"role": "system", "content": "restored"}]]
    assert fake_chat.actions[-1]["active_id"] == "c_target"


@pytest.mark.anyio
async def test_v2_switch_rejects_real_chat_input_during_save_and_restore(
    request: pytest.FixtureRequest,
) -> None:
    class BlockingStore(InMemoryConversationStore):
        def __init__(self) -> None:
            super().__init__()
            self.block_id: str | None = None
            self.source_save_entered = asyncio.Event()
            self.release_source_save = asyncio.Event()
            self.put_ids: list[str] = []

        async def put(
            self, partition: ConversationPartition, record: Any
        ) -> None:
            self.put_ids.append(record.id)
            if record.id == self.block_id:
                self.block_id = None
                self.source_save_entered.set()
                await self.release_source_save.wait()
            await super().put(partition, record)

    store = BlockingStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None

    session = _RealChatSession()
    session.input["history_switch_input_user_input"] = reactive.Value()
    with session_context(cast(Any, session)):
        chat = Chat("history_switch_input", history=False)
    switch: asyncio.Task[None] | None = None

    def cleanup_chat() -> None:
        if switch is not None and not switch.done():
            switch.cancel()
        chat.destroy()

    request.addfinalizer(cleanup_chat)
    controller.chat = chat  # type: ignore[assignment]
    recorder_inputs: list[str] = []
    original_accepted_input = recorder.accepted_input

    async def record_accepted_input(
        exchange_id: str, message: StoredMessage
    ) -> None:
        recorder_inputs.append(message.content)
        await original_accepted_input(exchange_id, message)

    chat._transcript.set_capture_callbacks(
        on_accepted_input=record_accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )
    provider_calls: list[str] = []
    raw_input_errors: list[BaseException] = []

    @chat.on_user_submit
    async def _provider_input(text: str) -> None:
        provider_calls.append(text)

    async def capture_raw_input_error(error: BaseException) -> None:
        raw_input_errors.append(error)

    chat._raise_exception = capture_raw_input_error  # type: ignore[method-assign]
    await reactive.flush()
    await chat._record_accepted_user_input_with_capture(
        ChatMessage(content="source", role="user")
    )
    await reactive.flush()
    assert provider_calls == ["source"]
    assert recorder_inputs == ["source"]
    assert recorder.record is not None
    source = recorder.record
    target = new_conversation_record_v2(
        title="target",
        id="c_target",
        client_info={},
    )
    await store.put(part(), target)

    clear_started = asyncio.Event()
    release_clear = asyncio.Event()
    original_clear_messages = chat.clear_messages

    async def blocked_clear_messages() -> None:
        clear_started.set()
        await release_clear.wait()
        await original_clear_messages()

    chat.clear_messages = blocked_clear_messages  # type: ignore[method-assign]

    async def assert_rejected(content: str) -> None:
        original_as_stored_message = chat._as_stored_message
        input_value = cast(Any, session.input[chat.user_input_id])

        def unexpected_conversion(_message: ChatMessage) -> StoredMessage:
            raise AssertionError("blocked input must not be converted")

        chat._as_stored_message = unexpected_conversion  # type: ignore[method-assign]
        try:
            with pytest.raises(
                RuntimeError,
                match="Cannot accept user input while switching conversations",
            ):
                chat._record_accepted_user_input(
                    ChatMessage(content=f"{content} sync", role="user")
                )
            with pytest.raises(
                RuntimeError,
                match="Cannot accept user input while switching conversations",
            ):
                await chat._record_accepted_user_input_with_capture(
                    ChatMessage(content=content, role="user")
                )
            error_count = len(raw_input_errors)
            input_value.set({"text": content, "attachments": []})
            await reactive.flush()
            errors = raw_input_errors[error_count:]
            assert len(errors) == 1
            assert isinstance(errors[0], RuntimeError)
            assert (
                str(errors[0])
                == "Cannot accept user input while switching conversations."
            )
        finally:
            chat._as_stored_message = original_as_stored_message  # type: ignore[method-assign]

    store.block_id = source.id
    switch = asyncio.create_task(controller.switch_to(target.id))
    await store.source_save_entered.wait()

    source_transcript = chat._transcript.read()
    with reactive.isolate():
        latest_before = chat.user_input()
        normal_submission_before = chat._normal_user_submission()
    put_count = len(store.put_ids)
    await assert_rejected("blocked during source save")
    assert chat._transcript.read() == source_transcript
    with reactive.isolate():
        assert chat.user_input() == latest_before
        assert chat._normal_user_submission() == normal_submission_before
    assert provider_calls == ["source"]
    assert recorder_inputs == ["source"]
    assert len(store.put_ids) == put_count
    assert recorder.record is source

    store.release_source_save.set()
    await clear_started.wait()

    stored_source = await store.get(part(), source.id)
    assert isinstance(stored_source, ConversationRecordV2)
    assert [
        node.input.content
        for node in stored_source.nodes.values()
        if node.input is not None
    ] == ["source"]

    put_count = len(store.put_ids)
    await assert_rejected("blocked during restore")
    assert chat._transcript.read() == source_transcript
    with reactive.isolate():
        assert chat.user_input() == latest_before
        assert chat._normal_user_submission() == normal_submission_before
    assert provider_calls == ["source"]
    assert recorder_inputs == ["source"]
    assert len(store.put_ids) == put_count
    assert recorder.record is source

    release_clear.set()
    await switch

    stored_target = await store.get(part(), target.id)
    assert isinstance(stored_target, ConversationRecordV2)
    assert recorder.record is target
    assert [
        node.input.content
        for node in stored_target.nodes.values()
        if node.input is not None
    ] == []
    assert chat._transcript.read() == ()
    assert provider_calls == ["source"]
    assert recorder_inputs == ["source"]

    blocked_error_count = len(raw_input_errors)
    cast(Any, session.input[chat.user_input_id]).set(
        {"text": "accepted after switch", "attachments": []}
    )
    await reactive.flush()

    assert len(raw_input_errors) == blocked_error_count
    assert provider_calls == ["source", "accepted after switch"]
    stored_target = await store.get(part(), target.id)
    assert isinstance(stored_target, ConversationRecordV2)
    assert [
        node.input.content
        for node in stored_target.nodes.values()
        if node.input is not None
    ] == ["accepted after switch"]
    with reactive.isolate():
        latest_input = chat.user_input()
        assert latest_input is not None
        assert latest_input.text == "accepted after switch"


@pytest.mark.anyio
async def test_v2_same_flush_input_and_history_selection_preserves_source_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id = ResolvedId("same_flush_source")
    history_ids = HistoryInputIds.for_chat(chat_id)
    session = _RealHistorySession()
    session.input[ResolvedId(f"{chat_id}_user_input")] = reactive.Value()
    session.input[history_ids.select] = reactive.Value()
    client = _SameFlushHistoryClient()
    store = InMemoryConversationStore()
    attachment = Attachment.from_data(
        b"notes", mime="text/plain", name="notes.txt"
    )
    public_calls: list[tuple[str, list[Attachment]]] = []
    chat: Chat | None = None

    monkeypatch.setattr("shinychat._history._EXCHANGE_TREE_HISTORY_V2", True)
    try:
        with session_context(cast(Any, session)):
            chat = Chat(
                str(chat_id),
                client=cast(Any, client),
                history=HistoryOptions(
                    restore_mode="none",
                    scope="same-flush-source",
                    store=store,
                    title=None,
                ),
            )
        await reactive.flush()

        controller = chat.history._controller
        assert controller is not None
        assert controller.partition is not None
        recorder = controller._exchange_recorder
        assert recorder is not None
        target = new_conversation_record_v2(
            title="target",
            id="c_target",
            client_info={},
        )
        target.open_exchange("n_0001", _stored_message("user", "target input"))
        await store.put(controller.partition, target)
        target_before = target.model_dump(mode="json")

        @chat.on_user_submit
        async def _public_handler(
            text: str, attachments: list[Attachment]
        ) -> None:
            public_calls.append((text, attachments))

        cast(Any, session.input[chat.user_input_id]).set(
            {"text": "source input", "attachments": [attachment], "seq": 1}
        )
        cast(Any, session.input[history_ids.select]).set({"id": target.id})
        await reactive.flush()
        await asyncio.wait_for(client.stream_started.wait(), timeout=1)

        source = recorder.record
        assert source is not None
        assert controller._active_id_now() == source.id
        assert [
            (node.input.content, node.input.attachments)
            for node in source.nodes.values()
            if node.input is not None
        ] == [("source input", [attachment])]
        assert public_calls == [("source input", [attachment])]
        assert len(client.stream_calls) == 1
        provider_text, provider_contents, provider_kwargs = client.stream_calls[0]
        assert provider_text == "source input"
        assert provider_kwargs["content"] == "all"
        assert len(provider_contents) == 1
        assert provider_contents[0].text == (
            '<file-attachment name="notes.txt" type="text/plain">\n'
            "notes\n"
            "</file-attachment>"
        )
        with reactive.isolate():
            latest_input = chat.user_input()
            assert latest_input is not None
            assert latest_input.text == "source input"
            assert latest_input.attachments == [attachment]
            assert chat.latest_message_stream.status() == "running"
        stored_target = await store.get(controller.partition, target.id)
        assert isinstance(stored_target, ConversationRecordV2)
        assert stored_target.model_dump(mode="json") == target_before
        assert target.model_dump(mode="json") == target_before
    finally:
        client.release_stream.set()
        if chat is not None:
            with reactive.isolate():
                chat.latest_message_stream.cancel()
            await asyncio.sleep(0)
            chat.destroy()


@pytest.mark.anyio
async def test_v2_same_flush_failed_capture_and_history_selection_restores_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id = ResolvedId("same_flush_failed_capture")
    history_ids = HistoryInputIds.for_chat(chat_id)
    session = _RealHistorySession()
    session.input[ResolvedId(f"{chat_id}_user_input")] = reactive.Value()
    session.input[history_ids.select] = reactive.Value()
    client = _SameFlushHistoryClient()
    store = InMemoryConversationStore()
    public_calls: list[str] = []
    capture_errors: list[BaseException] = []
    chat: Chat | None = None

    monkeypatch.setattr("shinychat._history._EXCHANGE_TREE_HISTORY_V2", True)
    try:
        with session_context(cast(Any, session)):
            chat = Chat(
                str(chat_id),
                client=cast(Any, client),
                history=HistoryOptions(
                    restore_mode="none",
                    scope="same-flush-failed-capture",
                    store=store,
                    title=None,
                ),
            )
        await reactive.flush()

        controller = chat.history._controller
        assert controller is not None
        assert controller.partition is not None
        recorder = controller._exchange_recorder
        assert recorder is not None
        target = new_conversation_record_v2(
            title="target",
            id="c_target",
            client_info={},
        )
        target.open_exchange("n_0001", _stored_message("user", "target input"))
        await store.put(controller.partition, target)
        target_before = target.model_dump(mode="json")

        async def fail_capture(
            exchange_id: str, message: StoredMessage
        ) -> None:
            del exchange_id
            del message
            raise RuntimeError("capture failed")

        async def capture_error(error: BaseException) -> None:
            capture_errors.append(error)

        chat._transcript.set_capture_callbacks(
            on_accepted_input=fail_capture,
            on_message_committed=recorder.message_committed,
            on_stream_started=recorder.stream_started,
            on_stream_updated=recorder.stream_updated,
            on_stream_finished=recorder.stream_finished,
        )
        chat._raise_exception = capture_error  # type: ignore[method-assign]

        @chat.on_user_submit
        async def _public_handler(text: str) -> None:
            public_calls.append(text)

        cast(Any, session.input[chat.user_input_id]).set(
            {"text": "failed source input", "attachments": [], "seq": 1}
        )
        cast(Any, session.input[history_ids.select]).set({"id": target.id})
        await reactive.flush()

        assert [str(error) for error in capture_errors] == ["capture failed"]
        assert public_calls == []
        assert client.stream_calls == []
        with reactive.isolate():
            assert chat.user_input() is None
            assert chat._normal_user_submission() is None
        assert recorder.record is target
        assert controller._active_id_now() == target.id
        assert [
            entry.message.content for entry in chat._transcript.read()
        ] == ["target input"]
        stored_target = await store.get(controller.partition, target.id)
        assert isinstance(stored_target, ConversationRecordV2)
        assert stored_target.model_dump(mode="json") == target_before
        assert target.model_dump(mode="json") == target_before
    finally:
        client.release_stream.set()
        if chat is not None:
            chat.destroy()


@pytest.mark.anyio
async def test_v2_switch_rejects_active_attached_provider_without_mutating_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chatlas = pytest.importorskip("chatlas")
    from chatlas._content import ContentText
    from chatlas._turn import AssistantTurn

    class HistorySession(_RealChatSession):
        def __init__(self) -> None:
            super().__init__()
            self.bookmark = type(
                "Bookmark",
                (),
                {
                    "exclude": [],
                    "store": "disable",
                    "_restore_context": None,
                },
            )()

        def is_stub_session(self) -> bool:
            return False

        def root_scope(self) -> "HistorySession":
            return self

    class BlockingLookupStore(InMemoryConversationStore):
        def __init__(self) -> None:
            super().__init__()
            self.blocked_target: str | None = None
            self.target_lookup_entered = asyncio.Event()
            self.release_target_lookup = asyncio.Event()

        async def get(
            self, partition: ConversationPartition, conv_id: str
        ) -> Any:
            if conv_id == self.blocked_target:
                self.target_lookup_entered.set()
                await self.release_target_lookup.wait()
            return await super().get(partition, conv_id)

    store = BlockingLookupStore()
    provider = MagicMock()
    provider.name = "blocking"
    provider.model = "blocking"
    provider_turn_started = asyncio.Event()
    release_provider = asyncio.Event()
    provider_stream_finished = asyncio.Event()
    provider_calls: list[dict[str, Any]] = []
    provider_chunk = object()
    provider_text = "terminal response"

    provider.stream_merge_chunks.side_effect = (
        lambda _completion, chunk: chunk
    )
    provider.stream_content.return_value = [ContentText(text=provider_text)]
    provider.stream_turn.return_value = AssistantTurn(
        contents=[ContentText(text=provider_text)]
    )

    async def chat_perform_async(**kwargs: Any) -> Any:
        provider_calls.append(kwargs)

        async def response() -> Any:
            provider_turn_started.set()
            await release_provider.wait()
            yield provider_chunk
            provider_stream_finished.set()

        return response()

    provider.chat_perform_async = chat_perform_async
    session = HistorySession()
    session.input["v2_switch_provider_user_input"] = reactive.Value()
    chat: Chat | None = None
    switch: asyncio.Task[None] | None = None
    source_stream: Any | None = None

    monkeypatch.setattr(
        "shinychat._history._EXCHANGE_TREE_HISTORY_V2",
        True,
    )
    try:
        with session_context(cast(Any, session)):
            chat = Chat(
                "v2_switch_provider",
                client=chatlas.Chat(provider),
                history=HistoryOptions(
                    restore_mode="none",
                    store=store,
                    scope="v2-switch-provider",
                    title=None,
                ),
            )
        await reactive.flush()

        controller = chat.history._controller
        assert controller is not None
        recorder = controller._exchange_recorder
        assert recorder is not None
        assert controller.partition is not None
        target = new_conversation_record_v2(
            title="target",
            id="c_target",
            client_info={},
        )
        await store.put(controller.partition, target)

        store.blocked_target = target.id
        switch = asyncio.create_task(controller.switch_to(target.id))
        await asyncio.wait_for(store.target_lookup_entered.wait(), timeout=1)

        cast(Any, session.input[chat.user_input_id]).set(
            {"text": "source", "attachments": [], "seq": 1}
        )
        await reactive.flush()
        await asyncio.wait_for(provider_turn_started.wait(), timeout=1)
        await asyncio.sleep(0)
        with reactive.isolate():
            source_stream = chat.latest_message_stream
            assert source_stream.status() == "running"

        source = recorder.record
        assert source is not None
        source_id = controller._active_id_now()
        assert source_id == source.id
        source_display = copy.deepcopy(chat.messages())
        source_turns = copy.deepcopy(
            controller.adapter.get_turns_json(include_system_prompt=True)
        )
        source_recorder = source.model_dump(mode="json")
        stored_source = await store.get(controller.partition, source.id)
        assert isinstance(stored_source, ConversationRecordV2)
        source_store = stored_source.model_dump(mode="json")
        target_store = target.model_dump(mode="json")

        assert [
            (message["role"], message["content"])
            for message in source_display
        ] == [("user", "source"), ("assistant", "")]
        assert [turn["role"] for turn in source_turns] == [
            "user",
            "assistant",
        ]
        assert provider_calls

        store.release_target_lookup.set()
        with pytest.raises(RuntimeError, match="stream is active"):
            await switch

        assert controller._active_id_now() == source_id
        assert chat.messages() == source_display
        assert (
            controller.adapter.get_turns_json(include_system_prompt=True)
            == source_turns
        )
        assert recorder.record is source
        assert source.model_dump(mode="json") == source_recorder
        stored_source = await store.get(controller.partition, source.id)
        stored_target = await store.get(controller.partition, target.id)
        assert isinstance(stored_source, ConversationRecordV2)
        assert isinstance(stored_target, ConversationRecordV2)
        assert stored_source.model_dump(mode="json") == source_store
        assert stored_target.model_dump(mode="json") == target_store
    finally:
        store.release_target_lookup.set()
        if switch is not None and not switch.done():
            switch.cancel()
            with suppress(asyncio.CancelledError):
                await switch
        release_provider.set()
        try:
            if source_stream is not None:
                await asyncio.wait_for(
                    provider_stream_finished.wait(), timeout=1
                )

                async def settle_source_stream() -> str:
                    while True:
                        await reactive.flush()
                        await asyncio.sleep(0)
                        with reactive.isolate():
                            source_status = source_stream.status()
                        if source_status != "running":
                            return source_status

                source_status = await asyncio.wait_for(
                    settle_source_stream(), timeout=1
                )
                with reactive.isolate():
                    assert source_status == "success"
                    assert source_stream.result() == provider_text
        finally:
            if chat is not None:
                chat.destroy()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("failure_kind", "sent_chunk"),
    [
        ("error", False),
        ("error", True),
        ("cancelled", False),
        ("cancelled", True),
    ],
)
async def test_v2_real_stream_failure_preserves_capture_matrix(
    failure_kind: str,
    sent_chunk: bool,
    request: pytest.FixtureRequest,
) -> None:
    adapter = _FakeAdapter()
    adapter.turns = []

    class SnapshotStore(InMemoryConversationStore):
        async def put(
            self, partition: ConversationPartition, record: Any
        ) -> None:
            await super().put(partition, record.model_copy(deep=True))

        async def get(
            self, partition: ConversationPartition, conv_id: str
        ) -> Any:
            record = await super().get(partition, conv_id)
            return record.model_copy(deep=True) if record is not None else None

    store = SnapshotStore()
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
        adapter=adapter,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    session = _RealChatSession()
    with session_context(cast(Any, session)):
        chat = Chat("history_stream_failure", history=False)
    request.addfinalizer(chat.destroy)
    controller.chat = chat  # type: ignore[assignment]
    chat._transcript.set_capture_callbacks(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )
    await chat._record_accepted_user_input_with_capture(
        ChatMessage(content="question", role="user")
    )
    committed_turns = [{"role": "user", "content": "question"}]
    adapter.turns = committed_turns
    original: BaseException = (
        RuntimeError("provider failure")
        if failure_kind == "error"
        else asyncio.CancelledError()
    )

    async def stream() -> AsyncIterator[str]:
        if sent_chunk:
            adapter.turns = [
                *committed_turns,
                {"role": "assistant", "content": "sent"},
            ]
            yield "sent"
        raise original

    with pytest.raises(type(original)) as raised:
        await chat._append_message_stream(stream())

    assert raised.value is original
    assert recorder.record is not None
    stored = await store.get(part(), recorder.record.id)
    assert isinstance(stored, ConversationRecordV2)
    assert stored is not recorder.record
    assert stored.active_leaf is not None
    node = stored.nodes[stored.active_leaf]
    assert [
        message.as_stored_message().content for message in node.messages
    ] == (["sent"] if sent_chunk else [""])
    assert node.status == failure_kind
    if failure_kind == "error":
        assert node.error is not None
        assert node.error.message == str(original)
    else:
        assert node.error is None
    assert node.state["shinychat:turns"].data == adapter.turns
    assert chat._transcript.active_stream_id is None


@pytest.mark.anyio
async def test_cancelled_v2_switch_releases_real_chat_input_admission(
    request: pytest.FixtureRequest,
) -> None:
    class BlockingStore(InMemoryConversationStore):
        def __init__(self) -> None:
            super().__init__()
            self.block_id: str | None = None
            self.source_save_entered = asyncio.Event()

        async def put(
            self, partition: ConversationPartition, record: Any
        ) -> None:
            if record.id == self.block_id:
                self.block_id = None
                self.source_save_entered.set()
                await asyncio.Event().wait()
            await super().put(partition, record)

    store = BlockingStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    session = _RealChatSession()
    with session_context(cast(Any, session)):
        chat = Chat("history_switch_cancel_input", history=False)
    switch: asyncio.Task[None] | None = None

    def cleanup_chat() -> None:
        if switch is not None and not switch.done():
            switch.cancel()
        chat.destroy()

    request.addfinalizer(cleanup_chat)
    controller.chat = chat  # type: ignore[assignment]
    chat._transcript.set_capture_callbacks(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )
    await chat._record_accepted_user_input_with_capture(
        ChatMessage(content="source", role="user")
    )
    assert recorder.record is not None
    source = recorder.record
    target = new_conversation_record_v2(
        title="target",
        id="c_target",
        client_info={},
    )
    await store.put(part(), target)

    store.block_id = source.id
    switch = asyncio.create_task(controller.switch_to(target.id))
    await store.source_save_entered.wait()
    assert chat._destructive_history_blocks_input

    switch.cancel()
    with pytest.raises(asyncio.CancelledError):
        await switch

    assert not chat._destructive_history_blocks_input
    await chat._record_accepted_user_input_with_capture(
        ChatMessage(content="accepted after cancellation", role="user")
    )
    assert [entry.message.content for entry in chat._transcript.read()] == [
        "source",
        "accepted after cancellation",
    ]
    assert recorder.record is source


@pytest.mark.anyio
async def test_error_v2_switch_releases_real_chat_input_admission(
    request: pytest.FixtureRequest,
) -> None:
    class ErrorStore(InMemoryConversationStore):
        fail_source = False
        source_id: str | None = None
        source_error = RuntimeError("source save failed")

        async def put(
            self, partition: ConversationPartition, record: Any
        ) -> None:
            if self.fail_source and record.id == self.source_id:
                raise self.source_error
            await super().put(partition, record)

    store = ErrorStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    session = _RealChatSession()
    with session_context(cast(Any, session)):
        chat = Chat("history_switch_error_input", history=False)
    request.addfinalizer(chat.destroy)
    controller.chat = chat  # type: ignore[assignment]
    chat._transcript.set_capture_callbacks(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )
    await chat._record_accepted_user_input_with_capture(
        ChatMessage(content="source", role="user")
    )
    assert recorder.record is not None
    source = recorder.record
    store.source_id = source.id
    target = new_conversation_record_v2(
        title="target",
        id="c_target",
        client_info={},
    )
    await store.put(part(), target)
    store.fail_source = True

    with pytest.raises(RuntimeError) as raised:
        await controller.switch_to(target.id)

    assert raised.value is store.source_error
    assert not chat._destructive_history_blocks_input
    store.fail_source = False
    await chat._record_accepted_user_input_with_capture(
        ChatMessage(content="accepted after error", role="user")
    )
    assert [entry.message.content for entry in chat._transcript.read()] == [
        "source",
        "accepted after error",
    ]
    assert recorder.record is source


@pytest.mark.anyio
async def test_generic_destructive_admission_does_not_block_real_chat_input(
    request: pytest.FixtureRequest,
) -> None:
    controller, _ = _make_controller(use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    session = _RealChatSession()
    with session_context(cast(Any, session)):
        chat = Chat("history_generic_input", history=False)

    request.addfinalizer(chat.destroy)
    controller.chat = chat  # type: ignore[assignment]
    chat._transcript.set_capture_callbacks(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )

    async with controller._destructive_mutation():
        await chat._record_accepted_user_input_with_capture(
            ChatMessage(
                content="accepted during generic admission", role="user"
            )
        )

    assert [entry.message.content for entry in chat._transcript.read()] == [
        "accepted during generic admission"
    ]


@pytest.mark.anyio
async def test_v2_switch_saves_source_before_target_preflight_failure() -> None:
    class SnapshotStore(InMemoryConversationStore):
        async def get(
            self, partition: ConversationPartition, conv_id: str
        ) -> Any:
            record = await super().get(partition, conv_id)
            return record.model_copy(deep=True) if record is not None else None

        async def put(
            self, partition: ConversationPartition, record: Any
        ) -> None:
            await super().put(partition, record.model_copy(deep=True))

    saved_value = "initial"

    def save(values: dict[str, Any]) -> None:
        values["current"] = saved_value

    adapter = _TrackingFakeAdapter()
    store = SnapshotStore()
    controller, _ = _make_controller(
        store=store,
        save_callbacks=[save],
        use_exchange_tree=True,
        adapter=adapter,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    source = new_conversation_record_v2(
        title="source",
        id="c_source",
        client_info={},
    )
    recorder.record = source
    controller._active_id.set(source.id)
    await store.put(part(), source)

    source.open_exchange("n_0001", _stored_message("user", "latest source"))
    saved_value = "latest value"
    target = new_conversation_record_v2(
        title="invalid target",
        id="c_target",
        client_info={},
    )
    target.nodes["n_0000"].state["unsupported"] = StateEntry(
        kind="test",
        version=1,
        mode="snapshot",
        data={},
    )
    await store.put(part(), target)

    fake_chat = cast(_FakeChat, controller.chat)
    fake_chat.messages = [_stored_message("assistant", "live source")]

    with pytest.raises(ValueError, match="Unsupported restore state entry"):
        await controller.switch_to(target.id)

    stored_source = await store.get(part(), source.id)
    assert isinstance(stored_source, ConversationRecordV2)
    assert stored_source.values == {"current": "latest value"}
    assert [
        node.input.content
        for node in stored_source.nodes.values()
        if node.input is not None
    ] == ["latest source"]
    assert recorder.record is source
    assert controller._active_id_now() == source.id
    assert fake_chat.clear_messages_calls == 0
    assert fake_chat.messages == [_stored_message("assistant", "live source")]
    assert fake_chat.set_greeting_calls == []
    assert adapter.set_calls == []


@pytest.mark.anyio
async def test_v2_restore_hooks_are_ordered_and_receive_keyed_path_context():
    controller, _ = _make_controller(use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = new_conversation_record_v2(
        title="restore",
        id="c_hooks",
        client_info={},
    )
    record.nodes["n_0000"].state["first"] = StateEntry(
        kind="test",
        version=1,
        mode="snapshot",
        data={"root": True},
    )
    record.open_exchange("n_0001", _stored_message("user", "first"))
    record.nodes["n_0001"].state["second"] = StateEntry(
        kind="test",
        version=1,
        mode="delta",
        data={"child": True},
    )
    observed: list[tuple[str, StatePathContext]] = []

    def first(context: StatePathContext) -> None:
        observed.append(("first", context))

    async def second(context: StatePathContext) -> None:
        observed.append(("second", context))

    recorder._register_restore_hook("first", first)
    recorder._register_restore_hook("second", second)

    await controller.replay_exchange_record(record)

    assert [name for name, _ in observed] == ["first", "second"]
    first_context = observed[0][1]
    second_context = observed[1][1]
    assert first_context.conversation_id == "c_hooks"
    assert first_context.active_leaf == "n_0001"
    assert first_context.node_ids == ("n_0000", "n_0001")
    assert first_context.bootstrap == "recorded"
    assert first_context.entries == (
        ("n_0000", record.nodes["n_0000"].state["first"]),
    )
    assert second_context.entries == (
        ("n_0001", record.nodes["n_0001"].state["second"]),
    )


@pytest.mark.anyio
async def test_v2_restore_invalid_path_leaves_live_chat_unchanged():
    adapter = _TrackingFakeAdapter()
    controller, _ = _make_controller(
        use_exchange_tree=True,
        adapter=adapter,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    existing = new_conversation_record_v2(
        title="existing",
        id="c_existing",
        client_info={},
    )
    recorder.record = existing
    invalid = new_conversation_record_v2(
        title="invalid",
        id="c_invalid",
        client_info={},
    )
    invalid.active_leaf = "missing"
    fake_chat = cast(_FakeChat, controller.chat)

    with pytest.raises(ValueError, match="Dangling parent reference"):
        await controller.replay_exchange_record(invalid)

    assert recorder.record is existing
    assert fake_chat.clear_messages_calls == 0
    assert fake_chat.set_greeting_calls == []
    assert adapter.set_calls == []


def _restore_target(*, id: str = "c_target") -> ConversationRecordV2:
    record = new_conversation_record_v2(title="target", id=id, client_info={})
    record.nodes["n_0000"].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[{"role": "system", "content": "restored"}],
    )
    exchange_id = "n_0001"
    record.open_exchange(exchange_id, _stored_message("user", "question"))
    for content in ("first reply", "second reply"):
        record.append_message(
            exchange_id,
            CapturedMessage.from_stored_message(
                _stored_message("assistant", content), icon=None
            ),
        )
    return record


def _install_live_v2_record(
    controller: HistoryController, *, id: str = "c_existing"
) -> ConversationRecordV2:
    recorder = controller._exchange_recorder
    assert recorder is not None
    existing = new_conversation_record_v2(
        title="existing", id=id, client_info={}
    )
    recorder.record = existing
    controller._active_id.set(existing.id)
    return existing


@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalid",
    [
        ("unknown", StateEntry(kind="test", version=1, mode="delta", data={})),
        ("mode", StateEntry(kind="turns", version=1, mode="snapshot", data=[])),
        ("data", StateEntry(kind="turns", version=1, mode="snapshot", data=[])),
    ],
)
async def test_v2_restore_preflight_failure_leaves_live_state_untouched(
    invalid: tuple[str, StateEntry],
) -> None:
    adapter = _TrackingFakeAdapter()
    controller, _ = _make_controller(
        use_exchange_tree=True,
        adapter=adapter,
    )
    existing = _install_live_v2_record(controller)
    target = _restore_target()
    name, entry = invalid
    if name == "data":
        entry.data = ["not a turn"]  # type: ignore[assignment]
    elif name == "mode":
        entry.mode = cast(Any, "invalid")
    target.nodes["n_0000"].state[
        "unexpected" if name == "unknown" else "shinychat:turns"
    ] = entry
    fake_chat = cast(_FakeChat, controller.chat)
    fake_chat.messages = [_stored_message("assistant", "live")]
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    with pytest.raises(ValueError):
        await controller.replay_exchange_record(target)

    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.record is existing
    assert controller._active_id_now() == existing.id
    assert fake_chat.clear_messages_calls == 0
    assert fake_chat.set_greeting_calls == []
    assert fake_chat.messages == [_stored_message("assistant", "live")]
    assert adapter.set_calls == []
    notifier.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("incompatibility", ["kind", "version", "content"])
async def test_v2_restore_degrades_effective_turns_and_keeps_exchange_usable(
    incompatibility: str,
) -> None:
    adapter = _TrackingFakeAdapter(chatlas=incompatibility == "content")
    controller, _ = _make_controller(
        use_exchange_tree=True,
        adapter=adapter,
    )
    target = _restore_target()
    exchange_id = "n_0001"
    target.nodes[exchange_id].status = "error"
    entry = target.nodes["n_0000"].state["shinychat:turns"]
    if incompatibility == "kind":
        entry.kind = "unsupported"
    elif incompatibility == "version":
        entry.version = 2
    else:
        entry.kind = "chatlas"
        entry.data = [{"role": "not-a-chatlas-role"}]
    target_before = target.model_copy(deep=True)
    events: list[str] = []

    async def warn() -> None:
        events.append("warning")

    async def publish() -> None:
        events.append("history_update")

    controller._notify_turns_unavailable = warn  # type: ignore[method-assign]
    controller.send_history_update = publish  # type: ignore[method-assign]

    await controller.replay_exchange_record(target)

    recorder = controller._exchange_recorder
    assert recorder is not None
    fake_chat = cast(_FakeChat, controller.chat)
    assert recorder.record is target
    assert controller._active_id_now() == target.id
    assert [message["role"] for message in fake_chat.restored_messages] == [
        "user",
        "assistant",
        "assistant",
    ]
    assert adapter.set_calls == [[]]
    assert adapter.turns == []
    assert target == target_before
    assert events == ["warning", "history_update"]
    assert {
        "type": "update_exchange_metadata",
        "data": {0: {"status": "error", "retryable": True}},
    } in fake_chat.actions

    adapter.turns = [{"role": "user", "content": "continued"}]
    if incompatibility == "content":
        adapter.system_turns = list(adapter.turns)
    await recorder._capture_state(exchange_id, "node_close")
    continued = target.nodes[exchange_id].state["shinychat:turns"]
    assert continued.mode == "snapshot"
    assert continued.data == [{"role": "user", "content": "continued"}]


@pytest.mark.anyio
async def test_v2_degraded_restore_continuation_snapshots_compatible_turns_for_reload(
    tmp_path: Path,
) -> None:
    from shinychat._history_store import FileConversationStore

    store = FileConversationStore(tmp_path)
    adapter = _TrackingFakeAdapter()
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
        adapter=adapter,
    )
    target = _restore_target()
    target.nodes["n_0000"].state["shinychat:turns"].kind = "unsupported"
    await store.put(part(), target)
    warning = AsyncMock()
    controller._notify_turns_unavailable = warning  # type: ignore[method-assign]

    await controller.replay_exchange_record(target)

    warning.assert_awaited_once()
    recorder = controller._exchange_recorder
    assert recorder is not None

    compatible_turns = [{"role": "user", "content": "continued"}]
    adapter.turns = compatible_turns
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "continued")
    )

    continued = target.nodes["n_0001"].state["shinychat:turns"]
    assert continued.mode == "snapshot"
    assert continued.data == compatible_turns

    stored = await store.get(part(), target.id)
    assert isinstance(stored, ConversationRecordV2)
    reloaded_adapter = _TrackingFakeAdapter()
    reloaded, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
        adapter=reloaded_adapter,
    )
    reloaded_warning = AsyncMock()
    reloaded._notify_turns_unavailable = reloaded_warning  # type: ignore[method-assign]

    await reloaded.replay_exchange_record(stored)

    reloaded_warning.assert_not_awaited()
    assert reloaded_adapter.turns == compatible_turns


@pytest.mark.anyio
@pytest.mark.parametrize("restore_bootstrap", ["recorded", "live"])
@pytest.mark.parametrize("resubmit_kind", ["retry", "edit", "regenerate"])
async def test_v2_degraded_resubmit_preserves_live_turns_and_immutable_target(
    tmp_path: Path, restore_bootstrap: str, resubmit_kind: str
) -> None:
    adapter = _TrackingFakeAdapter()
    live_baseline = [{"role": "system", "content": "live"}]
    adapter.turns = list(live_baseline)
    store = FileConversationStore(tmp_path)
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
        adapter=adapter,
    )
    controller.restore_bootstrap = cast(Any, restore_bootstrap)
    target = _restore_target()
    exchange_id = "n_0001"
    target.nodes[exchange_id].status = (
        "ok" if resubmit_kind == "regenerate" else "error"
    )
    target.nodes[exchange_id].state["shinychat:turns"] = StateEntry(
        kind="unsupported",
        version=1,
        mode="delta",
        data=[],
    )
    target.nodes["n_0000"].state["parent"] = StateEntry(
        kind="test",
        version=1,
        mode="snapshot",
        data={"parent": True},
    )
    events: list[str] = []
    rewind_contexts: list[StatePathContext] = []

    async def warn() -> None:
        events.append("warning")

    async def publish() -> None:
        events.append("history_update")

    controller._notify_turns_unavailable = warn  # type: ignore[method-assign]
    controller.send_history_update = publish  # type: ignore[method-assign]
    recorder = controller._exchange_recorder
    assert recorder is not None
    await store.put(part(), target)
    recorder._register_restore_hook("parent", lambda _context: None)
    rewind_before_branch: list[bool] = []

    def rewind_parent(context: StatePathContext) -> None:
        rewind_before_branch.append(
            context.active_leaf == "n_0000"
            and target.children_of("n_0000") == [exchange_id]
        )
        rewind_contexts.append(context)

    recorder._register_rewind_hook("parent", rewind_parent)

    await controller.replay_exchange_record(target)

    assert recorder.record is target
    expected_baseline = [] if restore_bootstrap == "recorded" else live_baseline
    assert adapter.turns == expected_baseline
    assert events == ["warning", "history_update"]
    restored_display = list(cast(_FakeChat, controller.chat).restored_messages)
    restore_set_calls = list(adapter.set_calls)
    original_node = target.nodes[exchange_id].model_dump_json()
    parent_before = target.nodes["n_0000"].model_copy(deep=True)
    assert recorder._active_path_turns_are_incompatible(target)
    original_send_action = cast(_FakeChat, controller.chat)._send_action
    original_publish = cast(_FakeChat, controller.chat)._publish_accepted_user_input

    async def send_projection(action: dict[str, Any]) -> None:
        events.append("projection")
        await original_send_action(action)

    def publish_after_projection(message: StoredMessage) -> None:
        events.append("published")
        original_publish(message)

    cast(_FakeChat, controller.chat)._send_action = send_projection  # type: ignore[method-assign]
    cast(_FakeChat, controller.chat)._publish_accepted_user_input = publish_after_projection  # type: ignore[method-assign]

    if resubmit_kind == "edit":
        await controller.handle_edit(0, "edited", request_id=resubmit_kind)
    else:
        await controller.handle_resubmit(
            0, resubmit_kind, request_id=resubmit_kind
        )

    sibling = target.active_leaf
    assert sibling is not None
    assert sibling != exchange_id
    assert target.nodes[sibling].parent_id == "n_0000"
    assert target.nodes[exchange_id].model_dump_json() == original_node
    assert adapter.set_calls == restore_set_calls
    assert adapter.turns == expected_baseline
    assert recorder._turn_baseline == recorder._canonical_turns(
        expected_baseline
    )[1]
    assert len(rewind_contexts) == 1
    assert rewind_before_branch == [True]
    assert rewind_contexts[0].node_ids == ("n_0000",)
    assert rewind_contexts[0].entries == (
        ("n_0000", target.nodes["n_0000"].state["parent"]),
    )
    assert rewind_contexts[0].bootstrap == "recorded"
    assert cast(_FakeChat, controller.chat).restored_messages == restored_display
    assert events == ["warning", "history_update", "projection", "published"]
    assert target.nodes["n_0000"].input == parent_before.input
    assert target.nodes["n_0000"].state == parent_before.state
    assert target.nodes["n_0000"].messages == parent_before.messages
    assert target.nodes["n_0000"].status == parent_before.status
    assert target.nodes["n_0000"].children == [exchange_id, sibling]
    assert target.nodes["n_0000"].selected_child == sibling
    sibling_turns = target.nodes[sibling].state["shinychat:turns"]
    assert sibling_turns.mode == "snapshot"
    assert sibling_turns.data == expected_baseline
    assert cast(_FakeChat, controller.chat).published_inputs == [
        target.nodes[sibling].input
    ]
    assert cast(_FakeChat, controller.chat).actions[-1] == {
        "type": "history_accepted_input_projection",
        "index": 0,
        "content": "edited" if resubmit_kind == "edit" else "question",
        "attachments": [],
    }

    stored = await store.get(part(), target.id)
    assert isinstance(stored, ConversationRecordV2)
    reloaded_adapter = _TrackingFakeAdapter()
    reloaded, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
        adapter=reloaded_adapter,
    )
    reloaded.restore_bootstrap = cast(Any, restore_bootstrap)
    reloaded_warning = AsyncMock()
    reloaded._notify_turns_unavailable = reloaded_warning  # type: ignore[method-assign]
    reloaded_recorder = reloaded._exchange_recorder
    assert reloaded_recorder is not None
    reloaded_recorder._register_restore_hook("parent", lambda _context: None)

    await reloaded.replay_exchange_record(stored)

    reloaded_warning.assert_not_awaited()
    assert reloaded_adapter.turns == expected_baseline


@pytest.mark.anyio
async def test_v2_degraded_resubmit_preserves_projection_error_when_publication_fails(
    tmp_path: Path,
):
    controller, chat, _adapter, _store, first, target = (
        _make_v2_resubmit_controller()
    )
    file_store = FileConversationStore(tmp_path)
    controller.store = file_store
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.nodes[target].state["shinychat:turns"].kind = "unsupported"

    projection_error = RuntimeError("projection unavailable")
    publication_error = RuntimeError("publication unavailable")
    publication_calls: list[StoredMessage] = []

    async def fail_projection(_action: dict[str, Any]) -> None:
        raise projection_error

    def fail_publication(message: StoredMessage) -> None:
        publication_calls.append(message)
        raise publication_error

    chat._send_action = fail_projection  # type: ignore[method-assign]
    chat._publish_accepted_user_input = fail_publication  # type: ignore[method-assign]

    with pytest.raises(RuntimeError) as raised:
        await controller.handle_resubmit(
            1, "retry", request_id="retry"
        )

    assert raised.value is projection_error
    assert raised.value.__cause__ is publication_error
    assert raised.value.__context__ is publication_error
    assert len(publication_calls) == 1
    sibling = record.active_leaf
    assert sibling is not None
    assert sibling != target
    assert record.nodes[sibling].parent_id == first
    assert record.children_of(first) == [target, sibling]
    assert publication_calls == [record.nodes[sibling].input]

    stored = await FileConversationStore(tmp_path).get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    assert stored.active_leaf == sibling
    assert stored.nodes[sibling].parent_id == first
    assert stored.children_of(first) == [target, sibling]


@pytest.mark.anyio
async def test_v2_degraded_resubmit_propagates_publication_failure_after_projection():
    controller, chat, _adapter, store, first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.nodes[target].state["shinychat:turns"].kind = "unsupported"

    publication_error = RuntimeError("publication unavailable")
    published_messages: list[StoredMessage] = []

    def fail_publication(message: StoredMessage) -> None:
        published_messages.append(message)
        raise publication_error

    chat._publish_accepted_user_input = fail_publication  # type: ignore[method-assign]

    with pytest.raises(RuntimeError) as raised:
        await controller.handle_resubmit(
            1, "retry", request_id="retry"
        )

    assert raised.value is publication_error
    assert chat.actions == [
        {
            "type": "history_accepted_input_projection",
            "index": 1,
            "content": "second",
            "attachments": [],
        }
    ]
    sibling = record.active_leaf
    assert sibling is not None
    assert sibling != target
    assert record.nodes[sibling].parent_id == first
    assert record.children_of(first) == [target, sibling]
    assert len(store.put_calls) == 1
    assert store.put_calls[0][1] is record
    assert published_messages == [record.nodes[sibling].input]


@pytest.mark.anyio
async def test_v2_degraded_resubmit_rewind_failure_precedes_sibling_mutation():
    controller, chat, adapter, store, first, target = _make_v2_resubmit_controller()
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.nodes[target].state["shinychat:turns"].kind = "unsupported"
    record.nodes[first].state["parent"] = StateEntry(
        kind="test",
        version=1,
        mode="snapshot",
        data={"parent": True},
    )
    before = record.model_dump()
    transcript_before = chat._transcript.read()
    turns_before = list(adapter.turns)
    error = RuntimeError("rewind failed")

    async def fail_rewind(_context: StatePathContext) -> None:
        raise error

    recorder._register_rewind_hook("parent", fail_rewind)

    with pytest.raises(RuntimeError) as raised:
        await controller.resubmit(
            target, kind="retry", request_id="retry", message_index=1
        )

    assert raised.value is error
    assert record.model_dump() == before
    assert chat._transcript.read() == transcript_before
    assert adapter.turns == turns_before
    assert store.put_calls == []
    assert chat.actions == []
    assert chat.published_inputs == []


@pytest.mark.anyio
async def test_v2_degraded_resubmit_projection_failure_publishes_durable_input_once():
    controller, chat, _adapter, store, first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.nodes[target].state["shinychat:turns"].kind = "unsupported"
    error = RuntimeError("projection unavailable")
    events: list[str] = []

    async def fail_projection(action: dict[str, Any]) -> None:
        events.append(action["type"])
        raise error

    original_publish = chat._publish_accepted_user_input

    def publish(message: StoredMessage) -> None:
        events.append("published")
        original_publish(message)

    chat._send_action = fail_projection  # type: ignore[method-assign]
    chat._publish_accepted_user_input = publish  # type: ignore[method-assign]

    with pytest.raises(RuntimeError) as raised:
        await controller.resubmit(
            target, kind="retry", request_id="retry", message_index=1
        )

    assert raised.value is error
    sibling = record.active_leaf
    assert sibling is not None
    assert sibling != target
    assert record.nodes[sibling].parent_id == first
    assert len(store.put_calls) == 1
    assert store.put_calls[0][1] is record
    assert chat.published_inputs == [record.nodes[sibling].input]
    assert events == ["history_accepted_input_projection", "published"]
    assert chat.clear_messages_calls == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("kind", "status", "match"),
    [
        ("retry", "ok", "Only interrupted or failed exchanges"),
        ("regenerate", "pending", "Only completed exchanges"),
        ("regenerate", "error", "Only completed exchanges"),
        ("regenerate", "cancelled", "Only completed exchanges"),
    ],
)
async def test_v2_resubmit_validates_kind_status_before_mutation(
    kind: str, status: str, match: str
) -> None:
    controller, chat, adapter, store, _first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.nodes[target].status = cast(Any, status)
    before = record.model_dump()
    turns_before = list(adapter.turns)

    with pytest.raises(ValueError, match=match):
        await controller.resubmit(
            target, kind=kind, request_id=kind, message_index=1
        )

    assert record.model_dump() == before
    assert adapter.turns == turns_before
    assert chat.destructive_preflight_calls == 0
    assert store.put_calls == []
    assert chat.actions == []
    assert chat.published_inputs == []


@pytest.mark.anyio
async def test_v2_resubmit_accepts_active_path_ancestor_for_edit():
    controller, chat, adapter, store, first, _target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None

    await controller.resubmit(
        first,
        _stored_message("user", "first replacement"),
        kind="edit",
        request_id="edit-ancestor",
        message_index=0,
    )

    assert record.active_leaf == "n_0000"
    assert adapter.turns == [{"role": "system", "content": "bootstrap"}]
    assert len(store.put_calls) == 1
    assert chat.actions[-1]["type"] == "history_edit_projection"


@pytest.mark.anyio
async def test_v2_resubmit_rejects_off_path_target_before_mutation():
    controller, chat, adapter, store, first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.set_active_leaf(first)
    off_path = "exchange-off-path"
    record.open_exchange(off_path, _stored_message("user", "off path"))
    record.set_active_leaf(target)
    before = record.model_dump()
    turns_before = list(adapter.turns)

    with pytest.raises(ValueError, match="not on the active path"):
        await controller.resubmit(
            off_path, kind="edit", request_id="off-path", message_index=1
        )

    assert record.model_dump() == before
    assert adapter.turns == turns_before
    assert chat.destructive_preflight_calls == 0
    assert store.put_calls == []
    assert chat.actions == []
    assert chat.published_inputs == []


@pytest.mark.anyio
async def test_v2_resubmit_rejects_missing_partition_before_mutation():
    controller, chat, adapter, store, _first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    before = record.model_dump()
    transcript_before = chat._transcript.read()
    turns_before = list(adapter.turns)
    controller.partition = None

    with pytest.raises(RuntimeError, match="HistoryController not initialized"):
        await controller.resubmit(
            target, kind="retry", request_id="retry", message_index=1
        )

    assert record.model_dump() == before
    assert chat._transcript.read() == transcript_before
    assert adapter.turns == turns_before
    assert chat.destructive_preflight_calls == 0
    assert store.put_calls == []
    assert chat.actions == []
    assert chat.published_inputs == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("data", "match"),
    [
        (["not a turn"], "Turn-state entries must contain a list of JSON objects"),
        ([{1: "not a JSON object"}], "Non-string mapping key"),
    ],
)
async def test_v2_resubmit_rejects_malformed_target_turn_data_before_mutation(
    data: list[Any], match: str
) -> None:
    controller, chat, adapter, store, _first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    target_state = record.nodes[target].state["shinychat:turns"]
    target_state.kind = "unsupported"
    target_state.data = data  # type: ignore[assignment]
    capture_state = AsyncMock()
    recorder._capture_state = capture_state  # type: ignore[method-assign]
    active_leaf = record.active_leaf
    turns_before = list(adapter.turns)

    with pytest.raises(ValueError, match=match):
        await controller.handle_resubmit(1, "retry", request_id="retry")

    capture_state.assert_not_awaited()
    assert record.active_leaf == active_leaf
    assert record.nodes[target].state["shinychat:turns"].data == data
    assert adapter.turns == turns_before
    assert chat.destructive_preflight_calls == 0
    assert store.put_calls == []
    assert chat.actions == []


@pytest.mark.anyio
async def test_v2_retry_rejects_incompatible_parent_superseded_by_target_snapshot():
    adapter = _TrackingFakeAdapter()
    controller, store = _make_controller(
        use_exchange_tree=True,
        adapter=adapter,
    )
    target = _restore_target()
    exchange_id = "n_0001"
    target.nodes[exchange_id].status = "error"
    target.nodes["n_0000"].state["shinychat:turns"].kind = "unsupported"
    target.nodes[exchange_id].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[{"role": "system", "content": "target snapshot"}],
    )
    events: list[str] = []

    async def warn() -> None:
        events.append("warning")

    async def publish() -> None:
        events.append("history_update")

    controller._notify_turns_unavailable = warn  # type: ignore[method-assign]
    controller.send_history_update = publish  # type: ignore[method-assign]

    await controller.replay_exchange_record(target)

    recorder = controller._exchange_recorder
    assert recorder is not None
    chat = cast(_FakeChat, controller.chat)
    assert not recorder._active_path_turns_are_incompatible(target)
    assert adapter.turns == [{"role": "system", "content": "target snapshot"}]
    assert events == ["history_update"]

    record_before = target.model_dump()
    turns_before = list(adapter.turns)
    set_calls_before = list(adapter.set_calls)
    display_before = list(chat.restored_messages)
    actions_before = list(chat.actions)
    clear_messages_before = chat.clear_messages_calls

    with pytest.raises(ValueError, match="Unsupported shinychat:turns"):
        await controller.handle_resubmit(0, "retry", request_id="retry")

    assert target.model_dump() == record_before
    assert adapter.turns == turns_before
    assert adapter.set_calls == set_calls_before
    assert chat.restored_messages == display_before
    assert chat.actions == actions_before
    assert chat.clear_messages_calls == clear_messages_before
    assert chat.destructive_preflight_calls == 1
    assert store.put_calls == []


@pytest.mark.anyio
async def test_v2_degraded_restore_warning_is_provider_neutral() -> None:
    controller, _ = _make_controller(use_exchange_tree=True)
    fake_chat = cast(_FakeChat, controller.chat)
    fake_chat._session = _RealHistorySession()  # type: ignore[attr-defined]
    notification = MagicMock()

    with patch("shiny.ui.notification_show", notification):
        await controller._notify_turns_unavailable()

    notification.assert_called_once_with(
        "Conversation display was restored, but model context was unavailable.",
        type="warning",
    )


@pytest.mark.anyio
async def test_v2_initial_bookmark_projection_failure_recovers() -> None:
    controller, _ = _make_controller(use_exchange_tree=True)
    target = _restore_target()
    target.nodes["n_0000"].parent_id = "missing"
    fake_chat = cast(_FakeChat, controller.chat)
    released_ids: list[str | None] = []

    async def release_active_id(id: str | None) -> None:
        released_ids.append(id)

    controller.on_active_id_change = release_active_id
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="Dangling parent reference"):
        await controller._restore_initial_exchange_record(
            target, node_id="n_0000"
        )

    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.record is None
    assert controller._active_id_now() is None
    assert released_ids == [None]
    assert fake_chat.clear_messages_calls == 1
    assert fake_chat.messages == []
    history_updates = [
        action for action in fake_chat.actions if action["type"] == "history_update"
    ]
    assert len(history_updates) == 1
    assert history_updates[0]["active_id"] is None
    notifier.assert_awaited_once_with(recovery_incomplete=False)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("initial admission failed"),
        asyncio.CancelledError("initial admission cancelled"),
    ],
)
async def test_v2_initial_restore_admission_failure_recovers(
    failure: BaseException,
) -> None:
    controller, _ = _make_controller(use_exchange_tree=True)
    target = _restore_target()
    fake_chat = cast(_FakeChat, controller.chat)
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    @asynccontextmanager
    async def fail_admission(*, block_input: bool = False):
        del block_input
        raise failure
        yield

    fake_chat._destructive_history_mutation = fail_admission  # type: ignore[method-assign]

    with pytest.raises(type(failure)) as raised:
        await controller._restore_initial_exchange_record(target)

    assert raised.value is failure
    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.record is None
    assert controller._active_id_now() is None
    assert fake_chat.clear_messages_calls == 1
    history_updates = [
        action for action in fake_chat.actions if action["type"] == "history_update"
    ]
    assert len(history_updates) == 1
    assert history_updates[0]["active_id"] is None
    notifier.assert_awaited_once_with(recovery_incomplete=False)


@pytest.mark.anyio
async def test_v2_live_restore_malformed_effective_turns_becomes_fresh_draft():
    store = InMemoryConversationStore()
    adapter = _TrackingFakeAdapter()
    adapter.turns = [{"role": "system", "content": "live"}]
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
        adapter=adapter,
    )
    controller.restore_bootstrap = "live"
    _install_live_v2_record(controller)
    target = _restore_target()
    target.nodes["n_0000"].state["shinychat:turns"].data = ["malformed"]
    target_before = target.model_copy(deep=True)
    await store.put(part(), target)
    fake_chat = cast(_FakeChat, controller.chat)
    fake_chat.messages = [_stored_message("assistant", "live")]
    fake_chat._transcript.replace(
        [TranscriptEntry(message=_stored_message("assistant", "live"))]
    )
    released_ids: list[str | None] = []

    async def release_active_id(id: str | None) -> None:
        released_ids.append(id)

    controller.on_active_id_change = release_active_id
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    with pytest.raises(
        ValueError, match="Turn-state entries must contain a list of JSON objects"
    ):
        await controller.replay_exchange_record(target)

    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.record is None
    assert controller.record is None
    assert controller._active_id_now() is None
    assert released_ids == [None]
    assert fake_chat.clear_messages_calls == 1
    assert fake_chat.messages == []
    assert fake_chat._transcript.read() == ()
    assert adapter.set_calls == [[]]
    assert adapter.turns == []
    assert target == target_before
    assert await store.get(part(), target.id) is target
    history_updates = [
        action for action in fake_chat.actions if action["type"] == "history_update"
    ]
    assert len(history_updates) == 1
    assert history_updates[0]["active_id"] is None
    assert history_updates[0]["transition_protocol"] == "completion-v2"
    notifier.assert_awaited_once_with(recovery_incomplete=False)


@pytest.mark.anyio
async def test_v2_live_restore_materialization_cancellation_cleans_up():
    adapter = _TrackingFakeAdapter()
    adapter.turns = [{"role": "system", "content": "live"}]
    controller, _ = _make_controller(
        use_exchange_tree=True,
        adapter=adapter,
    )
    controller.restore_bootstrap = "live"
    _install_live_v2_record(controller)
    target = _restore_target()
    fake_chat = cast(_FakeChat, controller.chat)
    fake_chat.messages = [_stored_message("assistant", "live")]
    fake_chat._transcript.replace(
        [TranscriptEntry(message=_stored_message("assistant", "live"))]
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    preflight_completed = False
    admission_held = False
    original_preflight = controller._prepare_exchange_restore
    original = asyncio.CancelledError("cancel during materialization")
    released_ids: list[str | None] = []

    def prepare_restore(
        target: ConversationRecordV2,
        *,
        bootstrap: Literal["recorded", "live"] | None = None,
    ) -> tuple[tuple[str, ...], Any, Any]:
        nonlocal preflight_completed
        result = original_preflight(target, bootstrap=bootstrap)
        preflight_completed = True
        return result

    @asynccontextmanager
    async def observe_admission(*, block_input: bool = False):
        nonlocal admission_held
        del block_input
        admission_held = True
        try:
            yield
        finally:
            admission_held = False

    def cancel_materialization(plan: Any) -> Any:
        assert preflight_completed
        assert admission_held
        assert recorder._lock.locked()
        raise original

    async def release_active_id(id: str | None) -> None:
        released_ids.append(id)

    controller._prepare_exchange_restore = prepare_restore  # type: ignore[method-assign]
    fake_chat._destructive_history_mutation = observe_admission  # type: ignore[method-assign]
    recorder._materialize_live_restore_turns = cancel_materialization  # type: ignore[method-assign]
    fake_chat.set_greeting = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("cleanup greeting failure")
    )
    controller.on_active_id_change = release_active_id
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    with pytest.raises(asyncio.CancelledError) as raised:
        await controller.replay_exchange_record(target)

    assert raised.value is original
    assert recorder.record is None
    assert controller.record is None
    assert controller._active_id_now() is None
    assert released_ids == [None]
    assert fake_chat.clear_messages_calls == 1
    assert fake_chat.messages == []
    assert fake_chat._transcript.read() == ()
    assert adapter.set_calls == [[]]
    assert adapter.turns == []
    history_updates = [
        action for action in fake_chat.actions if action["type"] == "history_update"
    ]
    assert len(history_updates) == 1
    assert history_updates[0]["active_id"] is None
    assert history_updates[0]["transition_protocol"] == "completion-v2"
    notifier.assert_awaited_once_with(recovery_incomplete=True)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure",
    [
        "clear",
        "greeting",
        "replay-0",
        "replay-1",
        "replay-2",
        "turns",
        "hook",
        "active-id",
        "app-callback",
        "metadata",
    ],
)
async def test_v2_restore_failure_becomes_fresh_draft(
    failure: str,
) -> None:
    store = InMemoryConversationStore()
    adapter = _TrackingFakeAdapter()
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
        adapter=adapter,
    )
    _install_live_v2_record(controller)
    target = _restore_target()
    await store.put(part(), target)
    fake_chat = cast(_FakeChat, controller.chat)
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]
    expected = RuntimeError(f"injected {failure} failure")

    if failure == "clear":
        fake_chat.clear_messages = AsyncMock(side_effect=expected)  # type: ignore[method-assign]
    elif failure == "greeting":
        fake_chat.set_greeting = AsyncMock(side_effect=expected)  # type: ignore[method-assign]
    elif failure.startswith("replay-"):
        fail_at = int(failure.removeprefix("replay-"))
        replay_count = 0

        async def fail_replay(
            _message: Any, *, icon: str | None = None
        ) -> None:
            nonlocal replay_count
            if replay_count == fail_at:
                raise expected
            replay_count += 1

        fake_chat._restore_bookmark_message = fail_replay  # type: ignore[method-assign]
    elif failure == "turns":
        original_set_turns = adapter.set_turns_json

        def fail_turns(turns: list[Any]) -> None:
            if turns:
                raise expected
            original_set_turns(turns)

        adapter.set_turns_json = fail_turns  # type: ignore[method-assign]
    elif failure == "hook":
        recorder = controller._exchange_recorder
        assert recorder is not None
        target.nodes["n_0000"].state["test:failure"] = StateEntry(
            kind="test", version=1, mode="snapshot", data={}
        )

        def fail_hook(_context: StatePathContext) -> None:
            raise expected

        recorder._register_restore_hook("test:failure", fail_hook)
    elif failure == "active-id":

        async def fail_active_id(_id: str | None) -> None:
            if _id == target.id:
                raise expected

        controller.on_active_id_change = fail_active_id
    elif failure == "app-callback":

        def fail_app_callback(_values: dict[str, Any]) -> None:
            raise expected

        controller._restore_callbacks.append(fail_app_callback)
    elif failure == "metadata":
        controller.send_history_update = AsyncMock(side_effect=expected)  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match=expected.args[0]):
        await controller.replay_exchange_record(target)

    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.record is None
    assert controller._active_id_now() is None
    assert adapter.turns == []
    assert await store.get(part(), target.id) is target
    notifier.assert_awaited_once()


@pytest.mark.anyio
async def test_v2_restore_cancellation_preserves_outcome_after_cleanup_failure():
    controller, _ = _make_controller(use_exchange_tree=True)
    _install_live_v2_record(controller)
    target = _restore_target()
    fake_chat = cast(_FakeChat, controller.chat)
    original_clear = fake_chat.clear_messages
    clear_calls = 0

    async def fail_cleanup_clear() -> None:
        nonlocal clear_calls
        clear_calls += 1
        if clear_calls > 1:
            raise RuntimeError("cleanup clear failed")
        await original_clear()

    fake_chat.clear_messages = fail_cleanup_clear  # type: ignore[method-assign]
    fake_chat._restore_bookmark_message = AsyncMock(  # type: ignore[method-assign]
        side_effect=asyncio.CancelledError()
    )
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    with pytest.raises(asyncio.CancelledError):
        await controller.replay_exchange_record(target)

    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.record is None
    assert controller._active_id_now() is None
    notifier.assert_awaited_once_with(recovery_incomplete=True)


@pytest.mark.anyio
async def test_v2_restore_active_id_cancellation_cleans_up_and_preserves_identity():
    adapter = _TrackingFakeAdapter()
    controller, _ = _make_controller(
        use_exchange_tree=True,
        adapter=adapter,
    )
    _install_live_v2_record(controller)
    target = _restore_target()
    fake_chat = cast(_FakeChat, controller.chat)
    fake_chat.messages = [_stored_message("assistant", "live")]
    original = asyncio.CancelledError("target active-ID cancellation")
    callback_ids: list[str | None] = []
    target_callback_state: list[
        tuple[ConversationRecordV2 | None, str | None]
    ] = []

    async def active_id_callback(id: str | None) -> None:
        callback_ids.append(id)
        if id == target.id:
            recorder = controller._exchange_recorder
            assert recorder is not None
            target_callback_state.append(
                (recorder.record, controller._active_id_now())
            )
            raise original

    controller.on_active_id_change = active_id_callback

    with pytest.raises(asyncio.CancelledError) as raised:
        await controller.replay_exchange_record(target)

    recorder = controller._exchange_recorder
    assert recorder is not None
    assert raised.value is original
    assert target_callback_state == [(target, target.id)]
    assert callback_ids == [target.id, None]
    assert recorder.record is None
    assert controller._active_id_now() is None
    assert fake_chat.clear_messages_calls == 2
    assert fake_chat.messages == []
    assert adapter.turns == []


@pytest.mark.anyio
async def test_v2_restore_notification_cancellation_preserves_original_instance():
    controller, _ = _make_controller(use_exchange_tree=True)
    _install_live_v2_record(controller)
    target = _restore_target()
    fake_chat = cast(_FakeChat, controller.chat)
    original = asyncio.CancelledError("original restore cancellation")
    notification = asyncio.CancelledError("notification cancellation")
    fake_chat._restore_bookmark_message = AsyncMock(  # type: ignore[method-assign]
        side_effect=original
    )
    notifier = AsyncMock(side_effect=notification)
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    with pytest.raises(asyncio.CancelledError) as raised:
        await controller.replay_exchange_record(target)

    assert raised.value is original
    notifier.assert_awaited_once_with(recovery_incomplete=False)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "cleanup",
    ["messages", "turns", "greeting", "active-id", "metadata"],
)
async def test_v2_restore_cleanup_failures_are_secondary_and_reported(
    cleanup: str,
) -> None:
    adapter = _TrackingFakeAdapter()
    controller, _ = _make_controller(
        use_exchange_tree=True,
        adapter=adapter,
    )
    _install_live_v2_record(controller)
    target = _restore_target()
    fake_chat = cast(_FakeChat, controller.chat)
    original = RuntimeError("original restore failure")
    cleanup_error = RuntimeError(f"{cleanup} cleanup failure")
    fake_chat._restore_bookmark_message = AsyncMock(  # type: ignore[method-assign]
        side_effect=original
    )

    if cleanup == "messages":
        original_clear = fake_chat.clear_messages
        clear_calls = 0

        async def fail_cleanup_clear() -> None:
            nonlocal clear_calls
            clear_calls += 1
            if clear_calls == 1:
                await original_clear()
                return
            raise cleanup_error

        fake_chat.clear_messages = fail_cleanup_clear  # type: ignore[method-assign]
    elif cleanup == "turns":

        def fail_cleanup_turns(_turns: list[Any]) -> None:
            raise cleanup_error

        adapter.set_turns_json = fail_cleanup_turns  # type: ignore[method-assign]
    elif cleanup == "greeting":
        original_greeting = fake_chat.set_greeting
        greeting_calls = 0

        async def fail_cleanup_greeting(value: Any) -> None:
            nonlocal greeting_calls
            greeting_calls += 1
            if greeting_calls == 1:
                await original_greeting(value)
                return
            raise cleanup_error

        fake_chat.set_greeting = fail_cleanup_greeting  # type: ignore[method-assign]
    elif cleanup == "active-id":
        controller.on_active_id_change = AsyncMock(side_effect=cleanup_error)
    else:
        controller.send_history_update = AsyncMock(side_effect=cleanup_error)  # type: ignore[method-assign]

    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="original restore failure"):
        await controller.replay_exchange_record(target)

    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.record is None
    assert controller._active_id_now() is None
    notifier.assert_awaited_once_with(recovery_incomplete=True)


@pytest.mark.anyio
async def test_v2_restore_cleanup_continues_after_earlier_failure():
    adapter = _TrackingFakeAdapter()
    controller, _ = _make_controller(
        use_exchange_tree=True,
        adapter=adapter,
    )
    _install_live_v2_record(controller)
    target = _restore_target()
    fake_chat = cast(_FakeChat, controller.chat)
    original_clear = fake_chat.clear_messages
    original_greeting = fake_chat.set_greeting
    original_set_turns = adapter.set_turns_json
    events: list[str] = []
    clear_calls = 0
    greeting_calls = 0

    async def clear() -> None:
        nonlocal clear_calls
        clear_calls += 1
        if clear_calls == 2:
            events.append("messages")
            raise RuntimeError("cleanup messages failure")
        events.append("initial-clear")
        await original_clear()

    def set_turns(turns: list[Any]) -> None:
        events.append("turns")
        original_set_turns(turns)

    async def greeting(value: Any) -> None:
        nonlocal greeting_calls
        greeting_calls += 1
        events.append("initial-greeting" if greeting_calls == 1 else "greeting")
        await original_greeting(value)

    async def active_id(_id: str | None) -> None:
        events.append("active-id")

    async def metadata() -> None:
        events.append("metadata")

    async def notify(*, recovery_incomplete: bool) -> None:
        assert recovery_incomplete
        events.append("notification")

    fake_chat.clear_messages = clear  # type: ignore[method-assign]
    fake_chat.set_greeting = greeting  # type: ignore[method-assign]
    fake_chat._restore_bookmark_message = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("original restore failure")
    )
    adapter.set_turns_json = set_turns  # type: ignore[method-assign]
    controller.on_active_id_change = active_id
    controller.send_history_update = metadata  # type: ignore[method-assign]
    controller._notify_restore_failure = notify  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="original restore failure"):
        await controller.replay_exchange_record(target)

    assert events == [
        "initial-clear",
        "initial-greeting",
        "messages",
        "turns",
        "greeting",
        "active-id",
        "metadata",
        "notification",
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("recovery_incomplete", "expected_message"),
    [
        (
            False,
            "Could not restore conversation. A fresh chat is ready.",
        ),
        (
            True,
            "Could not restore conversation. Recovery was incomplete; reload "
            "before starting a new chat.",
        ),
    ],
)
async def test_notify_restore_failure_emits_recovery_message(
    recovery_incomplete: bool, expected_message: str
) -> None:
    from shiny.module import ResolvedId

    class _NotificationSession:
        ns = ResolvedId("")

    controller, _ = _make_controller(use_exchange_tree=True)
    fake_chat = cast(_FakeChat, controller.chat)
    cast(Any, fake_chat)._session = _NotificationSession()

    with patch("shiny.ui.notification_show") as notification_show:
        await controller._notify_restore_failure(
            recovery_incomplete=recovery_incomplete
        )

    notification_show.assert_called_once_with(expected_message, type="error")


@pytest.mark.anyio
async def test_v2_restore_failure_allows_next_input_to_record_normally():
    store = InMemoryConversationStore()
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
    )
    existing = _install_live_v2_record(controller)
    target = _restore_target()
    existing_before = existing.model_copy(deep=True)
    target_before = target.model_copy(deep=True)
    fake_chat = cast(_FakeChat, controller.chat)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = fake_chat._transcript
    transcript.set_capture_callbacks(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )

    async def fail_send() -> bool:
        assert transcript._on_accepted_input is None
        assert transcript._on_message_committed is None
        assert transcript._on_stream_started is None
        assert transcript._on_stream_updated is None
        assert transcript._on_stream_finished is None
        raise RuntimeError("replay failed")

    async def replay_through_transcript(
        message: Any, *, icon: str | None = None
    ) -> None:
        await transcript.append(
            TranscriptEntry(
                message=StoredMessage.model_validate(message), icon=icon
            ),
            exchange_id=None,
            send=fail_send,
        )

    fake_chat._restore_bookmark_message = replay_through_transcript  # type: ignore[method-assign]
    controller._notify_restore_failure = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="replay failed"):
        await controller.replay_exchange_record(target)

    assert recorder.record is None
    assert controller._active_id_now() is None
    assert existing == existing_before
    assert target == target_before
    assert transcript._on_accepted_input == recorder.accepted_input
    assert transcript._on_message_committed == recorder.message_committed
    assert transcript._on_stream_started == recorder.stream_started
    assert transcript._on_stream_updated == recorder.stream_updated
    assert transcript._on_stream_finished == recorder.stream_finished

    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "fresh input")
    )

    assert recorder.record is not None
    assert recorder.record.id != target.id
    assert recorder.record.id != existing.id
    fresh_node = recorder.record.nodes[exchange_id]
    assert fresh_node.input is not None
    assert fresh_node.input.content == "fresh input"
    assert existing == existing_before


@pytest.mark.anyio
async def test_v2_restore_suppresses_real_transcript_capture_then_restores_it():
    controller, _ = _make_controller(use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    fake_chat = cast(_FakeChat, controller.chat)
    fake_chat._transcript.set_capture_callbacks(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=None,
        on_stream_updated=None,
        on_stream_finished=None,
    )
    target = _restore_target()

    async def replay_through_transcript(
        message: Any, *, icon: str | None = None
    ) -> None:
        await fake_chat._transcript.append(
            TranscriptEntry(
                message=StoredMessage.model_validate(message), icon=icon
            ),
            exchange_id=None,
            send=_sent,
        )

    fake_chat._restore_bookmark_message = replay_through_transcript  # type: ignore[method-assign]
    await controller.replay_exchange_record(target)

    assert recorder.record is target
    assert len(target.nodes) == 2
    await fake_chat._transcript.record_accepted_input_and_notify(
        _stored_message("user", "after restore")
    )
    assert len(target.nodes) == 3


@pytest.mark.anyio
async def test_v2_restore_success_order_and_no_failure_notification():
    adapter = _TrackingFakeAdapter()
    controller, _ = _make_controller(
        use_exchange_tree=True,
        adapter=adapter,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    target = _restore_target()
    events: list[str] = []
    fake_chat = cast(_FakeChat, controller.chat)
    original_clear = fake_chat.clear_messages
    original_greeting = fake_chat.set_greeting
    original_replay = fake_chat._restore_bookmark_message
    original_set_turns = adapter.set_turns_json
    original_install = recorder.install_restored_record

    async def clear() -> None:
        events.append("clear")
        await original_clear()

    async def greeting(value: Any) -> None:
        events.append("greeting")
        await original_greeting(value)

    async def replay(message: Any, *, icon: str | None = None) -> None:
        events.append("replay")
        await original_replay(message, icon=icon)

    def set_turns(turns: list[Any]) -> None:
        events.append("turns")
        original_set_turns(turns)

    def install(record: ConversationRecordV2) -> None:
        events.append("install")
        original_install(record)

    async def active_id(_id: str | None) -> None:
        events.append("active-id")

    def app_callback(_values: dict[str, Any]) -> None:
        events.append("app-callback")

    async def metadata() -> None:
        events.append("metadata")

    fake_chat.clear_messages = clear  # type: ignore[method-assign]
    fake_chat.set_greeting = greeting  # type: ignore[method-assign]
    fake_chat._restore_bookmark_message = replay  # type: ignore[method-assign]
    adapter.set_turns_json = set_turns  # type: ignore[method-assign]
    recorder.install_restored_record = install  # type: ignore[method-assign]
    controller.on_active_id_change = active_id
    controller._restore_callbacks.append(app_callback)
    controller.send_history_update = metadata  # type: ignore[method-assign]
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    await controller.replay_exchange_record(target)

    assert events == [
        "clear",
        "greeting",
        "replay",
        "replay",
        "replay",
        "turns",
        "install",
        "active-id",
        "app-callback",
        "metadata",
    ]
    notifier.assert_not_awaited()


@pytest.mark.anyio
async def test_v2_recorder_allocates_controller_id_before_root_capture():
    controller, _ = _make_controller(use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    observed_ids: list[str | None] = []

    def capture_id(_context: Any) -> None:
        observed_ids.append(controller._active_id_now())

    recorder._register_capture_hook("test:active-id", capture_id)
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "hello")
    )

    assert recorder.record is not None
    assert recorder.record.id == controller._active_id_now()
    assert observed_ids == [recorder.record.id]


@pytest.mark.anyio
async def test_v2_inputless_capture_allocates_controller_id():
    controller, _ = _make_controller(use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None

    await recorder.message_committed(
        None, TranscriptEntry(message=_stored_message("assistant", "notice"))
    )

    assert recorder.record is not None
    assert recorder.record.id == controller._active_id_now()


@pytest.mark.anyio
async def test_v2_active_id_callback_runs_after_first_store_write():
    store = InMemoryConversationStore()
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    persisted: list[ConversationRecordV2 | None] = []

    async def update_url(conv_id: str | None) -> None:
        assert conv_id is not None
        persisted.append(await store.get(part(), conv_id))

    controller.on_active_id_change = update_url
    await controller.ensure_conversation_id()
    assert persisted == []
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "hello")
    )

    assert recorder.record is not None
    assert persisted == [recorder.record]


@pytest.mark.anyio
async def test_v2_active_id_callback_retries_after_first_store_failure():
    class FailFirstStore(InMemoryConversationStore):
        fail_first_put = True

        async def put(
            self, partition: ConversationPartition, record: Any
        ) -> None:
            if self.fail_first_put:
                self.fail_first_put = False
                raise RuntimeError("durability failure")
            await super().put(partition, record)

    store = FailFirstStore()
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    persisted: list[ConversationRecordV2 | None] = []

    async def update_url(conv_id: str | None) -> None:
        assert conv_id is not None
        persisted.append(await store.get(part(), conv_id))

    controller.on_active_id_change = update_url
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
    )

    with pytest.raises(RuntimeError, match="durability failure"):
        await transcript.record_accepted_input_and_notify(
            _stored_message("user", "hello")
        )

    active_id = controller._active_id_now()
    assert active_id is not None
    assert persisted == []
    assert await store.get(part(), active_id) is None

    await recorder.message_committed(
        None,
        TranscriptEntry(message=_stored_message("assistant", "hi")),
    )

    assert recorder.record is not None
    assert persisted == [recorder.record]
    assert persisted[0] == await store.get(part(), active_id)


@pytest.mark.anyio
async def test_v2_active_delete_waits_for_blocked_write_and_clears_state():
    class BlockFirstStore(InMemoryConversationStore):
        started = asyncio.Event()
        release = asyncio.Event()
        first_put = True
        events: list[str] = []

        async def put(
            self, partition: ConversationPartition, record: Any
        ) -> None:
            if self.first_put:
                self.first_put = False
                self.started.set()
                await self.release.wait()
            self.events.append("put")
            await super().put(partition, record)

        async def delete(
            self, partition: ConversationPartition, conv_id: str
        ) -> None:
            self.events.append("delete")
            await super().delete(partition, conv_id)

    store = BlockFirstStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    fake_chat = cast(_FakeChat, controller.chat)
    fake_chat.messages = [_stored_message("assistant", "visible")]
    published: list[str | None] = []

    async def update_url(conv_id: str | None) -> None:
        published.append(conv_id)

    controller.on_active_id_change = update_url

    async def on_evict(_conv_id: str) -> None:
        store.events.append("evict")

    controller.on_evict = on_evict
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    fake_chat._transcript = transcript

    first_write = asyncio.create_task(
        transcript.record_accepted_input_and_notify(
            _stored_message("user", "A")
        )
    )
    await store.started.wait()
    first_id = controller._active_id_now()
    assert first_id is not None

    controller.adapter.set_turns_json([{"role": "user", "content": "A"}])
    delete_task = asyncio.create_task(controller.delete(first_id))
    await asyncio.sleep(0)
    assert not delete_task.done()
    assert store.events == []

    store.release.set()
    await first_write
    await delete_task

    assert store.events == ["put", "evict", "delete"]
    assert published == [first_id, None]
    assert await store.get(part(), first_id) is None
    assert recorder.record is None
    assert controller._active_id_now() is None
    assert controller.adapter.get_turns_json() == []
    assert fake_chat._transcript.read() == ()
    assert fake_chat.messages == []


@pytest.mark.anyio
async def test_v2_new_chat_waits_for_blocked_active_id_callback():
    controller, _ = _make_controller(use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    fake_chat = cast(_FakeChat, controller.chat)
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    fake_chat._transcript = transcript
    published: list[str | None] = []
    callback_started = asyncio.Event()
    release_callback = asyncio.Event()

    async def update_url(conv_id: str | None) -> None:
        published.append(conv_id)
        if conv_id is not None:
            callback_started.set()
            await release_callback.wait()

    controller.on_active_id_change = update_url
    first_write = asyncio.create_task(
        transcript.record_accepted_input_and_notify(
            _stored_message("user", "A")
        )
    )
    await callback_started.wait()
    first_id = controller._active_id_now()
    assert first_id is not None

    new_chat = asyncio.create_task(controller.new_chat())
    await asyncio.sleep(0)
    assert not new_chat.done()

    release_callback.set()
    await first_write
    await new_chat

    assert published == [first_id, None]
    assert recorder.record is None
    assert controller._active_id_now() is None


@pytest.mark.anyio
@pytest.mark.parametrize("callback_error", ["failure", "cancellation"])
async def test_v2_callback_failure_or_cancellation_retries_for_same_record(
    callback_error: str,
):
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    fake_chat = cast(_FakeChat, controller.chat)
    calls: list[str | None] = []
    fail_first = True

    async def update_url(conv_id: str | None) -> None:
        nonlocal fail_first
        calls.append(conv_id)
        if fail_first:
            fail_first = False
            if callback_error == "cancellation":
                raise asyncio.CancelledError()
            raise RuntimeError("URL update failed")

    controller.on_active_id_change = update_url
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
    )
    fake_chat._transcript = transcript

    with pytest.raises(
        asyncio.CancelledError
        if callback_error == "cancellation"
        else RuntimeError,
        match=None if callback_error == "cancellation" else "URL update failed",
    ):
        await transcript.record_accepted_input_and_notify(
            _stored_message("user", "first")
        )

    assert recorder.record is not None
    first_id = recorder.record.id
    await recorder.message_committed(
        None,
        TranscriptEntry(message=_stored_message("assistant", "retry")),
    )
    assert calls == [first_id, first_id]

    await controller.new_chat()
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "second")
    )
    assert recorder.record is not None
    second_id = recorder.record.id
    assert second_id != first_id
    assert calls == [first_id, first_id, None, second_id]
    assert await store.get(part(), second_id) is recorder.record


@pytest.mark.anyio
@pytest.mark.parametrize("use_exchange_tree", [False, True])
@pytest.mark.parametrize("callback_error", ["failure", "cancellation"])
async def test_active_delete_clears_local_state_before_callback_failure(
    use_exchange_tree: bool, callback_error: str
):
    store = InMemoryConversationStore()
    controller, _ = _make_controller(
        store=store, use_exchange_tree=use_exchange_tree
    )
    fake_chat = cast(_FakeChat, controller.chat)
    fake_chat.messages = [_stored_message("assistant", "visible")]
    fake_chat._transcript.record_accepted_input(
        _stored_message("user", "input")
    )
    controller.adapter.set_turns_json([{"role": "user", "content": "input"}])

    recorder = controller._exchange_recorder
    if use_exchange_tree:
        assert recorder is not None
        transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
        fake_chat._transcript = transcript
        await transcript.record_accepted_input_and_notify(
            _stored_message("user", "input")
        )
        assert recorder.record is not None
        active_id = recorder.record.id
    else:
        active_id = await controller.ensure_conversation_id()
        record = new_conversation_record(title="active", id=active_id)
        controller.record = record
        await store.put(part(), record)

    async def update_url(conv_id: str | None) -> None:
        assert conv_id is None
        if callback_error == "cancellation":
            raise asyncio.CancelledError()
        raise RuntimeError("URL clear failed")

    controller.on_active_id_change = update_url
    with pytest.raises(
        asyncio.CancelledError
        if callback_error == "cancellation"
        else RuntimeError,
        match=None if callback_error == "cancellation" else "URL clear failed",
    ):
        await controller.delete(active_id)

    assert await store.get(part(), active_id) is None
    assert controller.record is None
    assert controller._active_id_now() is None
    assert controller.adapter.get_turns_json() == []
    assert fake_chat.messages == []
    assert fake_chat._transcript.read() == ()
    assert fake_chat.clear_messages_calls == 1
    if recorder is not None:
        assert recorder.record is None


@pytest.mark.anyio
async def test_v2_new_chat_resets_recorder_and_allocates_a_new_id():
    controller, _ = _make_controller(use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "first")
    )
    assert recorder.record is not None
    first_id = recorder.record.id

    await controller.new_chat()
    assert recorder.record is None
    assert controller._active_id_now() is None

    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "second")
    )
    assert recorder.record is not None
    assert recorder.record.id != first_id
    assert recorder.record.id == controller._active_id_now()


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["new_chat", "delete"])
async def test_v2_destructive_active_id_callback_observes_reset(
    operation: str,
):
    store = InMemoryConversationStore()
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "hello")
    )
    assert recorder.record is not None

    observed: list[ConversationRecordV2 | None] = []

    async def active_id_callback(_conv_id: str | None) -> None:
        await asyncio.sleep(0)
        observed.append(recorder.record)

    controller.on_active_id_change = active_id_callback
    if operation == "new_chat":
        await controller.new_chat()
    else:
        await controller.delete(recorder.record.id)

    assert observed == [None]


@pytest.mark.anyio
async def test_v2_recorder_captures_postpartition_root_ui_but_not_greeting():
    from shiny.module import ResolvedId
    from shiny.session import session_context
    from shinychat import Chat

    class GreetingSession:
        ns = ResolvedId("")
        app: object = None
        id = "history-acceptance-session"

        async def send_custom_message(self, _type: str, _message: Any) -> None:
            pass

        def on_ended(self, _callback: object) -> Callable[[], None]:
            return lambda: None

        def on_destroy(self, _callback: object) -> None:
            pass

        def _increment_busy_count(self) -> None:
            pass

        def _decrement_busy_count(self) -> None:
            pass

    session = GreetingSession()
    with session_context(cast(Any, session)):
        real_chat = Chat("history_acceptance", history=False)

    adapter = _FakeAdapter()
    controller, _ = _make_controller(
        use_exchange_tree=True,
        adapter=adapter,
    )
    controller.chat = real_chat  # type: ignore[assignment]
    recorder = controller._exchange_recorder
    assert recorder is not None
    real_chat._transcript.set_capture_callbacks(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )

    await real_chat.set_greeting("ambient greeting")
    await real_chat._transcript.append(
        TranscriptEntry(message=_stored_message("assistant", "pre-input UI")),
        exchange_id=None,
        send=_sent,
    )
    exchange_id = await real_chat._transcript.record_accepted_input_and_notify(
        _stored_message("user", "question")
    )

    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    root = record.nodes["n_0000"]
    assert root.input is None
    assert root.state["shinychat:turns"].mode == "snapshot"
    assert root.state["shinychat:turns"].data == adapter.turns
    assert [
        message.as_stored_message().content for message in root.messages
    ] == ["pre-input UI"]
    assert all(
        "ambient greeting" not in message.as_stored_message().content
        for message in root.messages
    )
    assert record.nodes[exchange_id].input is not None


@pytest.mark.anyio
async def test_v2_recorder_runs_ordered_hooks_with_explicit_ids_and_removes_state():
    controller, _ = _make_controller(use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    observed: list[tuple[str, str, str]] = []

    def first(context: Any) -> StateEntry:
        observed.append(("first", context.node_id, context.reason))
        return StateEntry(
            kind="test",
            version=1,
            mode="snapshot",
            data={"reason": context.reason},
        )

    def second(context: Any) -> StateEntry:
        observed.append(("second", context.node_id, context.reason))
        return StateEntry(
            kind="test",
            version=1,
            mode="snapshot",
            data={"node": context.node_id},
        )

    recorder._register_capture_hook("first", first)
    recorder._register_capture_hook("second", second)
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "one")
    )

    root = recorder.record.nodes["n_0000"]  # type: ignore[union-attr]
    assert observed == [
        ("first", "n_0000", "root_close"),
        ("second", "n_0000", "root_close"),
    ]
    assert root.state["first"].data == {"reason": "root_close"}
    assert root.state["second"].data == {"node": "n_0000"}

    recorder._register_capture_hook("first", lambda _context: None)
    await recorder._capture_state("n_0000", "node_close")
    assert "first" not in root.state
    assert root.state["second"].data == {"node": "n_0000"}


def _make_v2_resubmit_controller() -> tuple[
    HistoryController, _FakeChat, _FakeAdapter, _RecordingStore, str, str
]:
    controller, store = _make_controller(use_exchange_tree=True)
    fake_chat = cast(_FakeChat, controller.chat)
    adapter = cast(_FakeAdapter, controller.adapter)
    recorder = controller._exchange_recorder
    assert recorder is not None

    record = new_conversation_record_v2(
        title="branching",
        id="c_branching",
        client_info={},
    )
    record.nodes["n_0000"].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[{"role": "system", "content": "bootstrap"}],
    )
    first = "exchange-first"
    target = "exchange-target"
    record.open_exchange(first, _stored_message("user", "first"))
    record.nodes[first].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[{"role": "user", "content": "first"}],
    )
    record.open_exchange(target, _stored_message("user", "second"))
    record.nodes[target].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[{"role": "user", "content": "second"}],
    )
    recorder.record = record
    controller._active_id.set(record.id)
    adapter.turns = [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "second"},
    ]
    recorder._set_turn_baseline(adapter.turns)
    fake_chat._transcript.set_capture_callbacks(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )
    return controller, fake_chat, adapter, store, first, target


def _make_v2_navigation_controller() -> tuple[
    HistoryController, _FakeChat, _FakeAdapter, _RecordingStore, str, str
]:
    controller, store = _make_controller(use_exchange_tree=True)
    fake_chat = cast(_FakeChat, controller.chat)
    adapter = cast(_FakeAdapter, controller.adapter)
    recorder = controller._exchange_recorder
    assert recorder is not None

    record = new_conversation_record_v2(
        title="branching",
        id="c_navigation",
        client_info={},
    )
    record.nodes["n_0000"].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[{"role": "system", "content": "bootstrap"}],
    )
    first = "exchange-first"
    original = "exchange-original"
    replacement = "exchange-replacement"
    record.open_exchange(first, _stored_message("user", "first"))
    record.nodes[first].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[{"role": "user", "content": "first"}],
    )
    record.append_message(
        first,
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "custom prefix"), icon=None
        ),
    )
    record.open_exchange(original, _stored_message("user", "original"))
    record.nodes[original].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[{"role": "user", "content": "original"}],
    )
    record.append_message(
        original,
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "original reply"), icon=None
        ),
    )
    record.set_active_leaf(first)
    record.open_exchange(
        replacement, _stored_message("user", "replacement")
    )
    record.nodes[replacement].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[{"role": "user", "content": "replacement"}],
    )
    record.append_message(
        replacement,
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "replacement reply"), icon=None
        ),
    )
    recorder.record = record
    controller._active_id.set(record.id)
    adapter.turns = [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "replacement"},
    ]
    recorder._set_turn_baseline(adapter.turns)
    return controller, fake_chat, adapter, store, original, replacement


@pytest.mark.anyio
async def test_v2_navigation_replays_selected_sibling_and_rewinds_turns():
    controller, chat, adapter, store, original, replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None

    await controller.handle_navigate(2, "prev", request_id="navigation")

    assert record.active_leaf == original
    assert record.nodes["exchange-first"].selected_child == original
    assert record.nodes[original].selected_child is None
    assert adapter.turns == [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "original"},
    ]
    assert [
        message["segments"][0]["content"] for message in chat.restored_messages
    ] == ["first", "custom prefix", "original", "original reply"]
    assert chat.actions[-3] == {
        "type": "update_siblings",
        "data": {2: {"index": 0, "total": 2}},
    }
    assert chat.actions[-2] == {
        "type": "update_exchange_metadata",
        "data": {
            0: {"status": "ok", "retryable": False},
            2: {"status": "ok", "retryable": False},
        },
    }
    assert chat.actions[-1]["type"] == "history_update"
    assert len(store.put_calls) == 1
    assert store.put_calls[0][1].active_leaf == original
    assert record.nodes["exchange-first"].children == [original, replacement]


def _make_v2_navigation_controller_with_remembered_descendants() -> tuple[
    HistoryController,
    _FakeChat,
    _FakeAdapter,
    _RecordingStore,
    str,
    str,
    str,
    str,
]:
    controller, store = _make_controller(use_exchange_tree=True)
    chat = cast(_FakeChat, controller.chat)
    adapter = cast(_FakeAdapter, controller.adapter)
    recorder = controller._exchange_recorder
    assert recorder is not None

    record = new_conversation_record_v2(
        title="remembered descendants",
        id="c_remembered_descendants",
        client_info={},
    )
    record.nodes["n_0000"].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[{"role": "system", "content": "bootstrap"}],
    )
    first = "exchange-first"
    original = "exchange-original"
    original_followup = "exchange-original-followup"
    replacement = "exchange-replacement"
    replacement_followup = "exchange-replacement-followup"

    record.open_exchange(first, _stored_message("user", "first"))
    record.nodes[first].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[{"role": "user", "content": "first"}],
    )
    record.append_message(
        first,
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "custom prefix"), icon=None
        ),
    )

    record.open_exchange(original, _stored_message("user", "original"))
    record.nodes[original].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[{"role": "user", "content": "original"}],
    )
    record.append_message(
        original,
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "original reply"), icon=None
        ),
    )
    record.open_exchange(
        original_followup, _stored_message("user", "original followup")
    )
    record.nodes[original_followup].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[{"role": "user", "content": "original followup"}],
    )
    record.append_message(
        original_followup,
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "original followup reply"), icon=None
        ),
    )

    record.set_active_leaf(first)
    record.open_exchange(replacement, _stored_message("user", "replacement"))
    record.nodes[replacement].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[{"role": "user", "content": "replacement"}],
    )
    record.append_message(
        replacement,
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "replacement reply"), icon=None
        ),
    )
    record.open_exchange(
        replacement_followup, _stored_message("user", "replacement followup")
    )
    record.nodes[replacement_followup].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[{"role": "user", "content": "replacement followup"}],
    )
    record.append_message(
        replacement_followup,
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "replacement followup reply"),
            icon=None,
        ),
    )

    recorder.record = record
    controller._active_id.set(record.id)
    adapter.turns = [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "replacement"},
        {"role": "user", "content": "replacement followup"},
    ]
    recorder._set_turn_baseline(adapter.turns)
    return (
        controller,
        chat,
        adapter,
        store,
        original,
        original_followup,
        replacement,
        replacement_followup,
    )


@pytest.mark.anyio
async def test_v2_navigation_follows_remembered_descendants_and_persists_paths():
    (
        controller,
        chat,
        adapter,
        store,
        original,
        original_followup,
        replacement,
        replacement_followup,
    ) = _make_v2_navigation_controller_with_remembered_descendants()
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None

    await controller.handle_navigate(2, "prev", request_id="previous")

    assert record.active_leaf == original_followup
    assert record.nodes["n_0000"].selected_child == "exchange-first"
    assert record.nodes["exchange-first"].selected_child == original
    assert record.nodes[original].selected_child == original_followup
    assert record.nodes[replacement].selected_child == replacement_followup
    assert adapter.turns == [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "original"},
        {"role": "user", "content": "original followup"},
    ]
    assert [
        message["segments"][0]["content"] for message in chat.restored_messages
    ] == [
        "first",
        "custom prefix",
        "original",
        "original reply",
        "original followup",
        "original followup reply",
    ]
    persisted_previous = store.put_calls[-1][1].model_copy(deep=True)
    assert persisted_previous.active_leaf == original_followup
    assert (
        persisted_previous.nodes["exchange-first"].selected_child == original
    )
    assert persisted_previous.nodes[original].selected_child == original_followup

    puts_before_first_boundary = len(store.put_calls)
    display_before_first_boundary = list(chat.restored_messages)
    await controller.handle_navigate(2, "prev", request_id="first-boundary")
    assert len(store.put_calls) == puts_before_first_boundary
    assert record.active_leaf == original_followup
    assert chat.restored_messages == display_before_first_boundary

    chat.restored_messages.clear()
    await controller.handle_navigate(2, "next", request_id="next")

    assert record.active_leaf == replacement_followup
    assert record.nodes["exchange-first"].selected_child == replacement
    assert record.nodes[original].selected_child == original_followup
    assert record.nodes[replacement].selected_child == replacement_followup
    assert adapter.turns == [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "replacement"},
        {"role": "user", "content": "replacement followup"},
    ]
    assert [
        message["segments"][0]["content"] for message in chat.restored_messages
    ] == [
        "first",
        "custom prefix",
        "replacement",
        "replacement reply",
        "replacement followup",
        "replacement followup reply",
    ]
    persisted_next = store.put_calls[-1][1].model_copy(deep=True)
    assert persisted_next.active_leaf == replacement_followup
    assert persisted_next.nodes["exchange-first"].selected_child == replacement
    assert (
        persisted_next.nodes[replacement].selected_child == replacement_followup
    )

    puts_before_last_boundary = len(store.put_calls)
    display_before_last_boundary = list(chat.restored_messages)
    await controller.handle_navigate(2, "next", request_id="last-boundary")
    assert len(store.put_calls) == puts_before_last_boundary
    assert record.active_leaf == replacement_followup
    assert chat.restored_messages == display_before_last_boundary


@pytest.mark.anyio
async def test_v2_navigation_persistence_failure_clears_to_fresh_draft():
    controller, chat, adapter, store, original, _replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    chat.messages = [
        _stored_message("user", "first"),
        _stored_message("user", "replacement"),
    ]
    chat._transcript.replace(
        [TranscriptEntry(message=_stored_message("user", "replacement"))]
    )
    expected = RuntimeError("navigation persistence failed")
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]
    persisted_attempts: list[ConversationRecordV2] = []

    async def fail_put(
        _partition: ConversationPartition, failed_record: ConversationRecordV2
    ) -> None:
        persisted_attempts.append(failed_record.model_copy(deep=True))
        raise expected

    store.put = fail_put  # type: ignore[method-assign]

    with pytest.raises(RuntimeError) as raised:
        await controller.handle_navigate(2, "prev", request_id="navigation")

    assert raised.value is expected
    assert persisted_attempts[0].active_leaf == original
    assert (
        persisted_attempts[0].nodes["exchange-first"].selected_child == original
    )
    assert recorder.record is None
    assert controller.record is None
    assert controller._active_id_now() is None
    assert recorder._turn_baseline == []
    assert adapter.turns == []
    assert chat.messages == []
    assert chat._transcript.read() == ()
    assert chat.clear_messages_calls == 1
    assert chat.set_greeting_calls == [None]
    assert chat.actions == [
        {
            "type": "history_update",
            "enabled": True,
            "conversations": [],
            "active_id": None,
            "transition_protocol": "completion-v2",
        }
    ]
    notifier.assert_awaited_once_with(recovery_incomplete=False)


@pytest.mark.anyio
@pytest.mark.parametrize("stage", ["replay", "rewind"])
async def test_v2_navigation_cancellation_clears_to_fresh_draft(
    stage: str,
) -> None:
    controller, chat, adapter, store, original, _replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    chat.messages = [_stored_message("user", "replacement")]
    chat._transcript.replace(
        [TranscriptEntry(message=_stored_message("user", "replacement"))]
    )
    replayed_display: list[dict[str, Any]] = []
    original_restore_message = chat._restore_bookmark_message

    async def restore_message(
        message_dict: dict[str, Any], *, icon: str | None = None
    ) -> None:
        chat.messages.append(message_dict)
        await original_restore_message(message_dict, icon=icon)

    chat._restore_bookmark_message = restore_message  # type: ignore[method-assign]
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    if stage == "replay":
        original_replay = controller._replay_exchange_display

        async def cancel_replay(
            target: ConversationRecordV2, node_ids: tuple[str, ...]
        ) -> None:
            await original_replay(target, node_ids)
            replayed_display.extend(chat.messages)
            raise asyncio.CancelledError()

        controller._replay_exchange_display = cancel_replay  # type: ignore[method-assign]
    else:
        original_rewind = recorder._rewind_state

        async def cancel_rewind(plan: Any) -> None:
            await original_rewind(plan)
            replayed_display.extend(chat.messages)
            raise asyncio.CancelledError()

        recorder._rewind_state = cancel_rewind  # type: ignore[method-assign]

    with pytest.raises(asyncio.CancelledError):
        await controller.handle_navigate(2, "prev", request_id="navigation")

    assert store.put_calls[0][1].active_leaf == original
    assert replayed_display == [
        _stored_message("user", "first").model_dump(mode="json"),
        _stored_message("assistant", "custom prefix").model_dump(mode="json"),
        _stored_message("user", "original").model_dump(mode="json"),
        _stored_message("assistant", "original reply").model_dump(mode="json"),
    ]
    assert recorder.record is None
    assert controller.record is None
    assert controller._active_id_now() is None
    assert recorder._turn_baseline == []
    assert adapter.turns == []
    assert chat.messages == []
    assert chat._transcript.read() == ()
    assert chat.clear_messages_calls == 2
    assert chat.set_greeting_calls == [None, None]
    assert chat.actions == [
        {
            "type": "history_update",
            "enabled": True,
            "conversations": [],
            "active_id": None,
            "transition_protocol": "completion-v2",
        }
    ]
    notifier.assert_awaited_once_with(recovery_incomplete=False)


@pytest.mark.anyio
async def test_v2_navigation_preflights_selected_path_before_mutation():
    controller, chat, adapter, store, original, replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.nodes[original].state["unsupported"] = StateEntry(
        kind="test",
        version=1,
        mode="snapshot",
        data={},
    )
    before = record.model_dump()
    turns_before = list(adapter.turns)

    with pytest.raises(ValueError, match="Unsupported rewind state entry"):
        await controller.handle_navigate(2, "prev", request_id="navigation")

    assert record.model_dump() == before
    assert adapter.turns == turns_before
    assert chat.clear_messages_calls == 0
    assert store.put_calls == []
    assert record.active_leaf == replacement


# --- v2 bookmark pointers ---------------------------------------------------


@pytest.mark.anyio
async def test_v2_bookmark_pointer_restores_selected_sibling_and_persists() -> None:
    controller, chat, adapter, store, original, replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    assert record.active_leaf == replacement

    await controller.restore_bookmark_pointer(record, original)

    restored = recorder.record
    assert restored is not None
    assert restored is not record
    assert restored.active_leaf == original
    assert restored.nodes["exchange-first"].selected_child == original
    assert adapter.turns == [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "original"},
    ]
    assert [
        message["segments"][0]["content"] for message in chat.restored_messages
    ] == ["first", "custom prefix", "original", "original reply"]
    assert store.put_calls[0][1].active_leaf == original


@pytest.mark.anyio
async def test_v2_bookmark_pointer_rejects_stale_node_before_mutation() -> None:
    controller, chat, adapter, store, _original, _replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    before = record.model_dump(mode="json")
    turns_before = list(adapter.turns)

    with pytest.raises(ValueError, match="Unknown exchange id"):
        await controller.restore_bookmark_pointer(record, "missing-node")

    assert recorder.record is record
    assert record.model_dump(mode="json") == before
    assert adapter.turns == turns_before
    assert chat.destructive_preflight_calls == 0
    assert chat.restored_messages == []
    assert store.put_calls == []


@pytest.mark.anyio
async def test_v2_bookmark_settlement_discards_late_url_and_cleans_replacements() -> (
    None
):
    controller, _chat, _adapter, store, original, replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None

    first_pointer = await recorder.bookmark_pointer(record)
    assert first_pointer == (record.id, replacement)
    assert first_pointer is not None
    current, cleanup = await recorder.settle_bookmark_state_id(
        first_pointer[0], first_pointer[1], "state-first"
    )
    assert current is True
    assert cleanup is None
    assert record.bookmark_state_id == "state-first"
    assert store.put_calls[-1][1].bookmark_state_id == "state-first"

    record.set_active_leaf(original)
    late_current, late_cleanup = await recorder.settle_bookmark_state_id(
        first_pointer[0], first_pointer[1], "state-late"
    )
    assert late_current is False
    assert late_cleanup == "state-late"
    assert record.bookmark_state_id == "state-first"

    replacement_pointer = await recorder.bookmark_pointer(record)
    assert replacement_pointer == (record.id, original)
    assert replacement_pointer is not None
    current, cleanup = await recorder.settle_bookmark_state_id(
        replacement_pointer[0], replacement_pointer[1], "state-replacement"
    )
    assert current is True
    assert cleanup == "state-first"
    assert record.bookmark_state_id == "state-replacement"


@pytest.mark.anyio
async def test_v2_resubmit_rewinds_parent_prefix_and_new_input_creates_sibling():
    controller, chat, adapter, store, first, target = _make_v2_resubmit_controller()
    recorder = controller._exchange_recorder
    assert recorder is not None
    target_input = recorder.record.nodes[target].input.model_copy(deep=True)  # type: ignore[union-attr]
    target_state = recorder.record.nodes[target].state["shinychat:turns"].model_copy(  # type: ignore[union-attr]
        deep=True
    )

    await controller.resubmit(
        target, kind="retry", request_id="request", message_index=1
    )

    record = recorder.record
    assert record is not None
    assert record.active_leaf == first
    assert adapter.turns == [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
    ]
    assert chat.actions[-1] == {
        "type": "history_edit_projection",
        "requestId": "request",
        "index": 1,
        "content": "second",
        "attachments": [],
    }
    assert len(store.put_calls) == 1
    assert record.nodes[target].input == target_input
    assert record.nodes[target].state["shinychat:turns"] == target_state

    exchange_id = await chat._transcript.record_accepted_input_and_notify(
        _stored_message("user", "second")
    )
    assert record.nodes[exchange_id].parent_id == first
    assert record.children_of(first) == [target, exchange_id]
    assert record.nodes[target].input == target_input


@pytest.mark.anyio
async def test_v2_resubmit_rejects_real_chat_input_until_replay_releases(
    request: pytest.FixtureRequest,
) -> None:
    controller, _fake_chat, _adapter, _store, first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None

    session = _RealChatSession()
    with session_context(cast(Any, session)):
        chat = Chat("history_resubmit_input", history=False)
    request.addfinalizer(chat.destroy)
    controller.chat = chat  # type: ignore[assignment]
    chat._transcript.set_capture_callbacks(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )

    rewind_started = asyncio.Event()
    release_rewind = asyncio.Event()
    original_rewind_state = recorder._rewind_state

    async def blocked_rewind_state(plan: Any) -> None:
        rewind_started.set()
        await release_rewind.wait()
        await original_rewind_state(plan)

    recorder._rewind_state = blocked_rewind_state  # type: ignore[method-assign]
    resubmit = asyncio.create_task(
        controller.resubmit(
            target, kind="retry", request_id="request", message_index=1
        )
    )
    await rewind_started.wait()

    assert chat._destructive_history_blocks_input
    with pytest.raises(
        RuntimeError,
        match="Cannot accept user input while switching conversations",
    ):
        await chat._record_accepted_user_input_with_capture(
            ChatMessage(content="competing input", role="user")
        )
    assert record.active_leaf == first
    assert record.children_of(first) == [target]

    release_rewind.set()
    await resubmit

    assert not chat._destructive_history_blocks_input
    await chat._record_accepted_user_input_with_capture(
        ChatMessage(content="second", role="user")
    )
    sibling = record.active_leaf
    assert sibling is not None
    sibling_input = record.nodes[sibling].input
    assert sibling_input is not None
    assert sibling_input.content == "second"
    assert record.children_of(first) == [target, sibling]


@pytest.mark.anyio
async def test_v2_resubmit_rewind_hooks_are_ordered_and_always_recorded():
    controller, _chat, _adapter, _store, first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.nodes["n_0000"].state["first"] = StateEntry(
        kind="test",
        version=1,
        mode="snapshot",
        data={"root": True},
    )
    record.nodes[first].state["second"] = StateEntry(
        kind="test",
        version=1,
        mode="delta",
        data={"first": True},
    )
    observed: list[tuple[str, StatePathContext]] = []

    def first_hook(context: StatePathContext) -> None:
        observed.append(("first", context))

    async def second_hook(context: StatePathContext) -> None:
        observed.append(("second", context))

    recorder._register_rewind_hook("first", first_hook)
    recorder._register_rewind_hook("second", second_hook)

    await controller.resubmit(
        target, kind="retry", request_id="request", message_index=1
    )

    assert [name for name, _ in observed] == ["first", "second"]
    assert observed[0][1].active_leaf == first
    assert observed[0][1].node_ids == ("n_0000", first)
    assert observed[0][1].entries == (
        ("n_0000", record.nodes["n_0000"].state["first"]),
    )
    assert observed[0][1].bootstrap == "recorded"
    assert observed[1][1].entries == (
        (first, record.nodes[first].state["second"]),
    )


@pytest.mark.anyio
async def test_v2_edit_validates_attachments_before_rewinding():
    controller, chat, adapter, store, _first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    before = recorder.record.model_dump()  # type: ignore[union-attr]

    with pytest.raises(ValueError, match="unsupported MIME type"):
        await controller.handle_edit(
            1,
            "edited",
            [
                {
                    "mime": "application/x-executable",
                    "data_url": "data:application/x-executable;base64,AAAA",
                    "name": "bad.exe",
                    "size": 3,
                }
            ],
            request_id="request",
        )

    assert recorder.record.model_dump() == before  # type: ignore[union-attr]
    assert adapter.turns == [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "second"},
    ]
    assert store.put_calls == []
    assert chat.actions == []
    assert recorder.record.nodes[target].input.content == "second"  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_v2_edit_resubmit_forwards_validated_attachment_copy():
    controller, chat, _adapter, _store, _first, target = (
        _make_v2_resubmit_controller()
    )
    attachment = {
        "mime": "image/png",
        "data_url": "data:image/png;base64,AAAA",
        "name": "replacement.png",
        "size": 3,
    }

    await controller.handle_edit(
        1, "edited", [attachment], request_id="request"
    )

    assert chat.actions[-1] == {
        "type": "history_edit_projection",
        "requestId": "request",
        "index": 1,
        "content": "edited",
        "attachments": [attachment],
    }
    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.record is not None
    target_input = recorder.record.nodes[target].input
    assert target_input is not None
    assert target_input.content == "second"
    attachment["name"] = "mutated.png"
    assert chat.actions[-1]["attachments"][0]["name"] == "replacement.png"


@pytest.mark.anyio
async def test_v2_edit_nonleaf_rewinds_to_root_and_preserves_old_branch() -> None:
    controller, chat, adapter, store, first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    old_first = record.nodes[first].input.model_copy(deep=True)  # type: ignore[union-attr]
    old_target = record.nodes[target].input.model_copy(deep=True)  # type: ignore[union-attr]

    await controller.handle_edit(0, "first replacement", request_id="request")

    assert record.active_leaf == "n_0000"
    assert adapter.turns == [{"role": "system", "content": "bootstrap"}]
    assert chat.actions[-1] == {
        "type": "history_edit_projection",
        "requestId": "request",
        "index": 0,
        "content": "first replacement",
        "attachments": [],
    }
    assert len(store.put_calls) == 1
    assert record.nodes[first].input == old_first
    assert record.nodes[target].input == old_target


@pytest.mark.anyio
async def test_v2_edit_projection_delivery_failure_clears_to_fresh_draft() -> None:
    controller, chat, adapter, _store, _first, _target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None

    async def fail_projection(action: dict[str, Any]) -> None:
        if action["type"] == "history_edit_projection":
            raise RuntimeError("projection unavailable")

    chat._send_action = fail_projection  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="projection unavailable"):
        await controller.handle_edit(1, "edited", request_id="request")

    assert recorder.record is None
    assert controller._active_id_now() is None
    assert controller.record is None
    assert adapter.turns == []
    assert chat.clear_messages_calls == 1


@pytest.mark.anyio
async def test_v2_resubmit_store_failure_clears_to_fresh_draft() -> None:
    controller, chat, adapter, store, _first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    live_turns = list(adapter.turns)
    chat.messages = [
        _stored_message("user", "first"),
        _stored_message("user", "second"),
    ]
    expected = RuntimeError("resubmit persistence failed")
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]
    cleanup_entry: list[tuple[Any, ...]] = []
    original_clear_failed_restore = controller._clear_failed_restore

    async def capture_cleanup_entry() -> None:
        cleanup_entry.append(
            (
                recorder.record,
                controller.record,
                controller._active_id_now(),
                record.active_leaf,
                list(chat.messages),
                list(adapter.turns),
            )
        )
        await original_clear_failed_restore()

    controller._clear_failed_restore = capture_cleanup_entry  # type: ignore[method-assign]
    put_attempts: list[ConversationRecordV2] = []

    async def fail_put(
        _partition: ConversationPartition, failed_record: ConversationRecordV2
    ) -> None:
        put_attempts.append(failed_record)
        raise expected

    store.put = fail_put  # type: ignore[method-assign]

    with pytest.raises(RuntimeError) as raised:
        await controller.resubmit(
            target, kind="retry", request_id="request", message_index=1
        )

    assert raised.value is expected
    assert put_attempts == [record]
    assert cleanup_entry == [
        (
            record,
            None,
            record.id,
            _first,
            [
                _stored_message("user", "first"),
                _stored_message("user", "second"),
            ],
            live_turns,
        )
    ]
    assert recorder.record is None
    assert controller.record is None
    assert controller._active_id_now() is None
    assert recorder._turn_baseline == []
    assert adapter.turns == []
    assert chat.clear_messages_calls == 1
    assert chat.messages == []
    assert chat.set_greeting_calls == [None]
    assert chat.actions == [
        {
            "type": "history_update",
            "enabled": True,
            "conversations": [],
            "active_id": None,
            "transition_protocol": "completion-v2",
        }
    ]
    notifier.assert_awaited_once_with(recovery_incomplete=False)


@pytest.mark.anyio
async def test_v2_resubmit_rejects_inputless_node_without_mutation():
    controller, chat, adapter, store, _first, _target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    before = recorder.record.model_dump()  # type: ignore[union-attr]

    with pytest.raises(ValueError, match="has no user input"):
        await controller.resubmit(
            "n_0000", kind="retry", request_id="request", message_index=0
        )

    assert recorder.record.model_dump() == before  # type: ignore[union-attr]
    assert adapter.turns == [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "second"},
    ]
    assert store.put_calls == []
    assert chat.actions == []


@pytest.mark.anyio
async def test_v2_edit_retry_and_regenerate_use_resubmit():
    controller, _chat, _adapter, _store, _first, target = (
        _make_v2_resubmit_controller()
    )
    resubmit = AsyncMock()
    controller.resubmit = resubmit  # type: ignore[method-assign]

    await controller.handle_edit(1, "edited", request_id="edit")
    await controller.retry(target, request_id="retry", message_index=1)
    await controller.regenerate(target, request_id="regenerate", message_index=1)

    edited_input = resubmit.await_args_list[0].args[1]
    assert isinstance(edited_input, StoredMessage)
    assert edited_input.content == "edited"
    assert resubmit.await_args_list == [
        call(
            target,
            edited_input,
            kind="edit",
            request_id="edit",
            message_index=1,
        ),
        call(target, kind="retry", request_id="retry", message_index=1),
        call(
            target,
            kind="regenerate",
            request_id="regenerate",
            message_index=1,
        ),
    ]


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["pending", "error", "cancelled"])
async def test_v2_projects_retry_metadata_for_restored_interrupted_exchanges(
    status: str,
) -> None:
    controller, chat, _adapter, _store, first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.nodes[first].status = "ok"
    record.nodes[target].status = cast(Any, status)

    await controller._send_exchange_metadata()

    assert chat.actions == [
        {
            "type": "update_exchange_metadata",
            "data": {
                0: {"status": "ok", "retryable": False},
                1: {"status": status, "retryable": True},
            },
        }
    ]


@pytest.mark.anyio
async def test_v2_compatible_retry_rewinds_stored_parent_turns():
    controller, chat, adapter, _store, first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.nodes[target].status = "error"
    original = record.nodes[target].input.model_copy(deep=True)  # type: ignore[union-attr]

    await controller.handle_resubmit(1, "retry", request_id="retry")

    assert record.active_leaf == first
    assert record.nodes[target].status == "error"
    assert record.nodes[target].input == original
    assert adapter.turns == [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
    ]
    assert chat.actions[-1] == {
        "type": "history_edit_projection",
        "requestId": "retry",
        "index": 1,
        "content": "second",
        "attachments": [],
    }


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["pending", "cancelled"])
async def test_v2_retry_restores_partial_exchange_before_creating_sibling(
    status: str,
) -> None:
    adapter = _TrackingFakeAdapter()
    controller, _store = _make_controller(
        use_exchange_tree=True,
        adapter=adapter,
    )
    chat = cast(_FakeChat, controller.chat)
    recorder = controller._exchange_recorder
    assert recorder is not None

    record = new_conversation_record_v2(
        title="restored retry",
        id=f"c_restored_{status}",
        client_info={},
    )
    record.nodes["n_0000"].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[{"role": "system", "content": "parent prefix"}],
    )
    target = "n_0001"
    original_input = _stored_message("user", "retry this")
    record.open_exchange(target, original_input)
    record.nodes[target].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[
            {"role": "user", "content": "retry this"},
            {"role": "assistant", "content": "partial response"},
        ],
    )
    record.append_stream_message(
        target,
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "partial response"),
            icon=None,
        ),
    )
    if status == "cancelled":
        record.finish_exchange(target, "cancelled", None)

    recorder.record = record
    controller._active_id.set(record.id)
    chat._transcript.set_capture_callbacks(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )

    await controller.replay_exchange_record(record)

    assert [
        message["segments"][0]["content"]
        for message in chat.restored_messages
    ] == ["retry this", "partial response"]
    assert adapter.turns == [
        {"role": "system", "content": "parent prefix"},
        {"role": "user", "content": "retry this"},
        {"role": "assistant", "content": "partial response"},
    ]
    original_node_json = record.nodes[target].model_dump_json()
    parent_id = record.nodes[target].parent_id
    assert parent_id == "n_0000"

    await controller.handle_resubmit(0, "retry", request_id="retry")

    assert chat.actions[-1] == {
        "type": "history_edit_projection",
        "requestId": "retry",
        "index": 0,
        "content": "retry this",
        "attachments": [],
    }
    assert adapter.turns == [
        {"role": "system", "content": "parent prefix"},
    ]
    assert record.active_leaf == parent_id
    assert record.nodes[target].model_dump_json() == original_node_json
    assert record.nodes[target].status == status
    assert [
        message.as_stored_message().content
        for message in record.nodes[target].messages
    ] == ["partial response"]

    await chat._transcript.record_accepted_input_and_notify(original_input)

    sibling = record.active_leaf
    assert sibling is not None
    assert sibling != target
    assert record.nodes[sibling].parent_id == parent_id
    assert record.nodes[sibling].input == original_input
    assert adapter.turns == [
        {"role": "system", "content": "parent prefix"},
    ]
    assert record.nodes[target].model_dump_json() == original_node_json


@pytest.mark.anyio
async def test_v2_regenerate_uses_the_real_resubmit_primitive():
    controller, chat, adapter, _store, first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.nodes[target].status = "ok"
    original = record.nodes[target].input.model_copy(deep=True)  # type: ignore[union-attr]

    await controller.handle_resubmit(1, "regenerate", request_id="regenerate")

    assert record.active_leaf == first
    assert record.nodes[target].status == "ok"
    assert record.nodes[target].input == original
    assert adapter.turns == [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
    ]
    assert chat.actions[-1] == {
        "type": "history_edit_projection",
        "requestId": "regenerate",
        "index": 1,
        "content": "second",
        "attachments": [],
    }


@pytest.mark.anyio
async def test_v2_rejects_retry_for_a_completed_exchange_without_mutating():
    controller, chat, adapter, store, _first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.nodes[target].status = "ok"
    before = record.model_dump()

    with pytest.raises(ValueError, match="Only interrupted or failed"):
        await controller.handle_resubmit(1, "retry", request_id="retry")

    assert record.model_dump() == before
    assert adapter.turns[-1] == {"role": "user", "content": "second"}
    assert store.put_calls == []
    assert chat.actions == []


@pytest.mark.anyio
async def test_v2_recorder_snapshots_chatlas_system_prompt_at_root_close():
    adapter = _FakeAdapter(chatlas=True)
    controller, _ = _make_controller(use_exchange_tree=True, adapter=adapter)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_finished=recorder.stream_finished,
    )

    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "one")
    )

    root_state = recorder.record.nodes["n_0000"].state["shinychat:turns"]  # type: ignore[union-attr]
    assert root_state.kind == "chatlas"
    assert root_state.mode == "snapshot"
    assert root_state.data == adapter.system_turns

    new_turn = {"role": "assistant", "content": "later"}
    adapter.turns.append(new_turn)
    adapter.system_turns.append(new_turn)
    await transcript.start_stream(
        stream_id="stream",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=exchange_id,
        send=_sent,
    )
    await transcript.end_stream(
        stream_id="stream",
        status=None,
        error=None,
        send=_sent,
    )
    state = recorder.record.nodes[exchange_id].state["shinychat:turns"]  # type: ignore[union-attr]
    assert state.mode == "delta"
    assert state.data == [new_turn]


@pytest.mark.anyio
async def test_v2_recorder_captures_model_backed_generic_turns():
    class ModelTurn(BaseModel):
        role: str
        content: str

    class ModelClient:
        def __init__(self) -> None:
            self.turns = [ModelTurn(role="user", content="hello")]

        def get_turns(self) -> list[ModelTurn]:
            return list(self.turns)

        def set_turns(self, turns: list[ModelTurn]) -> None:
            self.turns = list(turns)

    client = ModelClient()
    controller, _ = _make_controller(
        use_exchange_tree=True,
        adapter=TurnsAdapter(client),  # type: ignore[arg-type]
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "one")
    )

    state = recorder.record.nodes["n_0000"].state["shinychat:turns"]  # type: ignore[union-attr]
    assert state.kind == "turns"
    assert state.data == [{"role": "user", "content": "hello"}]


@pytest.mark.anyio
async def test_v2_recorder_captures_json_only_model_turns():
    class JsonOnlyTurn:
        def model_dump(self, *, mode: str) -> dict[str, Any]:
            if mode != "json":
                raise TypeError("only JSON mode is supported")
            return {"role": "user", "content": {"text": "hello"}}

    class ModelClient:
        def get_turns(self) -> list[JsonOnlyTurn]:
            return [JsonOnlyTurn()]

        def set_turns(self, turns: list[JsonOnlyTurn]) -> None:
            pass

    controller, _ = _make_controller(
        use_exchange_tree=True,
        adapter=TurnsAdapter(ModelClient()),  # type: ignore[arg-type]
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "one")
    )

    state = recorder.record.nodes["n_0000"].state["shinychat:turns"]  # type: ignore[union-attr]
    assert state.kind == "turns"
    assert state.data == [{"role": "user", "content": {"text": "hello"}}]


@pytest.mark.anyio
async def test_v2_recorder_rejects_model_key_collision_before_file_store(
    tmp_path: Path,
):
    from shinychat._history_store import FileConversationStore

    class ModelTurn(BaseModel):
        values: dict[Any, str]

    class ModelClient:
        def __init__(self) -> None:
            self.turns = [ModelTurn(values={2: "two", "2": "string"})]

        def get_turns(self) -> list[ModelTurn]:
            return list(self.turns)

        def set_turns(self, turns: list[ModelTurn]) -> None:
            self.turns = list(turns)

    store = FileConversationStore(tmp_path)
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
        adapter=TurnsAdapter(ModelClient()),  # type: ignore[arg-type]
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    with pytest.raises(ValueError, match="Non-string mapping key"):
        await transcript.record_accepted_input_and_notify(
            _stored_message("user", "one")
        )

    assert await store.list(part()) == []


@pytest.mark.anyio
async def test_v2_recorder_rejects_nested_deque_key_before_file_store(
    tmp_path: Path,
):
    from shinychat._history_store import FileConversationStore

    class ModelTurn(BaseModel):
        values: deque[dict[Any, str]]

    class ModelClient:
        def __init__(self) -> None:
            self.turns = [ModelTurn(values=deque([{2: "two", "2": "string"}]))]

        def get_turns(self) -> list[ModelTurn]:
            return list(self.turns)

        def set_turns(self, turns: list[ModelTurn]) -> None:
            self.turns = list(turns)

    store = FileConversationStore(tmp_path)
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
        adapter=TurnsAdapter(ModelClient()),  # type: ignore[arg-type]
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    with pytest.raises(ValueError, match="Non-string mapping key"):
        await transcript.record_accepted_input_and_notify(
            _stored_message("user", "one")
        )

    assert await store.list(part()) == []


@pytest.mark.anyio
async def test_v2_recorder_rejects_chatlas_key_collision_before_file_store(
    tmp_path: Path,
):
    chatlas = pytest.importorskip("chatlas")
    from chatlas import ContentToolResult
    from shinychat._history_store import FileConversationStore

    client = chatlas.ChatOpenAI(api_key="fake")
    client.set_turns(
        [
            chatlas.Turn(
                role="user",
                contents=[
                    ContentToolResult(
                        value="done",
                        extra={"nested": {2: "two", "2": "string"}},
                    )
                ],
            )
        ]
    )
    store = FileConversationStore(tmp_path)
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
        adapter=TurnsAdapter(client),  # type: ignore[arg-type]
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    with pytest.raises(ValueError, match="Non-string mapping key"):
        await transcript.record_accepted_input_and_notify(
            _stored_message("user", "one")
        )

    assert await store.list(part()) == []


@pytest.mark.anyio
async def test_v2_recorder_captures_delta_then_snapshot_on_earlier_turn_rewrite():
    adapter = _FakeAdapter()
    controller, _ = _make_controller(use_exchange_tree=True, adapter=adapter)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_finished=recorder.stream_finished,
    )
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "one")
    )
    adapter.turns.append({"role": "user", "content": "one"})
    await transcript.start_stream(
        stream_id="first",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=exchange_id,
        send=_sent,
    )
    await transcript.end_stream(
        stream_id="first",
        status=None,
        error=None,
        send=_sent,
    )
    state = recorder.record.nodes[exchange_id].state["shinychat:turns"]  # type: ignore[union-attr]
    assert state.mode == "delta"
    assert state.data == [{"role": "user", "content": "one"}]

    adapter.turns[0]["content"] = "rewritten"
    adapter.turns.append({"role": "assistant", "content": "later"})
    await transcript.start_stream(
        stream_id="second",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=exchange_id,
        send=_sent,
    )
    await transcript.end_stream(
        stream_id="second",
        status=None,
        error=None,
        send=_sent,
    )
    state = recorder.record.nodes[exchange_id].state["shinychat:turns"]  # type: ignore[union-attr]
    assert state.mode == "snapshot"
    assert state.data == adapter.turns


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["error", "cancelled"])
async def test_v2_recorder_captures_terminal_turns_verbatim(status: str):
    adapter = _FakeAdapter()
    controller, _ = _make_controller(use_exchange_tree=True, adapter=adapter)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_finished=recorder.stream_finished,
    )
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "one")
    )
    adapter.turns.append({"role": "assistant", "content": "partial"})
    await transcript.start_stream(
        stream_id="stream",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=exchange_id,
        send=_sent,
    )
    await transcript.end_stream(
        stream_id="stream",
        status=status,  # type: ignore[arg-type]
        error="provider failure" if status == "error" else None,
        send=_sent,
    )

    state = recorder.record.nodes[exchange_id].state["shinychat:turns"]  # type: ignore[union-attr]
    assert state.mode == "delta"
    assert state.data == [{"role": "assistant", "content": "partial"}]


@pytest.mark.anyio
async def test_v2_recorder_captures_active_node_before_next_input():
    adapter = _FakeAdapter()
    controller, _ = _make_controller(use_exchange_tree=True, adapter=adapter)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    first_exchange = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "one")
    )
    adapter.turns.append({"role": "user", "content": "one"})

    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "two")
    )

    node = recorder.record.nodes[first_exchange]  # type: ignore[union-attr]
    assert node.status == "pending"
    assert node.state["shinychat:turns"].mode == "delta"
    assert node.state["shinychat:turns"].data == [
        {"role": "user", "content": "one"}
    ]


@pytest.mark.anyio
async def test_v2_recorder_keeps_terminal_turn_delta_at_node_close():
    adapter = _FakeAdapter()
    controller, _ = _make_controller(use_exchange_tree=True, adapter=adapter)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_finished=recorder.stream_finished,
    )
    first_exchange = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "one")
    )
    adapter.turns.append({"role": "assistant", "content": "answer"})
    await transcript.start_stream(
        stream_id="stream",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=first_exchange,
        send=_sent,
    )
    await transcript.end_stream(
        stream_id="stream",
        status=None,
        error=None,
        send=_sent,
    )

    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "two")
    )

    state = recorder.record.nodes[first_exchange].state["shinychat:turns"]  # type: ignore[union-attr]
    assert state.mode == "delta"
    assert state.data == [{"role": "assistant", "content": "answer"}]


@pytest.mark.anyio
async def test_v2_recorder_replaces_stream_projection_on_its_opening_exchange():
    store = InMemoryConversationStore()
    adapter = _FakeAdapter()
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
        adapter=adapter,
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
    adapter.turns.append(
        {"role": "assistant", "content": "late first response"}
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
    assert [
        message.as_stored_message().content for message in first.messages
    ] == ["partial"]
    assert first.state["shinychat:turns"].data == [
        {"role": "assistant", "content": "late first response"}
    ]
    assert record.nodes[second_exchange].status == "pending"
    assert "shinychat:turns" not in record.nodes[second_exchange].state
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
    assert record.nodes[root_id].status == "pending"
    assert record.nodes[root_id].state["shinychat:turns"].mode == "snapshot"
    await transcript.end_stream(
        stream_id="stream",
        status=None,
        error=None,
        send=_sent,
    )

    assert record.title == "New chat"
    assert record.active_leaf == exchange_id
    assert record.nodes[root_id].status == "ok"
    assert [
        message.as_stored_message().content
        for message in record.nodes[root_id].messages
    ] == ["before input"]
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
async def test_v2_recorder_creates_inputless_child_for_unowned_content() -> (
    None
):
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
    assert [
        message.as_stored_message().content for message in child.messages
    ] == ["notice"]


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
    assert stored.nodes[first_exchange].messages[
        -1
    ].as_stored_message().content == ("partial")


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
    assert [
        message.as_stored_message().content for message in node.messages
    ] == ["partial"]


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
async def test_accepted_input_persistence_failure_is_open_and_preserves_input():
    class FailingStore(InMemoryConversationStore):
        async def put(
            self, partition: ConversationPartition, record: Any
        ) -> None:
            raise RuntimeError("durability failure")

    store = FailingStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    with pytest.raises(RuntimeError, match="durability failure"):
        await transcript.record_accepted_input_and_notify(
            _stored_message("user", "accepted but not durable")
        )

    exchange_id = transcript.open_exchange_id
    assert exchange_id is not None
    assert transcript.read()[-1].message.content == "accepted but not durable"
    assert isinstance(recorder.record, ConversationRecordV2)
    assert exchange_id in recorder.record.nodes
    assert await store.list(part()) == []


@pytest.mark.anyio
async def test_terminal_state_capture_failure_propagates_without_rollback():
    class FailingStore(InMemoryConversationStore):
        fail = False

        async def put(
            self, partition: ConversationPartition, record: Any
        ) -> None:
            if self.fail:
                raise RuntimeError("durability failure")
            await super().put(partition, record)

    adapter = _FakeAdapter()
    store = FailingStore()
    controller, _ = _make_controller(
        store=store,
        use_exchange_tree=True,
        adapter=adapter,
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
        stream_id="stream",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=exchange_id,
        send=_sent,
    )
    adapter.turns.append({"role": "assistant", "content": "partial"})
    store.fail = True

    with pytest.raises(RuntimeError, match="durability failure"):
        await transcript.end_stream(
            stream_id="stream",
            status="error",
            error="provider failure",
            send=_sent,
        )

    node = recorder.record.nodes[exchange_id]  # type: ignore[union-attr]
    assert node.state["shinychat:turns"].data == [
        {"role": "assistant", "content": "partial"}
    ]
    assert node.status == "error"
    assert transcript.active_stream_id is None


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

    source_root = str((Path(__file__).resolve().parents[1] / "src").resolve())
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
                adapter=SimpleNamespace(
                    client_info=lambda: {},
                    get_turns_json=lambda **_kwargs: [],
                    is_chatlas=lambda: False,
                ),
                store=store,
            )

            def allocate_conversation_id():
                if controller.conversation_id is None:
                    from shinychat._history_types import new_conversation_id

                    controller.conversation_id = new_conversation_id()
                return controller.conversation_id

            controller.conversation_id = None
            controller._allocate_conversation_id = allocate_conversation_id
            controller._active_id_now = lambda: controller.conversation_id
            controller.on_active_id_change = None
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
    metas = await store.list(
        ConversationPartition(chat_id="kill", scope="scope")
    )
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
        node = next(
            node for node in record.nodes.values() if node.input is not None
        )
    assert node.status == expected_status
    assert [
        message.as_stored_message().content for message in node.messages
    ] == expected_content
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
async def test_v2_response_settlement_writes_through_recorder_once():
    store = _RecordingStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "one")
    )
    assert len(store.put_calls) == 1
    assert isinstance(store.put_calls[0][1], ConversationRecordV2)

    await controller.on_response()

    assert len(store.put_calls) == 2
    assert isinstance(store.put_calls[-1][1], ConversationRecordV2)
    assert all(
        isinstance(record, ConversationRecordV2)
        for _, record in store.put_calls
    )


@pytest.mark.anyio
async def test_v2_response_persistence_does_not_depend_on_bookmark_settlement() -> (
    None
):
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "durable before bookmark")
    )
    record = recorder.record
    assert record is not None

    async def fail_bookmark(_record: ConversationRecord) -> None:
        raise RuntimeError("bookmark settlement failed")

    controller.on_response_saved = fail_bookmark

    with pytest.raises(RuntimeError, match="bookmark settlement failed"):
        await controller.on_response()

    persisted = await store.get(part(), record.id)
    assert isinstance(persisted, ConversationRecordV2)
    assert persisted.response_count == 1
    assert persisted.active_leaf is not None
    active_input = persisted.nodes[persisted.active_leaf].input
    assert active_input is not None
    assert active_input.content == "durable before bookmark"


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
    rec2.updated_at = rec2.updated_at + timedelta(seconds=1)
    rec3.updated_at = rec3.updated_at + timedelta(seconds=2)
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
    rec2.updated_at = rec2.updated_at + timedelta(seconds=1)
    rec3.updated_at = rec3.updated_at + timedelta(seconds=2)
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
        def get_turns_json(
            self, *, include_system_prompt: bool = False
        ) -> list[Any]:
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
