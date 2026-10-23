# HistoryController's session-coupled behavior (switch_to, on_response, etc.)
# is covered by Playwright e2e tests (Task 13). This file tests the pure
# helpers that HistoryController delegates to.

import asyncio
import copy
import json
import os
import signal
import subprocess
import sys
import textwrap
import warnings
from collections import deque
from collections.abc import AsyncIterator
from contextlib import (
    AbstractContextManager,
    asynccontextmanager,
    nullcontext,
    suppress,
)
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, cast
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from _history_test_helpers import replay_exchange_record
from pydantic import BaseModel
from shiny import Inputs, reactive
from shiny.module import ResolvedId
from shiny.session import session_context
from shinychat import Chat, _history_plan
from shinychat._attachments import Attachment
from shinychat._chat_transcript import ChatTranscript, TranscriptEntry
from shinychat._chat_types import (
    ChatMessage,
    StoredMessage,
    StoredSegment,
    StructuredBlock,
)
from shinychat._history import (
    HistoryInputIds,
    HistoryOptions,
    do_bookmark_with_cleanup,
)
from shinychat._history_client import TurnsAdapter
from shinychat._history_controller import HistoryController
from shinychat._history_plan import (
    StatePathContext,
    canonical_turns,
    resolve_path_values,
)
from shinychat._history_store import (
    ConversationPartition,
    ConversationStore,
    FileConversationStore,
    InMemoryConversationStore,
    sanitize_scope,
)
from shinychat._history_types import (
    HISTORY_ERROR_GENERIC,
    HISTORY_ERROR_MESSAGES,
    HISTORY_ERROR_STREAM_START,
    HISTORY_ERROR_STREAM_TERMINAL,
    MAX_SCHEMA_VERSION,
    STORED_UI_VERSION,
    VALUES_STATE_KEY,
    CapturedMessage,
    ConversationNode,
    ConversationRecordV1,
    ConversationRecordV2,
    ErrorEntry,
    StateEntry,
    StoredUiMessage,
    UnsupportedSchemaVersionError,
    new_conversation_record,
    new_conversation_record_v2,
    normalize_history_error_message,
    project_history_error_message,
)
from shinychat._history_v1 import _strip_attachment_content


def msg(role: str) -> dict[str, object]:
    return {
        "role": role,
        "segments": [{"content": role, "content_type": "markdown"}],
    }


def derived(role: str, content: str) -> dict[str, object]:
    """The stored UI message a plain-text turn group derives to."""
    return {
        "role": role,
        "segments": [{"content": content, "content_type": "markdown"}],
        "version": STORED_UI_VERSION,
    }


def chatlas_tool_group() -> list[Any]:
    """A serialized chatlas tool-call exchange (request, result, final text),
    round-tripped through JSON dicts exactly as the history store persists
    them."""
    from chatlas import Turn
    from chatlas.types import (
        ContentText,
        ContentToolRequest,
        ContentToolResult,
    )
    from shinychat._chat_bookmark import serialize_chatlas_turn

    req = ContentToolRequest(
        id="x", name="get_weather", arguments={"city": "Duluth"}
    )
    res = ContentToolResult(value="Sunny", request=req)
    turns = [
        Turn(role="assistant", contents=[req]),
        Turn(role="user", contents=[res]),
        Turn(role="assistant", contents=[ContentText(text="It's sunny.")]),
    ]
    return [serialize_chatlas_turn(t) for t in turns]


def part(
    *, chat_id: str = "chat", scope: str = "test-scope"
) -> ConversationPartition:
    return ConversationPartition(chat_id=chat_id, scope=scope)


def test_strip_attachment_content_repairs_existing_stored_ui():
    attachment = {
        "mime": "image/png",
        "name": "plot.png",
        "size": 3,
        "data_url": "data:image/png;base64,QUJD",
    }
    stored = cast(
        StoredUiMessage,
        {
            "version": STORED_UI_VERSION,
            "role": "user",
            "segments": [
                {"content": "See attached", "content_type": "markdown"},
                {
                    "type": "html_block",
                    "version": 1,
                    "content": '<img src="data:image/png;base64,QUJD"/>',
                },
            ],
            "attachments": [attachment],
        },
    )

    cleaned = _strip_attachment_content(stored)

    assert cleaned["segments"] == [
        {"content": "See attached", "content_type": "markdown"}
    ]
    assert cleaned.get("attachment_content_stripped") is True


def test_strip_attachment_content_matches_unnamed_text_attachment():
    # Regression: unnamed attachments must render with a deterministic
    # filename, or the re-derived content here never matches the stored
    # segment and the auto-generated name leaks into the restored message.
    attachment = {
        "mime": "text/plain",
        "name": "",
        "size": 5,
        "data_url": "data:text/plain;base64,aGVsbG8=",
    }
    stored = cast(
        StoredUiMessage,
        {
            "version": STORED_UI_VERSION,
            "role": "user",
            "segments": [
                {"content": "See attached\n\nfile", "content_type": "markdown"}
            ],
            "attachments": [attachment],
        },
    )

    cleaned = _strip_attachment_content(stored)

    assert cleaned["segments"] == [
        {"content": "See attached", "content_type": "markdown"}
    ]
    assert cleaned.get("attachment_content_stripped") is True


def test_strip_attachment_content_keeps_empty_attachment_only_message():
    attachment = {
        "mime": "image/png",
        "name": "plot.png",
        "size": 3,
        "data_url": "data:image/png;base64,QUJD",
    }
    stored = cast(
        StoredUiMessage,
        {
            "version": STORED_UI_VERSION,
            "role": "user",
            "segments": [
                {
                    "type": "html_block",
                    "version": 1,
                    "content": '<img src="data:image/png;base64,QUJD"/>',
                }
            ],
            "attachments": [attachment],
        },
    )

    cleaned = _strip_attachment_content(stored)

    assert cleaned["segments"] == [{"content": "", "content_type": "markdown"}]
    assert cleaned.get("attachment_content_stripped") is True


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
        self.clear_messages_greetings: list[bool] = []
        self.published_inputs: list[StoredMessage] = []
        self._transcript = ChatTranscript()
        self.latest_message_stream = _InactiveMessageStream()
        self._session = None
        self._destructive_history_transaction: object | None = None

    def _messages_for_bookmark(self) -> list[Any]:
        return self.messages

    async def _send_action(self, action: Any) -> None:
        self.actions.append(action)

    async def clear_messages(self, *, greeting: bool = False) -> None:
        self.clear_messages_calls += 1
        self.clear_messages_greetings.append(greeting)
        self.messages.clear()
        # Restored messages ARE the display in production: clearing the
        # display discards them too, so multi-restore flows (switch away
        # and back) see only the latest restore, not an accumulation.
        self.restored_messages.clear()
        self.restored_icons.clear()
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
        self.stream_calls: list[
            tuple[str, tuple[Any, ...], dict[str, Any]]
        ] = []
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

    def has_system_prompt(self) -> bool:
        return False

    def get_system_prompt(self) -> str | None:
        return None

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
    ) -> ConversationRecordV1 | None:
        return None

    async def delete(
        self, partition: ConversationPartition, conv_id: str
    ) -> None:
        pass


class _FailingStore(_RecordingStore):
    async def put(self, partition: ConversationPartition, record: Any) -> None:
        raise OSError("disk full")


class _PartitionCaptureStore(ConversationStore):
    def __init__(self) -> None:
        self.put_partitions: list[ConversationPartition] = []
        self.records: dict[str, ConversationRecordV1] = {}

    async def list(self, partition: ConversationPartition) -> list[Any]:
        return []

    async def get(
        self, partition: ConversationPartition, conv_id: str
    ) -> ConversationRecordV1 | None:
        return self.records.get(conv_id)

    async def put(self, partition: ConversationPartition, record: Any) -> None:
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
    )
    controller.partition = part()
    return controller, resolved_store


@pytest.mark.anyio
async def test_v2_history_update_advertises_completion_v2() -> None:
    controller, _ = _make_controller()

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
    with pytest.raises(ValueError, match="Non-string mapping key"):
        canonical_turns([turn])


def test_v2_recorder_string_key_reordering_keeps_a_stable_prefix():
    _, baseline = canonical_turns([{"one": "one", "two": {"nested": "value"}}])
    _, current = canonical_turns(
        [
            {"two": {"nested": "value"}, "one": "one"},
            {"role": "assistant", "content": "later"},
        ]
    )

    assert current[: len(baseline)] == baseline


def test_v2_recorder_rejects_non_json_turn_values():
    with pytest.raises(TypeError):
        canonical_turns([{"value": object()}])


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
    )
    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    await replay_exchange_record(restored, stored)
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


# ---------------------------------------------------------------------------
# v2 attachment capture semantics (main #394/#401 parity, gwg3)
# ---------------------------------------------------------------------------


_MODEL_ATTACHMENT_TURN = (
    '<file-attachment name="notes.txt" type="text/plain">\n'
    "hello\n"
    "</file-attachment>"
)
# Quote-free marker: survives json.dumps escaping of the turn above.
_MODEL_ATTACHMENT_MARKER = "</file-attachment>"


def _attachment_input() -> StoredMessage:
    """A user input carrying one text attachment, as the chat displays it."""
    return StoredMessage(
        role="user",
        segments=[
            StoredSegment(content="See attached", content_type="markdown")
        ],
        attachments=[
            Attachment(
                mime="text/plain",
                name="notes.txt",
                size=5,
                data_url="data:text/plain;base64,aGVsbG8=",
            )
        ],
    )


def _attachment_dict() -> dict[str, Any]:
    return {
        "mime": "text/plain",
        "name": "notes.txt",
        "size": 5,
        "data_url": "data:text/plain;base64,aGVsbG8=",
    }


def _display_layer_json(record: ConversationRecordV2) -> str:
    """Serialize every node's input and response display content."""
    return json.dumps(
        [
            {
                "input": (
                    node.input.model_dump(mode="json")
                    if node.input is not None
                    else None
                ),
                "messages": [
                    message.as_stored_message().model_dump(mode="json")
                    for message in node.messages
                ],
            }
            for node in record.nodes.values()
        ]
    )


def _turns_layer_json(record: ConversationRecordV2) -> str:
    """Serialize every node's recorded state entries (the model layer)."""
    return json.dumps(
        {
            node_id: {
                name: entry.model_dump(mode="json")
                for name, entry in node.state.items()
            }
            for node_id, node in record.nodes.items()
        }
    )


@pytest.mark.anyio
async def test_v2_attachment_input_captures_display_and_strips_model_text(
    tmp_path: Path,
):
    """v2 input capture matches main #394/#401 (pinned, gwg3).

    Attachments stay on the captured ``ExchangeNode.input`` for display,
    while the model-facing attachment text (the ``<file-attachment>`` block
    the chatlas adapter received) never enters the stored display layer —
    it belongs only to the turns state entries the adapter restores from.
    """
    adapter = _FakeAdapter()
    adapter.turns = [
        {
            "role": "user",
            "contents": [
                {"content_type": "text", "text": "See attached"},
                {"content_type": "text", "text": _MODEL_ATTACHMENT_TURN},
            ],
        },
        {"role": "assistant", "content": "Thanks"},
    ]
    store = FileConversationStore(tmp_path)
    controller, _ = _make_controller(
        store=store,
        adapter=adapter,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None

    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
    )
    first = await transcript.record_accepted_input_and_notify(
        _attachment_input()
    )
    await transcript.append(
        TranscriptEntry(message=_stored_message("assistant", "Thanks")),
        exchange_id=first,
        send=_sent,
    )
    # A second accepted input closes the first exchange's node and captures
    # its turns state, completing the record for the assertions below.
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "next question")
    )

    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    node = record.nodes[first]
    assert node.input is not None
    # Attachments are displayed: the captured input keeps them verbatim.
    assert node.input.content == "See attached"
    assert node.input.attachments == [
        Attachment.model_validate(_attachment_dict())
    ]
    assert [
        message.as_stored_message().content for message in node.messages
    ] == ["Thanks"]
    # Model-facing attachment text is stripped from the display layer...
    assert _MODEL_ATTACHMENT_MARKER not in _display_layer_json(record)
    # ...but the model layer (turns state) still carries it for restore.
    assert _MODEL_ATTACHMENT_MARKER in _turns_layer_json(record)

    # The persisted record keeps the same split: display stripped on disk.
    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    stored_node = stored.nodes[first]
    assert stored_node.input is not None
    assert stored_node.input.content == "See attached"
    assert stored_node.input.attachments == [
        Attachment.model_validate(_attachment_dict())
    ]
    assert _MODEL_ATTACHMENT_MARKER not in _display_layer_json(stored)
    assert _MODEL_ATTACHMENT_MARKER in _turns_layer_json(stored)

    # Replay shows the attachment chips with the clean body text.
    restored, _ = _make_controller(store=store)
    await replay_exchange_record(restored, stored)
    fake_chat = cast(_FakeChat, restored.chat)
    restored_user = fake_chat.restored_messages[0]
    assert restored_user["role"] == "user"
    assert restored_user["segments"] == [
        {
            "content": "See attached",
            "content_type": "markdown",
            "html_deps": None,
        }
    ]
    assert restored_user["attachments"] == [_attachment_dict()]


# ---------------------------------------------------------------------------
# v2 structured content blocks in captured messages (main #373 parity)
# ---------------------------------------------------------------------------


def _structured_block_segments() -> list[StoredSegment | StructuredBlock]:
    """One of every ``StructuredBlock`` type, in content order."""
    return [
        StoredSegment(content="", content_type="markdown"),
        {
            "type": "tool_request",
            "version": 1,
            "request_id": "req-1",
            "tool_name": "get_weather",
            "title": "Weather",
            "icon": "cloud",
            "intent": "Look up the weather",
            "arguments": '{"city": "Paris"}',
            "grouping": "tool",
        },
        {
            "type": "tool_result",
            "version": 1,
            "request_id": "req-1",
            "tool_name": "get_weather",
            "status": "success",
            "value": "Sunny, 21C",
            "value_type": "markdown",
        },
        {
            "type": "web_search",
            "version": 1,
            "query": "weather paris",
            "id": "search-1",
        },
        {
            "type": "web_search_results",
            "version": 1,
            "sources": [
                {
                    "url": "https://example.com/paris",
                    "title": "Paris",
                    "domain": "example.com",
                }
            ],
            "search_id": "search-1",
        },
        {
            "type": "web_search_citations",
            "version": 1,
            "sources": [{"url": "https://example.com/paris"}],
        },
        {
            "type": "web_fetch",
            "version": 1,
            "url": "https://example.com/paris",
            "status": "success",
        },
        {
            "type": "html_block",
            "version": 1,
            "content": "<b>Sunny</b>",
            "html_deps": [{"name": "sunny-dep", "version": "1"}],
        },
    ]


def _expected_restored_blocks() -> list[dict[str, Any]]:
    """The wire dicts each block segment must restore as, verbatim."""
    return [
        cast(dict[str, Any], segment)
        for segment in _structured_block_segments()
        if isinstance(segment, dict)
    ]


@pytest.mark.anyio
async def test_v2_recorder_round_trips_structured_blocks_through_file_store(
    tmp_path: Path,
) -> None:
    """Every StructuredBlock type survives capture, the JSON store, and replay."""
    store = FileConversationStore(tmp_path)
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    assert recorder is not None

    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
    )
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "search weather in paris")
    )
    await transcript.append(
        TranscriptEntry(
            message=StoredMessage(
                role="assistant",
                segments=_structured_block_segments(),
            ),
            icon="<i>bot</i>",
        ),
        exchange_id=exchange_id,
        send=_sent,
    )

    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    node = record.nodes[exchange_id]
    assert node.status == "ok"
    assert len(node.messages) == 1
    captured_blocks = [
        segment
        for segment in node.messages[0].segments
        if isinstance(segment, dict)
    ]
    assert captured_blocks == _expected_restored_blocks()

    # Persist and re-read through the file store's JSON round trip.
    await controller.on_response()
    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    stored_blocks = [
        segment
        for segment in stored.nodes[exchange_id].messages[0].segments
        if isinstance(segment, dict)
    ]
    assert stored_blocks == _expected_restored_blocks()

    # A fresh controller replays the stored record verbatim.
    restored, _ = _make_controller(store=store)
    await replay_exchange_record(restored, stored)
    fake_chat = cast(_FakeChat, restored.chat)
    assert [message["role"] for message in fake_chat.restored_messages] == [
        "user",
        "assistant",
    ]
    user_segments = fake_chat.restored_messages[0]["segments"]
    assert user_segments[0]["content"] == "search weather in paris"
    replayed_blocks = [
        segment
        for segment in fake_chat.restored_messages[1]["segments"]
        if segment.get("type") is not None
    ]
    assert replayed_blocks == _expected_restored_blocks()
    assert fake_chat.restored_icons == [None, "<i>bot</i>"]


@pytest.mark.anyio
async def test_v2_recorder_persists_structured_blocks_from_streams(
    tmp_path: Path,
) -> None:
    """Streamed block_insert projections are captured and replayed, not dropped."""
    store = FileConversationStore(tmp_path)
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    assert recorder is not None

    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "weather?")
    )
    request_block: StructuredBlock = cast(
        StructuredBlock,
        {
            "type": "tool_request",
            "version": 1,
            "request_id": "req-1",
            "tool_name": "get_weather",
        },
    )
    result_block: StructuredBlock = cast(
        StructuredBlock,
        {
            "type": "tool_result",
            "version": 1,
            "request_id": "req-1",
            "tool_name": "get_weather",
            "status": "success",
            "value": "Sunny",
            "value_type": "markdown",
        },
    )

    def _stream_message(*blocks: StructuredBlock) -> StoredMessage:
        return StoredMessage(
            role="assistant",
            segments=[
                StoredSegment(content="", content_type="markdown"),
                *blocks,
            ],
        )

    await transcript.start_stream(
        stream_id="stream",
        entry=TranscriptEntry(message=_stream_message(request_block)),
        owner_task=None,
        exchange_id=exchange_id,
        send=_sent,
    )
    await transcript.transition_stream(
        stream_id="stream",
        source_segments=[],
        message=_stream_message(request_block, result_block),
        operation="replace",
        send=_sent,
    )
    await transcript.end_stream(
        stream_id="stream",
        status=None,
        error=None,
        send=_sent,
    )

    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    node = record.nodes[exchange_id]
    assert node.status == "ok"
    assert len(node.messages) == 1
    streamed_blocks = [
        segment
        for segment in node.messages[0].segments
        if isinstance(segment, dict)
    ]
    assert streamed_blocks == [request_block, result_block]

    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    restored, _ = _make_controller(store=store)
    await replay_exchange_record(restored, stored)
    fake_chat = cast(_FakeChat, restored.chat)
    replayed_blocks = [
        segment
        for segment in fake_chat.restored_messages[-1]["segments"]
        if segment.get("type") is not None
    ]
    assert replayed_blocks == [request_block, result_block]


@pytest.mark.anyio
async def test_restore_bookmark_message_warns_on_unknown_block_type() -> None:
    """An unreplayable block degrades with a warning, never silently.

    Messages with block types this version does not know (e.g. written by a
    newer shinychat) are skipped loudly; the restore loop continues with the
    remaining messages.
    """
    from shiny.express._stub_session import ExpressStubSession

    with session_context(ExpressStubSession()):
        chat = Chat(id="chat_unknown_block")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append({"action": action, "deps": deps})

        chat._send_action = _capture  # type: ignore[method-assign]

        unknown = {
            "role": "assistant",
            "segments": [
                {"content": "", "content_type": "markdown"},
                {"type": "future_block", "version": 1},
            ],
        }
        with pytest.warns(
            UserWarning,
            match="Skipping malformed bookmarked chat message",
        ):
            await chat._restore_bookmark_message(unknown)
        assert sent == []
        assert list(chat._transcript.read()) == []

        # A known-block message in the same restore loop still replays, with
        # its blocks inline in the wire segments and html_deps passed to the
        # transport.
        await chat._restore_bookmark_message(
            {
                "role": "assistant",
                "segments": [
                    {
                        "content": "",
                        "content_type": "markdown",
                        "html_deps": [{"name": "seg-dep"}],
                    },
                    *(
                        block
                        for block in _structured_block_segments()
                        if isinstance(block, dict)
                    ),
                ],
            },
            icon="<i>bot</i>",
        )

        message_actions = [
            item["action"]
            for item in sent
            if item["action"]["type"] == "message"
        ]
        assert len(message_actions) == 1
        wire_segments = message_actions[0]["message"]["segments"]
        assert [
            segment["type"]
            for segment in wire_segments
            if segment.get("type") is not None
        ] == [block["type"] for block in _expected_restored_blocks()]
        assert [
            segment
            for segment in wire_segments
            if segment.get("type") is not None
        ] == _expected_restored_blocks()
        assert chat._transcript.read()[0].message.blocks == (
            _expected_restored_blocks()
        )

        # The message action carries the segment's html_deps to the transport.
        message_items = [
            item for item in sent if item["action"]["type"] == "message"
        ]
        assert len(message_items) == 1
        assert {"name": "seg-dep"} in (message_items[0]["deps"] or [])


@pytest.mark.anyio
async def test_v2_active_rename_survives_later_capture_in_file_store(
    tmp_path: Path,
) -> None:
    from shinychat._history_store import FileConversationStore

    store = FileConversationStore(tmp_path)
    controller, _ = _make_controller(store=store)
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
    controller, _ = _make_controller(store=store)
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
    )
    recorder = controller._exchange_recorder
    assert recorder is not None

    def restore_callback(values: dict[str, Any]) -> None:
        # Restore installs a detached copy of the stored record, so compare
        # identity by conversation id rather than object identity.
        assert recorder.record is not None
        assert recorder.record.id == target.id
        restored_values.append(dict(values))

    controller._restore_callbacks.append(restore_callback)
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "source")
    )
    # Complete the exchange through a real stream terminal so the save
    # checkpoints below are coherent completed positions.
    await transcript.start_stream(
        stream_id="values-stream",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=exchange_id,
        send=_sent,
    )
    await transcript.end_stream(
        stream_id="values-stream",
        status=None,
        error=None,
        send=_sent,
    )
    assert recorder.record is not None
    source_id = recorder.record.id

    await controller.on_response()
    source = await store.get(part(), source_id)
    assert isinstance(source, ConversationRecordV2)
    # Per-exchange sparse recording: the root recorded the live values at
    # root close; the leaf exchange inherits them unchanged.
    assert source.nodes[source.root_id].state[VALUES_STATE_KEY].data == {
        "value": "response"
    }
    assert VALUES_STATE_KEY not in source.nodes[exchange_id].state
    assert resolve_path_values(source, exchange_id) == {"value": "response"}

    current_value = "save"
    assert await controller.save()
    source = await store.get(part(), source_id)
    assert isinstance(source, ConversationRecordV2)
    assert source.nodes[exchange_id].state[VALUES_STATE_KEY].data == {
        "value": "save"
    }

    target = new_conversation_record_v2(
        title="target",
        id="c_target",
        client_info={},
    )
    target.nodes[target.root_id].state[VALUES_STATE_KEY] = StateEntry(
        kind="values",
        version=1,
        mode="snapshot",
        data={"restored": "target"},
    )
    await store.put(part(), target)

    current_value = "switch"
    await controller.switch_to(target.id)
    source = await store.get(part(), source_id)
    assert isinstance(source, ConversationRecordV2)
    # Leaving is a model-only capture: the app-values callback does not run,
    # so the exchange keeps its last explicitly saved value.
    assert source.nodes[exchange_id].state[VALUES_STATE_KEY].data == {
        "value": "save"
    }
    assert restored_values == [{"restored": "target"}]

    current_value = "new"
    await controller.new_chat()
    stored_target = await store.get(part(), target.id)
    assert isinstance(stored_target, ConversationRecordV2)
    # Leaving a conversation (New chat) is model-only: it does not run the
    # app-values callback, so the target's stored values are unchanged.
    assert stored_target.nodes[stored_target.root_id].state[
        VALUES_STATE_KEY
    ].data == {"restored": "target"}
    # The callbacks run only at explicit/boundary saves and terminal or
    # settlement captures; leaving a conversation does not add an entry.
    # Root close, the stream terminal, response settlement, and the stream
    # boundary captures all run the callback before the explicit save.
    assert saved_values == [
        "response",
        "response",
        "response",
        "response",
        "save",
    ]


def _v2_record_contents(record: ConversationRecordV2) -> list[str]:
    """Flatten a v2 record's inputs and response messages, in node order."""
    contents: list[str] = []
    for node in record.nodes.values():
        if node.input is not None:
            contents.append(node.input.content)
        for message in node.messages:
            contents.append(message.as_stored_message().content)
    return contents


@pytest.mark.anyio
async def test_v2_new_chat_closes_old_record_and_starts_fresh():
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    assert recorder is not None
    chat = cast(_FakeChat, controller.chat)
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
    )

    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "first question")
    )
    assert await transcript.append(
        TranscriptEntry(message=_stored_message("assistant", "first answer")),
        exchange_id=None,
        send=_sent,
    )
    await controller.on_response()
    assert recorder.record is not None
    closed_id = recorder.record.id

    await controller.new_chat()

    # The closed record is persisted and listed; nothing stays active.
    assert [meta.id for meta in await store.list(part())] == [closed_id]
    stored_closed = await store.get(part(), closed_id)
    assert isinstance(stored_closed, ConversationRecordV2)
    assert _v2_record_contents(stored_closed) == [
        "first question",
        "first answer",
    ]
    # The root always records its values ({} without `on_save`
    # callbacks); descendants inherit and record nothing.
    assert (
        stored_closed.nodes[stored_closed.root_id].state[VALUES_STATE_KEY].data
        == {}
    )
    assert all(
        VALUES_STATE_KEY not in node.state
        for nid, node in stored_closed.nodes.items()
        if nid != stored_closed.root_id
    )
    # The in-memory store aliases the record it was handed, so snapshot
    # the closed record before the fresh conversation's activity.
    closed_snapshot = stored_closed.model_dump(mode="json")
    assert recorder.record is None
    assert controller._active_id_now() is None
    assert any(
        action.get("type") == "history_update"
        and action.get("active_id") is None
        and [conv["id"] for conv in action["conversations"]] == [closed_id]
        for action in chat.actions
    )

    # A subsequent submission starts a fresh record with a new identity that
    # carries no content from the closed conversation.
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "second question")
    )
    assert await transcript.append(
        TranscriptEntry(message=_stored_message("assistant", "second answer")),
        exchange_id=None,
        send=_sent,
    )
    await controller.on_response()
    fresh = recorder.record
    assert fresh is not None
    assert fresh.id != closed_id
    assert _v2_record_contents(fresh) == ["second question", "second answer"]
    closed_after = await store.get(part(), closed_id)
    assert isinstance(closed_after, ConversationRecordV2)
    # The fresh conversation's activity left the closed record -- root
    # values entry included -- byte-identical.
    assert closed_after.model_dump(mode="json") == closed_snapshot
    assert _v2_record_contents(closed_after) == [
        "first question",
        "first answer",
    ]


@pytest.mark.anyio
async def test_v2_new_chat_greeting_resolves_and_is_not_captured():
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    assert recorder is not None
    chat = cast(_FakeChat, controller.chat)

    settled: list[bool] = []

    async def on_settled(restored: bool) -> None:
        settled.append(restored)
        # Mirror ChatHistory.setup_greeting wiring: resolve the configured
        # greeting once the fresh conversation settles.
        await chat.set_greeting("## Hello")

    controller.on_settled = on_settled
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
    )

    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "first question")
    )
    assert await transcript.append(
        TranscriptEntry(message=_stored_message("assistant", "first answer")),
        exchange_id=None,
        send=_sent,
    )
    await controller.on_response()
    assert recorder.record is not None
    closed_id = recorder.record.id

    await controller.new_chat(greeting=True)

    # The greeting flag reaches clear_messages and the configured greeting is
    # resolved again for the fresh conversation...
    assert chat.clear_messages_calls == 1
    assert chat.clear_messages_greetings == [True]
    assert chat.set_greeting_calls == ["## Hello"]
    assert settled == [False]

    # ...but the greeting never enters the record: the stored closed record
    # holds exactly its own exchange, and the fresh record does too.
    stored_closed = await store.get(part(), closed_id)
    assert isinstance(stored_closed, ConversationRecordV2)
    assert _v2_record_contents(stored_closed) == [
        "first question",
        "first answer",
    ]

    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "second question")
    )
    assert await transcript.append(
        TranscriptEntry(message=_stored_message("assistant", "second answer")),
        exchange_id=None,
        send=_sent,
    )
    await controller.on_response()
    fresh = recorder.record
    assert fresh is not None
    assert _v2_record_contents(fresh) == ["second question", "second answer"]


@pytest.mark.anyio
async def test_v2_initial_programmatic_message_persists_and_publishes_metadata():
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store)
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
async def test_v2_initial_programmatic_stream_persists_only_at_terminal():
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store)
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

    # Stream start creates the live record and notifies the client, but
    # writes nothing to the store: no pending root is saved before terminal.
    assert recorder.record is not None
    conv_id = recorder.record.id
    assert await store.get(part(), conv_id) is None
    controller.send_history_update.assert_awaited_once()

    assert await transcript.transition_stream(
        stream_id="stream",
        source_segments=[],
        message=_stored_message("assistant", "partial"),
        operation="append",
        send=_sent,
    )
    # Chunks mutate only the live record; the store is still untouched.
    assert await store.get(part(), conv_id) is None
    assert [
        message.as_stored_message().content
        for node in recorder.record.nodes.values()
        for message in node.messages
    ] == ["partial"]
    controller.send_history_update.assert_awaited_once()

    assert await transcript.end_stream(
        stream_id="stream",
        status=None,
        error=None,
        send=_sent,
    )
    stored = await store.get(part(), conv_id)
    assert isinstance(stored, ConversationRecordV2)
    assert [
        message.as_stored_message().content
        for node in stored.nodes.values()
        for message in node.messages
    ] == ["partial"]
    controller.send_history_update.assert_awaited_once()


@pytest.mark.anyio
async def test_v2_stream_chunks_are_durable_only_after_terminal(
    tmp_path: Path,
) -> None:
    from shinychat._history_store import FileConversationStore

    store = FileConversationStore(tmp_path)
    controller, _ = _make_controller(store=store)
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
    conv_id = recorder.record.id  # type: ignore[union-attr]
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
    await transcript.transition_stream(
        stream_id="stream",
        source_segments=[],
        message=_stored_message("assistant", " gated"),
        operation="append",
        send=_sent,
    )

    # Stream start and chunks leave the saved record at its accepted-input
    # checkpoint: the streamed text lives only in the live record.
    stored = await store.get(part(), conv_id)
    assert isinstance(stored, ConversationRecordV2)
    assert stored.nodes[exchange_id].messages == []
    assert stored.nodes[exchange_id].status == "pending"
    assert [
        message.as_stored_message().content
        for message in recorder.record.nodes[exchange_id].messages  # type: ignore[union-attr]
    ] == ["partial gated"]
    controller.send_history_update.assert_not_awaited()

    await transcript.end_stream(
        stream_id="stream",
        status=None,
        error=None,
        send=_sent,
    )
    # The terminal is the first durable write of the streamed content.
    stored = await store.get(part(), conv_id)
    assert isinstance(stored, ConversationRecordV2)
    assert [
        message.as_stored_message().content
        for message in stored.nodes[exchange_id].messages
    ] == ["partial gated"]
    assert stored.nodes[exchange_id].status == "ok"
    controller.send_history_update.assert_not_awaited()

    await controller.on_response()
    controller.send_history_update.assert_awaited_once()


@pytest.mark.anyio
async def test_v2_restore_marks_exact_record_published_after_callback() -> None:
    controller, _ = _make_controller()
    recorder = controller._exchange_recorder
    assert recorder is not None
    target = _restore_target()
    published: list[str | None] = []

    async def active_id_callback(record_id: str | None) -> None:
        # Restore installs a detached copy: match the active record by id.
        assert recorder.record is not None
        assert recorder.record.id == target.id
        assert recorder._active_id_published_for is None
        published.append(record_id)

    controller._active_id.set("c_previous")
    controller.on_active_id_change = active_id_callback

    await replay_exchange_record(controller, target)

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
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "question")
    )
    # Complete the source exchange through a real stream terminal: leaving a
    # pending exchange is not a coherent checkpoint and writes nothing, so the
    # held put below must come from a completed source.
    await transcript.start_stream(
        stream_id="source-stream",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=exchange_id,
        send=_sent,
    )
    await transcript.end_stream(
        stream_id="source-stream",
        status=None,
        error=None,
        send=_sent,
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
    # Bounded waits: a regression must fail here, never hang the suite.
    await asyncio.wait_for(store.entered.wait(), 2)
    rename = asyncio.create_task(controller.rename(source.id, "Renamed source"))
    await asyncio.sleep(0)
    assert not rename.done()

    store.release.set()
    await asyncio.wait_for(switch, 2)
    await asyncio.wait_for(rename, 2)

    stored_source = await store.get(part(), source.id)
    stored_target = await store.get(part(), target.id)
    assert isinstance(stored_source, ConversationRecordV2)
    assert isinstance(stored_target, ConversationRecordV2)
    assert stored_source.title == "Renamed source"
    assert stored_target.title == "target"
    # Restore installs a detached copy, so the active record matches by id.
    assert recorder.record is not None
    assert recorder.record.id == target.id
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
    controller, _ = _make_controller(store=store)
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
    # The coherent leaf is terminal; the pending ancestors stay pending so
    # the restore path still covers unfinished ancestors.
    record.finish_exchange(leaf, "ok", None)

    await replay_exchange_record(controller, record)

    expected = [
        {"role": "assistant", "content": "replacement"},
        {"role": "user", "content": "after snapshot"},
    ]
    assert adapter.set_calls == [expected]
    assert adapter.turns == expected
    assert recorder.record is record

    adapter.turns.append({"role": "assistant", "content": "next delta"})
    await recorder.accepted_input("n_0004", _stored_message("user", "next"))
    captured = record.nodes[leaf].state["shinychat:turns"]
    assert captured.mode == "snapshot"
    assert captured.data == adapter.turns


@pytest.mark.anyio
async def test_v2_restore_waits_for_admission_and_recorder_lock():
    """A restore never mutates the live turns before admission is granted
    and the recorder lock is held, even though preflight materialized the
    turns up front."""

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
    controller, _ = _make_controller(
        adapter=adapter,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    observed_lock = _ObservedRestoreLock()
    recorder.lock = observed_lock  # type: ignore[assignment]
    record = new_conversation_record_v2(
        title="restore",
        id="c_admission",
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
    await recorder.lock.acquire()
    try:
        restore_task = asyncio.create_task(
            replay_exchange_record(controller, record)
        )
        await entered_admission.wait()
        assert adapter.set_calls == []

        release_admission.set()
        await observed_lock.restore_attempted.wait()
        assert adapter.set_calls == []

        observed_lock.release()
        await restore_task
    finally:
        if observed_lock.locked():
            observed_lock.release()

    assert observed_lock.restore_acquired.is_set()
    assert adapter.set_calls == [
        [{"role": "system", "content": "recorded root"}]
    ]


@pytest.mark.anyio
async def test_v2_switch_uses_restore_transaction_and_controller_active_id():
    adapter = _TrackingFakeAdapter()
    store = InMemoryConversationStore()
    controller, _ = _make_controller(
        store=store,
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
    target.finish_exchange("n_0001", "ok", None)
    await store.put(part(), target)
    recorder.record = existing
    controller._active_id.set(existing.id)

    await controller.switch_to(target.id)

    fake_chat = cast(_FakeChat, controller.chat)
    # Restore installs a detached copy: match the active record by id.
    assert recorder.record is not None
    assert recorder.record.id == target.id
    assert [
        message["segments"][0]["content"]
        for message in fake_chat.restored_messages
    ] == ["restore me"]
    assert adapter.set_calls == [[{"role": "system", "content": "restored"}]]
    assert fake_chat.actions[-1]["active_id"] == "c_target"


# --- v2 bookmark-mode switch navigation (mfb3 / D5) ---------------------------


class _RunningMessageStream:
    def status(self) -> str:
        return "running"


def _v2_switch_target(state_id: str | None) -> ConversationRecordV2:
    """A minimal switchable v2 target with an optional bookmark state id."""
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
    target.bookmark_state_id = state_id
    return target


@pytest.mark.anyio
async def test_v2_switch_fires_on_switch_restored_after_successful_restore():
    """The hook fires exactly once, with the restored record, after restore."""
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    assert recorder is not None
    existing = new_conversation_record_v2(
        title="existing",
        id="c_existing",
        client_info={},
    )
    target = _v2_switch_target("state_target")
    await store.put(part(), target)
    recorder.record = existing
    controller._active_id.set(existing.id)

    restored: list[ConversationRecordV2] = []

    async def hook(record: ConversationRecordV2) -> None:
        restored.append(record)

    controller.on_switch_restored = hook

    await controller.switch_to(target.id)

    assert [r.id for r in restored] == ["c_target"]
    assert restored[0].bookmark_state_id == "state_target"
    # The controller itself stays out of navigation policy: with the hook
    # recording instead of navigating, no history_navigate is emitted.
    assert _nav_actions(cast(_FakeChat, controller.chat)) == []


@pytest.mark.anyio
async def test_v2_switch_hook_failure_is_swallowed_with_warning():
    """A raising on_switch_restored must not fail an already-committed switch."""
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    assert recorder is not None
    existing = new_conversation_record_v2(
        title="existing",
        id="c_existing",
        client_info={},
    )
    target = _v2_switch_target("state_target")
    await store.put(part(), target)
    recorder.record = existing
    controller._active_id.set(existing.id)

    async def hook(record: ConversationRecordV2) -> None:
        raise RuntimeError("session closing")

    controller.on_switch_restored = hook

    with pytest.warns(UserWarning, match="on_switch_restored hook failed"):
        await controller.switch_to(target.id)

    # The restore committed: the active record switched to the target.
    # Restore installs a detached copy: match the active record by id.
    assert recorder.record is not None
    assert recorder.record.id == target.id
    assert controller._active_id_now() == target.id


@pytest.mark.anyio
async def test_v2_switch_without_hook_emits_no_navigate():
    """Non-bookmark modes never wire the hook: no URL update on switch."""
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    assert recorder is not None
    target = _v2_switch_target("state_target")
    await store.put(part(), target)
    recorder.record = new_conversation_record_v2(
        title="existing",
        id="c_existing",
        client_info={},
    )
    controller._active_id.set("c_existing")

    await controller.switch_to(target.id)

    assert _nav_actions(cast(_FakeChat, controller.chat)) == []
    # Restore installs a detached copy: match the active record by id.
    assert recorder.record is not None
    assert recorder.record.id == target.id


@pytest.mark.anyio
async def test_v2_switch_blocked_by_stream_fires_no_on_switch_restored():
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store)
    chat = cast(_FakeChat, controller.chat)
    chat.latest_message_stream = _RunningMessageStream()  # type: ignore[assignment]
    target = _v2_switch_target("state_target")
    await store.put(part(), target)

    restored: list[ConversationRecordV2] = []

    async def hook(record: ConversationRecordV2) -> None:
        restored.append(record)

    controller.on_switch_restored = hook

    with pytest.raises(RuntimeError, match="stream"):
        await controller.switch_to(target.id)

    assert restored == []
    assert _nav_actions(chat) == []


@pytest.mark.anyio
async def test_v2_switch_failed_preflight_fires_no_on_switch_restored():
    """A switch that fails before the in-place restore leaves the URL alone."""
    store = _UnsupportedSchemaVersionStore()
    controller, _ = _make_controller(store=store)

    restored: list[ConversationRecordV2] = []

    async def hook(record: ConversationRecordV2) -> None:
        restored.append(record)

    controller.on_switch_restored = hook

    with pytest.raises(UnsupportedSchemaVersionError):
        await controller.switch_to("c_future")

    assert restored == []
    assert _nav_actions(cast(_FakeChat, controller.chat)) == []


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
    controller, _ = _make_controller(store=store)
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

    # Leaving a pending exchange writes nothing, so the source's coherent leaf
    # is completed first; the switch's save of that checkpoint is then held.
    assert source.active_leaf is not None
    source.finish_exchange(source.active_leaf, "ok", None)
    store.block_id = source.id
    switch = asyncio.create_task(controller.switch_to(target.id))
    await asyncio.wait_for(store.source_save_entered.wait(), 2)

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
    # Restore installs a detached copy: match the active record by id.
    assert recorder.record is not None
    assert recorder.record.id == target.id
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
        provider_text, provider_contents, provider_kwargs = client.stream_calls[
            0
        ]
        assert provider_text == "source input"
        assert provider_kwargs["content"] == "all"
        assert len(provider_contents) == 1
        # Since #415, text attachments travel to the provider as native
        # document content rather than a <file-attachment> text wrapper.
        from chatlas.types import ContentDocument

        assert isinstance(provider_contents[0], ContentDocument)
        assert provider_contents[0].data == b"notes"
        assert provider_contents[0].filename == "notes.txt"
        assert provider_contents[0].mime_type == "text/plain"
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
        target.finish_exchange("n_0001", "ok", None)
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
        # Restore installs a detached copy: match the active record by id.
        assert recorder.record is not None
        assert recorder.record.id == target.id
        assert controller._active_id_now() == target.id
        assert [entry.message.content for entry in chat._transcript.read()] == [
            "target input"
        ]
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

    provider.stream_merge_chunks.side_effect = lambda _completion, chunk: chunk
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
            (message["role"], message["content"]) for message in source_display
        ] == [("user", "source"), ("assistant", "")]
        assert [turn.get("role") for turn in source_turns] == [
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

    await chat._start_message_stream("stream")
    with pytest.raises(type(original)) as raised:
        await chat._append_message_stream(stream(), "stream")

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
        assert node.error.message == HISTORY_ERROR_GENERIC
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
    controller, _ = _make_controller(store=store)
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

    # Leaving a pending exchange writes nothing: complete the source's coherent
    # leaf so the switch's save of that checkpoint is the one held.
    assert source.active_leaf is not None
    source.finish_exchange(source.active_leaf, "ok", None)
    store.block_id = source.id
    switch = asyncio.create_task(controller.switch_to(target.id))
    await asyncio.wait_for(store.source_save_entered.wait(), 2)
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
    controller, _ = _make_controller(store=store)
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
    await _finish_pending_exchange(chat._transcript, recorder, "answer")
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
        "answer",
        "accepted after error",
    ]
    assert recorder.record is source


@pytest.mark.anyio
async def test_generic_destructive_admission_does_not_block_real_chat_input(
    request: pytest.FixtureRequest,
) -> None:
    controller, _ = _make_controller()
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
    source.finish_exchange("n_0001", "ok", None)
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

    # Switching away is model-only: the app-values callback runs only on an
    # explicit save, so persist the latest values before the switch attempt.
    assert await controller.save()
    with pytest.raises(ValueError, match="Unsupported restore state entry"):
        await controller.switch_to(target.id)

    stored_source = await store.get(part(), source.id)
    assert isinstance(stored_source, ConversationRecordV2)
    leaf = stored_source.active_leaf
    assert leaf is not None
    assert resolve_path_values(stored_source, leaf) == {
        "current": "latest value"
    }
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
    controller, _ = _make_controller()
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
    record.finish_exchange("n_0001", "ok", None)
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

    await replay_exchange_record(controller, record)

    assert [name for name, _ in observed] == ["first", "second"]
    first_context = observed[0][1]
    second_context = observed[1][1]
    assert first_context.conversation_id == "c_hooks"
    assert first_context.active_leaf == "n_0001"
    assert first_context.node_ids == ("n_0000", "n_0001")
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
        await replay_exchange_record(controller, invalid)

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
        await replay_exchange_record(controller, target)

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
async def test_v2_restore_with_unavailable_model_context_becomes_read_only(
    incompatibility: str,
) -> None:
    adapter = _TrackingFakeAdapter(chatlas=incompatibility == "content")
    controller, _ = _make_controller(
        adapter=adapter,
    )
    target = _restore_target()
    exchange_id = "n_0001"
    target.nodes[exchange_id].status = "error"
    entry = target.nodes["n_0000"].state["shinychat:turns"]
    if incompatibility == "kind":
        entry.kind = "unsupported"
        cause = "kind"
    elif incompatibility == "version":
        entry.version = 2
        cause = "version"
    else:
        entry.kind = "chatlas"
        entry.data = [{"role": "not-a-chatlas-role"}]
        cause = "validation"
    target_before = target.model_copy(deep=True)
    events: list[str] = []

    async def publish() -> None:
        events.append("history_update")

    controller.send_history_update = publish  # type: ignore[method-assign]

    with pytest.warns(UserWarning, match=cause):
        await replay_exchange_record(controller, target)

    recorder = controller._exchange_recorder
    assert recorder is not None
    fake_chat = cast(_FakeChat, controller.chat)
    # Restore installs a detached copy: match the active record by id.
    assert recorder.record is not None
    assert recorder.record.id == target.id
    assert recorder.read_only
    assert controller._active_id_now() == target.id
    assert [message["role"] for message in fake_chat.restored_messages] == [
        "user",
        "assistant",
        "assistant",
    ]
    assert adapter.set_calls == [[]]
    assert adapter.turns == []
    assert target == target_before
    assert events == ["history_update"]
    expected_metadata = {
        "status": "error",
        "retryable": True,
        "error_message": HISTORY_ERROR_GENERIC,
    }
    assert {
        "type": "update_exchange_metadata",
        "data": {0: expected_metadata},
    } in fake_chat.actions

    # Read-only captures are suppressed: a node close can never replace
    # the saved model context with cleared live turns.
    adapter.turns = [{"role": "user", "content": "continued"}]
    if incompatibility == "content":
        adapter.system_turns = list(adapter.turns)
    await recorder.capture_state_locked(exchange_id, "node_close")
    assert target == target_before


@pytest.mark.anyio
async def test_v2_read_only_restore_preserves_saved_context_on_reload(
    tmp_path: Path,
) -> None:
    store = FileConversationStore(tmp_path)
    adapter = _TrackingFakeAdapter()
    controller, _ = _make_controller(
        store=store,
        adapter=adapter,
    )
    target = _restore_target()
    target.nodes["n_0000"].state["shinychat:turns"].kind = "unsupported"
    await store.put(part(), target)

    with pytest.warns(UserWarning, match="read-only"):
        await replay_exchange_record(controller, target)

    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.read_only
    target_before = target.model_copy(deep=True)

    # A forged or late input can neither mutate nor capture into the
    # saved record, so the stored model context survives intact.
    adapter.turns = [{"role": "user", "content": "continued"}]
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "continued")
    )
    assert target == target_before

    stored = await store.get(part(), target.id)
    assert isinstance(stored, ConversationRecordV2)
    assert stored == target_before

    reloaded_adapter = _TrackingFakeAdapter()
    reloaded, _ = _make_controller(
        store=store,
        adapter=reloaded_adapter,
    )

    with pytest.warns(UserWarning, match="read-only"):
        await replay_exchange_record(reloaded, stored)

    reloaded_recorder = reloaded._exchange_recorder
    assert reloaded_recorder is not None
    assert reloaded_recorder.read_only
    assert reloaded_adapter.turns == []


@pytest.mark.anyio
@pytest.mark.parametrize("resubmit_kind", ["retry", "edit", "regenerate"])
async def test_v2_read_only_resubmit_is_rejected_before_mutation(
    tmp_path: Path, resubmit_kind: str
) -> None:
    adapter = _TrackingFakeAdapter()
    adapter.turns = [{"role": "system", "content": "live"}]
    store = FileConversationStore(tmp_path)
    controller, _ = _make_controller(
        store=store,
        adapter=adapter,
    )
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
    await store.put(part(), target)
    recorder = controller._exchange_recorder
    assert recorder is not None

    with pytest.warns(UserWarning, match="read-only"):
        await replay_exchange_record(controller, target)

    # Restore installs a detached copy: match the active record by id.
    assert recorder.record is not None
    assert recorder.record.id == target.id
    assert recorder.read_only
    assert adapter.turns == []
    record_before = target.model_dump()
    turns_before = list(adapter.turns)
    set_calls_before = list(adapter.set_calls)
    chat = cast(_FakeChat, controller.chat)
    display_before = list(chat.restored_messages)
    actions_before = list(chat.actions)
    preflight_before = chat.destructive_preflight_calls

    with pytest.raises(RuntimeError, match="read-only"):
        if resubmit_kind == "edit":
            await controller.handle_edit(0, "edited", request_id=resubmit_kind)
        else:
            await controller.handle_resubmit(
                0, resubmit_kind, request_id=resubmit_kind
            )

    assert target.model_dump() == record_before
    assert target.active_leaf == exchange_id
    assert adapter.turns == turns_before
    assert adapter.set_calls == set_calls_before
    assert chat.restored_messages == display_before
    assert chat.actions == actions_before
    assert chat.destructive_preflight_calls == preflight_before
    assert chat.published_inputs == []

    stored = await store.get(part(), target.id)
    assert isinstance(stored, ConversationRecordV2)
    assert stored.model_dump() == record_before


@pytest.mark.anyio
async def test_v2_read_only_navigation_replays_sibling_without_model_rewind() -> (
    None
):
    controller, chat, adapter, store, original, replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    # Every path's recorded model context is unavailable, so the record
    # restores read-only whichever sibling is selected.
    for node in record.nodes.values():
        node.state["shinychat:turns"].kind = "unsupported"
    record.nodes["exchange-first"].state["app:state"] = StateEntry(
        kind="test",
        version=1,
        mode="snapshot",
        data={"v": 1},
    )
    events: list[str] = []
    recorder._register_restore_hook("app:state", lambda _context: None)

    def rewind_app_state(_context: StatePathContext) -> None:
        events.append("rewind-app-state")

    recorder._register_rewind_hook("app:state", rewind_app_state)
    set_calls: list[list[Any]] = []
    original_set_turns = adapter.set_turns_json

    def set_turns(turns: list[Any]) -> None:
        set_calls.append(list(turns))
        original_set_turns(turns)

    adapter.set_turns_json = set_turns  # type: ignore[method-assign]

    with pytest.warns(UserWarning, match="read-only"):
        await replay_exchange_record(controller, record)

    assert recorder.read_only
    assert set_calls == [[]]
    assert adapter.turns == []
    states_before = {
        node_id: {
            name: entry.model_dump() for name, entry in node.state.items()
        }
        for node_id, node in record.nodes.items()
    }

    await controller.handle_navigate(2, "prev", request_id="navigate")

    assert record.active_leaf == original
    assert [
        message["segments"][0]["content"] for message in chat.restored_messages
    ] == [
        "first",
        "custom prefix",
        "original",
        "original reply",
    ]
    # No builtin model rewind and no capture: the adapter is untouched
    # and saved node state is byte-identical; the view pointer moved.
    assert set_calls == [[]]
    assert adapter.turns == []
    assert {
        node_id: {
            name: entry.model_dump() for name, entry in node.state.items()
        }
        for node_id, node in record.nodes.items()
    } == states_before
    # App-registered rewind hooks retain their ordinary behavior.
    assert events == ["rewind-app-state"]
    # The selected leaf is persisted, sibling metadata goes out, and the
    # client is told the active record is still read-only.
    assert store.put_calls[-1][1] == record
    assert any(action["type"] == "update_siblings" for action in chat.actions)
    history_updates = [
        action for action in chat.actions if action["type"] == "history_update"
    ]
    assert history_updates[-1]["active_read_only"] is True
    # The flag sticks to the loaded conversation even though this
    # sibling's own turns would classify the same way on reopen.
    assert recorder.read_only


@pytest.mark.anyio
async def test_v2_read_only_record_suppresses_message_and_stream_captures() -> (
    None
):
    adapter = _TrackingFakeAdapter()
    controller, store = _make_controller(adapter=adapter)
    target = _restore_target()
    target.nodes["n_0000"].state["shinychat:turns"].kind = "unsupported"

    with pytest.warns(UserWarning, match="read-only"):
        await replay_exchange_record(controller, target)

    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.read_only
    before = target.model_dump()

    entry = TranscriptEntry(
        message=_stored_message("assistant", "unsolicited"), icon=None
    )
    await recorder.accepted_input("n_forged", _stored_message("user", "forged"))
    await recorder.message_committed("n_0001", entry)
    await recorder.stream_started("s1", "n_0001", entry)
    await recorder.stream_updated("s1", entry)
    await recorder.stream_finished("s1", "ok", None)
    await recorder.capture_state_locked("n_0001", "node_close")
    assert not await recorder.save_current()
    assert not await recorder.response_settled()

    assert target.model_dump() == before
    assert store.put_calls == []

    # View-pointer, rename, and delete writes stay available.
    await controller.rename(target.id, "renamed")
    assert target.title == "renamed"
    assert store.put_calls[-1][1] == target
    assert target.model_dump()["nodes"] == before["nodes"]


@pytest.mark.anyio
async def test_v2_read_only_new_chat_clears_flag_and_wire_field() -> None:
    adapter = _TrackingFakeAdapter()
    controller, _store = _make_controller(adapter=adapter)
    target = _restore_target()
    target.nodes["n_0000"].state["shinychat:turns"].kind = "unsupported"
    chat = cast(_FakeChat, controller.chat)

    with pytest.warns(UserWarning, match="read-only"):
        await replay_exchange_record(controller, target)

    history_updates = [
        action for action in chat.actions if action["type"] == "history_update"
    ]
    assert history_updates[-1]["active_read_only"] is True

    await controller.new_chat()

    recorder = controller._exchange_recorder
    assert recorder is not None
    assert not recorder.read_only
    history_updates = [
        action for action in chat.actions if action["type"] == "history_update"
    ]
    assert "active_read_only" not in history_updates[-1]


@pytest.mark.anyio
async def test_v2_switch_to_writable_conversation_clears_read_only() -> None:
    store = InMemoryConversationStore()
    adapter = _TrackingFakeAdapter()
    controller, _ = _make_controller(store=store, adapter=adapter)
    readonly_target = _restore_target(id="c_readonly")
    readonly_target.nodes["n_0000"].state[
        "shinychat:turns"
    ].kind = "unsupported"
    writable_target = _restore_target(id="c_writable")
    await store.put(part(), readonly_target)
    await store.put(part(), writable_target)

    with pytest.warns(UserWarning, match="read-only"):
        await controller.switch_to(readonly_target.id)

    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.read_only

    await controller.switch_to(writable_target.id)

    assert not recorder.read_only
    assert recorder.record == writable_target
    assert adapter.turns == [{"role": "system", "content": "restored"}]
    chat = cast(_FakeChat, controller.chat)
    history_updates = [
        action for action in chat.actions if action["type"] == "history_update"
    ]
    assert "active_read_only" not in history_updates[-1]


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
async def test_v2_resubmit_projection_failure_names_the_step():
    controller, chat, _adapter, _store, first, _target = (
        _make_v2_resubmit_controller()
    )
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]
    expected = RuntimeError("projection send failed")

    original_send = chat._send_action

    async def fail_projection_send(
        action: dict[str, Any], *args: Any, **kwargs: Any
    ) -> Any:
        if action.get("type") == "history_edit_projection":
            raise expected
        return await original_send(action, *args, **kwargs)

    chat._send_action = fail_projection_send  # type: ignore[method-assign]

    with (
        pytest.raises(RuntimeError, match="projection send failed"),
        pytest.warns(
            UserWarning,
            match=r"Chat history restore failed \(failed while sending the resubmission\)",
        ),
    ):
        await controller.resubmit(
            first,
            _stored_message("user", "first replacement"),
            kind="edit",
            request_id="edit-ancestor",
            message_index=0,
        )

    notifier.assert_awaited_once_with(
        recovery_incomplete=False,
        detail="failed while sending the resubmission",
    )


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
        (
            ["not a turn"],
            "Turn-state entries must contain a list of JSON objects",
        ),
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
    recorder.capture_state_locked = capture_state  # type: ignore[method-assign]
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

    async def publish() -> None:
        events.append("history_update")

    controller.send_history_update = publish  # type: ignore[method-assign]

    await replay_exchange_record(controller, target)

    recorder = controller._exchange_recorder
    assert recorder is not None
    chat = cast(_FakeChat, controller.chat)
    # The target snapshot supersedes the incompatible parent entry, so
    # the restored path is writable.
    assert not recorder.read_only
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
async def test_v2_read_only_restore_warning_is_provider_neutral() -> None:
    adapter = _TrackingFakeAdapter()
    controller, _ = _make_controller(adapter=adapter)
    target = _restore_target()
    target.nodes["n_0000"].state["shinychat:turns"].kind = "unsupported"
    fake_chat = cast(_FakeChat, controller.chat)
    fake_chat._session = _RealHistorySession()  # type: ignore[attr-defined]
    notification = MagicMock()

    with (
        patch("shiny.ui.notification_show", notification),
        pytest.warns(UserWarning, match="read-only") as warning_record,
    ):
        await replay_exchange_record(controller, target)

    messages = [str(warning.message) for warning in warning_record]
    assert any("recorded turn kind 'unsupported'" in m for m in messages)
    assert all("provider" not in m.lower() for m in messages)
    # The unavailable-context toast is gone: the client learns about the
    # read-only view through the history_update wire field instead.
    notification.assert_not_called()


@pytest.mark.anyio
async def test_v2_initial_bookmark_projection_failure_recovers() -> None:
    controller, _ = _make_controller()
    target = _restore_target()
    target.nodes["n_0000"].parent_id = "missing"
    fake_chat = cast(_FakeChat, controller.chat)
    released_ids: list[str | None] = []

    async def release_active_id(id: str | None) -> None:
        released_ids.append(id)

    controller.on_active_id_change = release_active_id
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    with (
        pytest.raises(ValueError, match="Dangling parent reference"),
        pytest.warns(
            UserWarning,
            match=r"Chat history restore failed \(failed while validating the saved conversation\): "
            r"ValueError\(\"Dangling parent reference at 'missing'\"\)",
        ),
    ):
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
        action
        for action in fake_chat.actions
        if action["type"] == "history_update"
    ]
    assert len(history_updates) == 1
    assert history_updates[0]["active_id"] is None
    notifier.assert_awaited_once_with(
        recovery_incomplete=False,
        detail="failed while validating the saved conversation",
    )


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
    controller, _ = _make_controller()
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

    if isinstance(failure, Exception):
        warn_ctx: AbstractContextManager[Any] = pytest.warns(
            UserWarning,
            match=r"Chat history restore failed \(failed while admitting the restored conversation\): "
            r"RuntimeError\('initial admission failed'\)",
        )
    else:
        warn_ctx = nullcontext()

    with warn_ctx, pytest.raises(type(failure)) as raised:
        await controller._restore_initial_exchange_record(target)
    assert raised.value is failure
    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.record is None
    assert controller._active_id_now() is None
    assert fake_chat.clear_messages_calls == 1
    history_updates = [
        action
        for action in fake_chat.actions
        if action["type"] == "history_update"
    ]
    assert len(history_updates) == 1
    assert history_updates[0]["active_id"] is None
    # Cancellation keeps the generic message: no detail to attribute.
    expected_detail = (
        "failed while admitting the restored conversation"
        if isinstance(failure, Exception)
        else None
    )
    notifier.assert_awaited_once_with(
        recovery_incomplete=False, detail=expected_detail
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("second admission guard failed"),
        asyncio.CancelledError("second admission guard cancelled"),
    ],
)
async def test_v2_initial_restore_second_guard_failure_recovers(
    failure: BaseException,
) -> None:
    # Admission enters the destructive-mutation guard first; when the
    # exchange-mutation (recorder lock) guard then fails on entry, the
    # admission context must still label the failure, the unwinding
    # AsyncExitStack must release the entered guard, and the recovery
    # must run.
    controller, _ = _make_controller()
    target = _restore_target()
    fake_chat = cast(_FakeChat, controller.chat)
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    # Mirrors the real Chat's `_destructive_history_transaction`: set on
    # admission, released on exit, so the test can see the guard unwind.
    transactions: list[object] = []

    @asynccontextmanager
    async def admit_destructive(*, block_input: bool = False):
        del block_input
        transaction = object()
        transactions.append(transaction)
        fake_chat._destructive_history_transaction = transaction
        try:
            yield
        finally:
            fake_chat._destructive_history_transaction = None

    fake_chat._destructive_history_mutation = admit_destructive  # type: ignore[method-assign]

    @asynccontextmanager
    async def fail_exchange_mutation():
        raise failure
        yield

    controller._exchange_mutation = (  # type: ignore[method-assign]
        fail_exchange_mutation
    )

    if isinstance(failure, Exception):
        warn_ctx: AbstractContextManager[Any] = pytest.warns(
            UserWarning,
            match=r"Chat history restore failed \(failed while admitting the restored conversation\): "
            r"RuntimeError\('second admission guard failed'\)",
        )
    else:
        warn_ctx = nullcontext()

    with warn_ctx, pytest.raises(type(failure)) as raised:
        await controller._restore_initial_exchange_record(target)
    assert raised.value is failure

    # The destructive guard was entered exactly once and released by the
    # unwinding stack.
    assert len(transactions) == 1
    assert fake_chat._destructive_history_transaction is None
    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.record is None
    assert controller._active_id_now() is None
    assert fake_chat.clear_messages_calls == 1
    history_updates = [
        action
        for action in fake_chat.actions
        if action["type"] == "history_update"
    ]
    assert len(history_updates) == 1
    assert history_updates[0]["active_id"] is None
    # The synthetic CancelledError never puts the test task into
    # cancelling state, so cleanup awaits proceed normally; cancellation
    # just keeps the generic message, as everywhere.
    expected_detail = (
        "failed while admitting the restored conversation"
        if isinstance(failure, Exception)
        else None
    )
    notifier.assert_awaited_once_with(
        recovery_incomplete=False, detail=expected_detail
    )


@pytest.mark.anyio
async def test_v2_initial_restore_body_failure_leaves_no_stale_step_label():
    # The restore body consumes its own step attribution on failure; the
    # admission label wrapping it must not be re-armed on the re-raise, or a
    # later unrelated failure would misreport it.
    controller, _ = _make_controller()
    target = _restore_target()
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]
    body_error = RuntimeError("body replay failed")

    async def fail_replay(*_args: Any, **_kwargs: Any) -> None:
        raise body_error

    controller._replay_exchange_display = fail_replay  # type: ignore[method-assign]

    with (
        pytest.raises(RuntimeError, match="body replay failed"),
        pytest.warns(
            UserWarning,
            match=r"Chat history restore failed \(failed while replaying the conversation display\): "
            r"RuntimeError\('body replay failed'\)",
        ),
    ):
        await controller._restore_initial_exchange_record(target)

    notifier.assert_awaited_once_with(
        recovery_incomplete=False,
        detail="failed while replaying the conversation display",
    )


@pytest.mark.anyio
async def test_v2_restore_hook_failure_names_entry_and_clears_to_fresh_draft():
    controller, _ = _make_controller()
    _install_live_v2_record(controller)
    target = _restore_target()
    target.nodes["n_0000"].state["test:restore"] = StateEntry(
        kind="test", version=1, mode="snapshot", data={}
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    expected = RuntimeError("injected restore hook failure")

    def fail_restore(_context: StatePathContext) -> None:
        raise expected

    recorder._register_restore_hook("test:restore", fail_restore)
    fake_chat = cast(_FakeChat, controller.chat)
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]
    released_ids: list[str | None] = []

    async def release_active_id(id: str | None) -> None:
        released_ids.append(id)

    controller.on_active_id_change = release_active_id

    with (
        pytest.raises(_history_plan.StateHookError) as raised,
        pytest.warns(
            UserWarning,
            match=r"Chat history restore failed "
            r"\(the 'test:restore' state entry failed to apply\): "
            r"StateHookError\(\"Failed to apply state entry "
            r"'test:restore': injected restore hook failure\"\)",
        ),
    ):
        await replay_exchange_record(controller, target)

    # The hook's own error stays chained; the wrapper names the entry.
    assert raised.value.entry_name == "test:restore"
    assert raised.value.__cause__ is expected
    # Fail-to-fresh-draft cleanup: the record is dropped and the UI is
    # cleared, even though the display may have been partially restored.
    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.record is None
    assert controller._active_id_now() is None
    assert released_ids == [None]
    history_updates = [
        action
        for action in fake_chat.actions
        if action["type"] == "history_update"
    ]
    assert len(history_updates) == 1
    assert history_updates[0]["active_id"] is None
    # The entry name takes precedence over any step label, and the raw
    # error text goes to developers via the warning, not the notification.
    notifier.assert_awaited_once_with(
        recovery_incomplete=False,
        detail="the 'test:restore' state entry failed to apply",
    )


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
        await replay_exchange_record(controller, target)

    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.record is None
    assert controller._active_id_now() is None
    assert adapter.turns == []
    assert await store.get(part(), target.id) is target
    notifier.assert_awaited_once()


@pytest.mark.anyio
async def test_v2_restore_cancellation_preserves_outcome_after_cleanup_failure():
    controller, _ = _make_controller()
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
        await replay_exchange_record(controller, target)

    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.record is None
    assert controller._active_id_now() is None
    # Cancellation keeps the generic message: no detail to attribute.
    notifier.assert_awaited_once_with(recovery_incomplete=True, detail=None)


@pytest.mark.anyio
async def test_v2_restore_active_id_cancellation_cleans_up_and_preserves_identity():
    adapter = _TrackingFakeAdapter()
    controller, _ = _make_controller(
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
        await replay_exchange_record(controller, target)

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
    controller, _ = _make_controller()
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
        await replay_exchange_record(controller, target)

    assert raised.value is original
    # Cancellation keeps the generic message: no detail to attribute.
    notifier.assert_awaited_once_with(recovery_incomplete=False, detail=None)


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

    with (
        pytest.raises(RuntimeError, match="original restore failure"),
        pytest.warns(
            UserWarning,
            match=r"Chat history restore failed "
            r"\(failed while replaying the conversation display\): "
            r"RuntimeError\('original restore failure'\)",
        ),
    ):
        await replay_exchange_record(controller, target)

    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.record is None
    assert controller._active_id_now() is None
    notifier.assert_awaited_once_with(
        recovery_incomplete=True,
        detail="failed while replaying the conversation display",
    )


@pytest.mark.anyio
async def test_v2_restore_cleanup_continues_after_earlier_failure():
    adapter = _TrackingFakeAdapter()
    controller, _ = _make_controller(
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

    async def notify(
        *, recovery_incomplete: bool, detail: str | None = None
    ) -> None:
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
        await replay_exchange_record(controller, target)

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
async def test_v2_restore_cleanup_prefers_failed_restore_clear_callback():
    """A restore mode whose active-id callback navigates destructively
    installs ``on_failed_restore_cleared``; failure cleanup uses it
    INSTEAD of ``on_active_id_change(None)``. Bookmark mode's active-id
    callback hard-reloads — right for an intentional New chat, wrong for
    failure recovery, where the reload would discard the recovered fresh
    draft and the failure toast."""
    adapter = _TrackingFakeAdapter()
    controller, _ = _make_controller(adapter=adapter)
    _install_live_v2_record(controller)
    target = _restore_target()
    fake_chat = cast(_FakeChat, controller.chat)
    fake_chat._restore_bookmark_message = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("original restore failure")
    )
    active_id_calls: list[str | None] = []
    cleared: list[bool] = []

    async def active_id(id: str | None) -> None:
        active_id_calls.append(id)

    async def clear() -> None:
        cleared.append(True)

    controller.on_active_id_change = active_id
    controller.on_failed_restore_cleared = clear
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="original restore failure"):
        await replay_exchange_record(controller, target)

    assert cleared == [True]
    assert active_id_calls == []
    notifier.assert_awaited_once()


@pytest.mark.anyio
async def test_v2_restore_cleanup_marks_failure_as_notified():
    """After a successful cleanup notification the failure carries the
    notified marker (consumed on read), so an outer action boundary can
    skip its duplicate raw toast. When the notification itself could not
    be sent, the failure stays unmarked so the boundary still notifies."""
    from shinychat._history_controller import _restore_failure_was_notified

    controller, _ = _make_controller()
    _install_live_v2_record(controller)
    target = _restore_target()
    fake_chat = cast(_FakeChat, controller.chat)
    original = RuntimeError("original restore failure")
    fake_chat._restore_bookmark_message = AsyncMock(  # type: ignore[method-assign]
        side_effect=original
    )
    controller._notify_restore_failure = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(RuntimeError) as raised:
        await replay_exchange_record(controller, target)

    assert raised.value is original
    # Read-once, matching the restore-step label convention.
    assert _restore_failure_was_notified(original) is True
    assert _restore_failure_was_notified(original) is False

    unnotified = RuntimeError("second restore failure")
    fake_chat._restore_bookmark_message = AsyncMock(  # type: ignore[method-assign]
        side_effect=unnotified
    )
    controller._notify_restore_failure = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("notification send failed")
    )

    with pytest.raises(RuntimeError) as raised_again:
        await replay_exchange_record(controller, target)

    assert raised_again.value is unnotified
    assert _restore_failure_was_notified(unnotified) is False


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

    controller, _ = _make_controller()
    fake_chat = cast(_FakeChat, controller.chat)
    cast(Any, fake_chat)._session = _NotificationSession()

    with patch("shiny.ui.notification_show") as notification_show:
        await controller._notify_restore_failure(
            recovery_incomplete=recovery_incomplete
        )

    notification_show.assert_called_once_with(expected_message, type="error")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("recovery_incomplete", "detail", "expected_message"),
    [
        (
            False,
            "the 'shinychat:turns' state entry failed to apply: hook blew up",
            "Could not restore conversation: the 'shinychat:turns' state "
            "entry failed to apply: hook blew up. A fresh chat is ready.",
        ),
        (
            False,
            "failed while replaying the conversation display: boom",
            "Could not restore conversation: failed while replaying the "
            "conversation display: boom. A fresh chat is ready.",
        ),
        (
            True,
            "failed while materializing the restored turns: bad turns",
            "Could not restore conversation: failed while materializing the "
            "restored turns: bad turns. Recovery was incomplete; reload "
            "before starting a new chat.",
        ),
    ],
)
async def test_notify_restore_failure_names_failing_hook_or_step(
    recovery_incomplete: bool, detail: str, expected_message: str
) -> None:
    from shiny.module import ResolvedId

    class _NotificationSession:
        ns = ResolvedId("")

    controller, _ = _make_controller()
    fake_chat = cast(_FakeChat, controller.chat)
    cast(Any, fake_chat)._session = _NotificationSession()

    with patch("shiny.ui.notification_show") as notification_show:
        await controller._notify_restore_failure(
            recovery_incomplete=recovery_incomplete, detail=detail
        )

    notification_show.assert_called_once_with(expected_message, type="error")


@pytest.mark.anyio
async def test_v2_restore_failure_allows_next_input_to_record_normally():
    store = InMemoryConversationStore()
    controller, _ = _make_controller(
        store=store,
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
        await replay_exchange_record(controller, target)

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
    controller, _ = _make_controller()
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
    await replay_exchange_record(controller, target)

    # Restore installs a detached copy: match the active record by id.
    assert recorder.record is not None
    assert recorder.record.id == target.id
    assert len(target.nodes) == 2
    await fake_chat._transcript.record_accepted_input_and_notify(
        _stored_message("user", "after restore")
    )
    assert len(target.nodes) == 3


@pytest.mark.anyio
async def test_v2_restore_success_order_and_no_failure_notification():
    adapter = _TrackingFakeAdapter()
    controller, _ = _make_controller(
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

    def install(
        record: ConversationRecordV2,
        *,
        read_only: bool = False,
        source_isolated: bool = False,
    ) -> None:
        events.append("install")
        original_install(
            record, read_only=read_only, source_isolated=source_isolated
        )

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

    await replay_exchange_record(controller, target)

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
    controller, _ = _make_controller()
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
    controller, _ = _make_controller()
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
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    persisted: list[ConversationRecordV1 | ConversationRecordV2 | None] = []

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
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    persisted: list[ConversationRecordV1 | ConversationRecordV2 | None] = []

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
            terminal = (
                record.active_leaf is not None
                and record.nodes[record.active_leaf].status != "pending"
            )
            if self.first_put and terminal:
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
    controller, _ = _make_controller(store=store)
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
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )
    fake_chat._transcript = transcript

    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "A")
    )
    first_id = controller._active_id_now()
    assert first_id is not None
    assert store.events == ["put"]

    controller.adapter.set_turns_json([{"role": "user", "content": "A"}])
    # The terminal write is the gated one: delete must wait behind it.
    terminal_write = asyncio.create_task(
        _finish_pending_exchange(transcript, recorder, "answer")
    )
    await store.started.wait()
    delete_task = asyncio.create_task(controller.delete(first_id))
    await asyncio.sleep(0)
    assert not delete_task.done()
    assert store.events == ["put"]

    store.release.set()
    await terminal_write
    await delete_task

    assert store.events == ["put", "put", "evict", "delete"]
    assert published == [first_id, None]
    assert await store.get(part(), first_id) is None
    assert recorder.record is None
    assert controller._active_id_now() is None
    assert controller.adapter.get_turns_json() == []
    assert fake_chat._transcript.read() == ()
    assert fake_chat.messages == []


@pytest.mark.anyio
async def test_v2_new_chat_waits_for_blocked_active_id_callback():
    controller, _ = _make_controller()
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
    controller, _ = _make_controller(store=store)
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
    assert await store.get(part(), second_id) == recorder.record


@pytest.mark.anyio
@pytest.mark.parametrize("callback_error", ["failure", "cancellation"])
async def test_active_delete_clears_local_state_before_callback_failure(
    callback_error: str,
):
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store)
    fake_chat = cast(_FakeChat, controller.chat)
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )
    fake_chat._transcript = transcript
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "input")
    )
    await _finish_pending_exchange(transcript, recorder)
    assert recorder.record is not None
    active_id = recorder.record.id

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
    assert controller._active_id_now() is None
    assert controller.adapter.get_turns_json() == []
    assert fake_chat.messages == []
    assert fake_chat._transcript.read() == ()
    assert fake_chat.clear_messages_calls == 1
    assert recorder.record is None


@pytest.mark.anyio
async def test_v2_new_chat_resets_recorder_and_allocates_a_new_id():
    controller, _ = _make_controller()
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
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "hello")
    )
    await _finish_pending_exchange(transcript, recorder)
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
    controller, _ = _make_controller()
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
    await recorder.capture_state_locked("n_0000", "node_close")
    assert "first" not in root.state
    assert root.state["second"].data == {"node": "n_0000"}


def _make_v2_resubmit_controller() -> tuple[
    HistoryController, _FakeChat, _FakeAdapter, _RecordingStore, str, str
]:
    controller, store = _make_controller()
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
    controller, store = _make_controller()
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
    recorder.record = record
    controller._active_id.set(record.id)
    adapter.turns = [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "replacement"},
    ]
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
    controller, store = _make_controller()
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
    assert persisted_previous.nodes["exchange-first"].selected_child == original
    assert (
        persisted_previous.nodes[original].selected_child == original_followup
    )

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
    assert controller._active_id_now() is None
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
    notifier.assert_awaited_once_with(
        recovery_incomplete=False,
        detail="failed while saving the navigation change",
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "step,fail_on",
    [
        ("replaying the conversation display", "_replay_exchange_display"),
        ("sending the navigation update", "_send_sibling_metadata"),
    ],
)
async def test_v2_navigation_update_failure_names_the_step(
    step: str, fail_on: str
) -> None:
    controller, chat, _adapter, _store, _original, _replacement = (
        _make_v2_navigation_controller()
    )
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]
    expected = RuntimeError("navigation post-persist failure")

    async def fail_step(*_args: Any, **_kwargs: Any) -> None:
        raise expected

    setattr(controller, fail_on, fail_step)

    with (
        pytest.raises(RuntimeError, match="navigation post-persist failure"),
        pytest.warns(
            UserWarning,
            match=rf"Chat history restore failed \(failed while {step}\)",
        ),
    ):
        await controller.handle_navigate(2, "prev", request_id="navigation")

    notifier.assert_awaited_once_with(
        recovery_incomplete=False,
        detail=f"failed while {step}",
    )


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
        rewind_patch: AbstractContextManager[Any] = nullcontext()
    else:
        original_rewind = _history_plan.run_plan

        # The rewind stage runs before any display replay, so there is
        # nothing to capture from the display; the assertions below pin
        # that no replay ever happened.
        async def cancel_rewind(plan: Any, **kwargs: Any) -> None:
            await original_rewind(plan, **kwargs)
            raise asyncio.CancelledError()

        rewind_patch = patch.object(_history_plan, "run_plan", cancel_rewind)

    with rewind_patch, pytest.raises(asyncio.CancelledError):
        await controller.handle_navigate(2, "prev", request_id="navigation")

    # The rewind stage now cancels before the leaf move: nothing was
    # persisted and the display was never replayed.
    if stage == "replay":
        assert store.put_calls[0][1].active_leaf == original
        assert replayed_display == [
            _stored_message("user", "first").model_dump(mode="json"),
            _stored_message("assistant", "custom prefix").model_dump(
                mode="json"
            ),
            _stored_message("user", "original").model_dump(mode="json"),
            _stored_message("assistant", "original reply").model_dump(
                mode="json"
            ),
        ]
        assert chat.clear_messages_calls == 2
        assert chat.set_greeting_calls == [None, None]
    else:
        assert store.put_calls == []
        assert replayed_display == []
        # No display replay ran, so only the fail-to-fresh-draft cleanup
        # cleared the chat.
        assert chat.clear_messages_calls == 1
        assert chat.set_greeting_calls == [None]
    assert recorder.record is None
    assert controller._active_id_now() is None
    assert adapter.turns == []
    assert chat.messages == []
    assert chat._transcript.read() == ()
    assert chat.actions == [
        {
            "type": "history_update",
            "enabled": True,
            "conversations": [],
            "active_id": None,
            "transition_protocol": "completion-v2",
        }
    ]
    # Cancellation keeps the generic message: no detail to attribute.
    notifier.assert_awaited_once_with(recovery_incomplete=False, detail=None)


@pytest.mark.anyio
async def test_v2_navigation_rewind_hook_failure_keeps_persisted_leaf() -> None:
    controller, chat, adapter, store, original, replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    seeded = record.model_copy(deep=True)
    await store.put(part(), seeded)
    error = RuntimeError("navigation rewind failed")

    async def fail_rewind(_context: StatePathContext) -> None:
        raise error

    # A custom entry on the navigation target makes the rewind plan fail
    # at a known hook; the built-in turns rewind still runs first.
    record.nodes[original].state["test:rewind"] = StateEntry(
        kind="test",
        version=1,
        mode="snapshot",
        data={},
    )
    recorder._register_rewind_hook("test:rewind", fail_rewind)
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    with (
        pytest.raises(_history_plan.StateHookError) as raised,
        pytest.warns(
            UserWarning,
            match=r"Chat history restore failed "
            r"\(the 'test:rewind' state entry failed to apply\): "
            r"StateHookError\(\"Failed to apply state entry "
            r"'test:rewind': navigation rewind failed\"\)",
        ),
    ):
        await controller.handle_navigate(2, "prev", request_id="navigation")

    # The hook's own error stays chained; the wrapper names the entry.
    assert raised.value.entry_name == "test:rewind"
    assert raised.value.__cause__ is error
    # The rewind hooks run before the leaf move is persisted: only the
    # seeded record reached the store, and it still points at the leaf
    # the user sees.
    assert len(store.put_calls) == 1
    assert store.put_calls[0][1].active_leaf == replacement
    assert record.active_leaf == replacement
    # Fail-to-fresh-draft applies: memory is cleared even though the
    # store was never moved.
    assert recorder.record is None
    assert controller._active_id_now() is None
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
    notifier.assert_awaited_once_with(
        recovery_incomplete=False,
        detail="the 'test:rewind' state entry failed to apply",
    )


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
async def test_v2_bookmark_pointer_restores_selected_sibling_and_persists() -> (
    None
):
    controller, chat, adapter, store, original, replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    assert record.active_leaf == replacement

    # The production entry for restoring a validated v2 bookmark node
    # through the normal transaction: the bookmark-boot path in _history.py
    # calls this with the saved leaf.
    await controller._restore_initial_exchange_record(record, node_id=original)

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
async def test_v2_bookmark_pointer_stale_node_fails_preflight_and_resets_to_fresh_draft() -> (
    None
):
    controller, chat, adapter, store, _original, _replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    before = record.model_dump(mode="json")
    turns_before = list(adapter.turns)
    fake_chat = cast(_FakeChat, controller.chat)
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    # A stale node fails during preflight: no restore or persistence
    # happens, and the production initial-restore entry then recovers by
    # resetting to a fresh draft.
    with (
        pytest.raises(ValueError, match="Unknown exchange id"),
        pytest.warns(
            UserWarning,
            match=r"Chat history restore failed "
            r"\(failed while validating the saved conversation\): "
            r"ValueError\(\"Unknown exchange id 'missing-node'\"\)",
        ),
    ):
        await controller._restore_initial_exchange_record(
            record, node_id="missing-node"
        )

    # The stored record itself is untouched...
    assert record.model_dump(mode="json") == before
    assert turns_before != []  # sanity: the fixture had live turns
    # ...and nothing destructive or persisted happened.
    assert fake_chat.destructive_preflight_calls == 0
    assert fake_chat.restored_messages == []
    assert store.put_calls == []
    # Recovery: the controller released the bad restore's state instead.
    assert recorder.record is None
    assert controller._active_id_now() is None
    assert fake_chat.clear_messages_calls == 1
    assert adapter.turns == []
    history_updates = [
        action
        for action in fake_chat.actions
        if action["type"] == "history_update"
    ]
    assert len(history_updates) == 1
    assert history_updates[0]["active_id"] is None
    notifier.assert_awaited_once_with(
        recovery_incomplete=False,
        detail="failed while validating the saved conversation",
    )


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
    controller, chat, adapter, store, first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    target_input = record.nodes[target].input.model_copy(deep=True)  # type: ignore[union-attr]

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
    # Leaving the target branch captures its full turn snapshot (the live
    # model context at that point), replacing the seeded delta.
    assert record.nodes[target].state["shinychat:turns"] == StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[
            {"role": "system", "content": "bootstrap"},
            {"role": "user", "content": "first"},
            {"role": "user", "content": "second"},
        ],
    )

    exchange_id = await chat._transcript.record_accepted_input_and_notify(
        _stored_message("user", "second")
    )
    assert record.nodes[exchange_id].parent_id == first
    assert record.children_of(first) == [target, exchange_id]
    assert record.nodes[target].input == target_input


def _make_v2_resubmit_real_chat(
    request: pytest.FixtureRequest, *, chat_id: str
) -> tuple[HistoryController, Chat, _FakeAdapter, _RecordingStore, str, str]:
    """The resubmit fixture with a real ``Chat`` hosting the transcript.

    The record gains assistant replies so the server transcript mirrors a
    live conversation: a retained prefix (root -> ``first``) and an
    abandoned tail (``target``) that a resubmit of ``target`` rewinds.
    """
    controller, _fake_chat, adapter, store, first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.append_message(
        first,
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "reply one"), icon="icon-one"
        ),
    )
    record.append_message(
        target,
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "reply two"), icon=None
        ),
    )
    session = _RealChatSession()
    with session_context(cast(Any, session)):
        chat = Chat(chat_id, history=False)
    request.addfinalizer(chat.destroy)
    controller.chat = chat  # type: ignore[assignment]
    return controller, chat, adapter, store, first, target


async def _seed_resubmit_transcript(
    chat: Chat, first: str, target: str
) -> None:
    """Seed a real transcript exactly as live capture would have left it.

    The retained prefix carries rich entry data (attachments, icon, a
    terminal status/error) so the regression proves truncation preserves
    it instead of reconstructing lossy entries.
    """

    async def send() -> bool:
        return True

    first_input = StoredMessage(
        role="user",
        segments=[StoredSegment(content="first", content_type="markdown")],
        attachments=[
            Attachment(
                mime="text/plain",
                name="notes.txt",
                size=5,
                data_url="data:text/plain;base64,aGVsbG8=",
            )
        ],
    )
    await chat._transcript.append(
        TranscriptEntry(message=first_input),
        exchange_id=first,
        send=send,
    )
    await chat._transcript.append(
        TranscriptEntry(
            message=_stored_message("assistant", "reply one"),
            icon="icon-one",
            status="cancelled",
            error={"message": "interrupted"},
        ),
        exchange_id=first,
        send=send,
    )
    await chat._transcript.append(
        TranscriptEntry(message=_stored_message("user", "second")),
        exchange_id=target,
        send=send,
    )
    await chat._transcript.append(
        TranscriptEntry(message=_stored_message("assistant", "reply two")),
        exchange_id=target,
        send=send,
    )


def _wire_resubmit_capture(controller: HistoryController, chat: Chat) -> None:
    recorder = controller._exchange_recorder
    assert recorder is not None
    chat._transcript.set_capture_callbacks(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )


def _spy_send_actions(chat: Chat) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []
    original = chat._send_action

    async def record_action(action: Any, *args: Any, **kwargs: Any) -> None:
        sent.append(action)
        await original(action, *args, **kwargs)

    chat._send_action = record_action  # type: ignore[method-assign]
    return sent


@pytest.mark.anyio
@pytest.mark.parametrize(
    "kind,target_status",
    [("edit", "ok"), ("retry", "error"), ("regenerate", "ok")],
)
async def test_v2_resubmit_syncs_real_server_transcript_to_parent_prefix(
    request: pytest.FixtureRequest, kind: str, target_status: Any
) -> None:
    """A resubmit rewinds the authoritative server transcript to the same
    parent prefix the record/adapter/display rewind to, so ``chat.messages()``
    and legacy flat-message bookmark serialization match the visible
    conversation instead of retaining abandoned messages."""
    controller, chat, _adapter, _store, first, target = (
        _make_v2_resubmit_real_chat(
            request, chat_id=f"resubmit_transcript_{kind}"
        )
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.nodes[target].status = target_status
    await _seed_resubmit_transcript(chat, first, target)
    _wire_resubmit_capture(controller, chat)
    sent = _spy_send_actions(chat)

    if kind == "edit":
        await controller.handle_edit(2, "second edited", request_id="req")
    else:
        await controller.handle_resubmit(2, kind, request_id="req")

    # The client projection still goes out unchanged.
    assert sent[-1] == {
        "type": "history_edit_projection",
        "requestId": "req",
        "index": 2,
        "content": "second edited" if kind == "edit" else "second",
        "attachments": [],
    }

    # The server transcript holds exactly the parent prefix, with the
    # retained entries' rich data intact.
    messages = chat.messages()
    assert [m["content"] for m in messages] == ["first", "reply one"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    prefix_attachments = messages[0].get("attachments")
    assert prefix_attachments is not None
    assert prefix_attachments[0].name == "notes.txt"
    assert messages[1].get("status") == "cancelled"
    assert messages[1].get("error") == {"message": "interrupted"}
    bookmark_dump = chat._messages_for_bookmark()
    assert [m["segments"][0]["content"] for m in bookmark_dump] == [
        "first",
        "reply one",
    ]
    assert bookmark_dump[0]["attachments"][0]["name"] == "notes.txt"

    # The replacement input then appends through the ordinary real-Chat
    # capture path, producing prefix + replacement on the server too.
    replacement = "second edited" if kind == "edit" else "second"
    await chat._record_accepted_user_input_with_capture(
        ChatMessage(content=replacement, role="user")
    )
    assert [m["content"] for m in chat.messages()] == [
        "first",
        "reply one",
        replacement,
    ]
    sibling = record.active_leaf
    assert sibling is not None
    assert sibling != target
    assert record.children_of(first) == [target, sibling]
    sibling_input = record.nodes[sibling].input
    assert sibling_input is not None
    assert sibling_input.content == replacement


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
    original_run_plan = _history_plan.run_plan

    async def blocked_run_plan(plan: Any, **kwargs: Any) -> None:
        rewind_started.set()
        await release_rewind.wait()
        await original_run_plan(plan, **kwargs)

    rewind_patch = patch.object(_history_plan, "run_plan", blocked_run_plan)
    rewind_patch.start()
    request.addfinalizer(rewind_patch.stop)
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
    # The rewind hooks run before the leaf move is persisted: while they
    # are blocked the record still points at the leaf the user sees.
    assert record.active_leaf == target
    assert record.children_of(first) == [target]

    release_rewind.set()
    await resubmit

    # Only after the rewind accepted does the leaf move to the parent.
    assert record.active_leaf == first
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
async def test_v2_edit_nonleaf_rewinds_to_root_and_preserves_old_branch() -> (
    None
):
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
async def test_v2_edit_projection_delivery_failure_clears_to_fresh_draft() -> (
    None
):
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
    chat.messages = [
        _stored_message("user", "first"),
        _stored_message("user", "second"),
    ]
    expected = RuntimeError("resubmit persistence failed")
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]
    cleanup_entry: list[tuple[Any, ...]] = []
    original_clear_failed_restore = controller._clear_failed_restore

    async def capture_cleanup_entry(
        failure: BaseException | None = None,
    ) -> None:
        cleanup_entry.append(
            (
                failure,
                recorder.record,
                controller._active_id_now(),
                record.active_leaf,
                list(chat.messages),
                list(adapter.turns),
            )
        )
        await original_clear_failed_restore(failure)

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
    assert len(put_attempts) == 1
    assert put_attempts[0].active_leaf == _first
    # The rewind hooks ran before the failed persist, so the cleanup
    # snapshot sees the rewound parent-prefix turns, not the live ones.
    rewound_turns = [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
    ]
    assert cleanup_entry == [
        (
            expected,
            record,
            record.id,
            _first,
            [
                _stored_message("user", "first"),
                _stored_message("user", "second"),
            ],
            rewound_turns,
        )
    ]
    assert recorder.record is None
    assert controller._active_id_now() is None
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
    notifier.assert_awaited_once_with(
        recovery_incomplete=False,
        detail="failed while saving the resubmission",
    )


@pytest.mark.anyio
async def test_v2_resubmit_rewind_hook_failure_keeps_persisted_leaf() -> None:
    controller, chat, adapter, store, first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    seeded = record.model_copy(deep=True)
    await store.put(part(), seeded)
    error = RuntimeError("resubmit rewind failed")

    async def fail_rewind(_context: StatePathContext) -> None:
        raise error

    # A custom entry on the rewind prefix makes the rewind plan fail at a
    # known hook; the built-in turns rewind still runs first.
    record.nodes[first].state["test:rewind"] = StateEntry(
        kind="test",
        version=1,
        mode="snapshot",
        data={},
    )
    recorder._register_rewind_hook("test:rewind", fail_rewind)
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    with (
        pytest.raises(_history_plan.StateHookError) as raised,
        pytest.warns(
            UserWarning,
            match=r"Chat history restore failed "
            r"\(the 'test:rewind' state entry failed to apply\): "
            r"StateHookError\(\"Failed to apply state entry "
            r"'test:rewind': resubmit rewind failed\"\)",
        ),
    ):
        await controller.resubmit(
            target, kind="retry", request_id="request", message_index=1
        )

    # The hook's own error stays chained; the wrapper names the entry.
    assert raised.value.entry_name == "test:rewind"
    assert raised.value.__cause__ is error
    # The rewind hooks run before the leaf move is persisted: only the
    # seeded record reached the store, and it still points at the leaf
    # the user sees.
    assert len(store.put_calls) == 1
    assert store.put_calls[0][1].active_leaf == target
    assert record.active_leaf == target
    # Fail-to-fresh-draft applies: memory is cleared even though the
    # store was never moved.
    assert recorder.record is None
    assert controller._active_id_now() is None
    assert adapter.turns == []
    assert chat.messages == []
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
    notifier.assert_awaited_once_with(
        recovery_incomplete=False,
        detail="the 'test:rewind' state entry failed to apply",
    )


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
async def test_v2_edit_uses_resubmit():
    controller, _chat, _adapter, _store, _first, target = (
        _make_v2_resubmit_controller()
    )
    resubmit = AsyncMock()
    controller.resubmit = resubmit  # type: ignore[method-assign]

    await controller.handle_edit(1, "edited", request_id="edit")

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

    expected_target = {"status": status, "retryable": True}
    if status == "error":
        expected_target["error_message"] = HISTORY_ERROR_GENERIC
    assert chat.actions == [
        {
            "type": "update_exchange_metadata",
            "data": {
                0: {"status": "ok", "retryable": False},
                1: expected_target,
            },
        }
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (HISTORY_ERROR_GENERIC, HISTORY_ERROR_GENERIC),
        (HISTORY_ERROR_STREAM_START, HISTORY_ERROR_STREAM_START),
        (HISTORY_ERROR_STREAM_TERMINAL, HISTORY_ERROR_STREAM_TERMINAL),
        ("provider timeout", HISTORY_ERROR_GENERIC),
        ("legacy \n unsafe", HISTORY_ERROR_GENERIC),
    ],
)
async def test_v2_error_catalogue_is_bounded_at_write_and_projection(
    message: str, expected: str
) -> None:
    controller, chat, _adapter, _store, first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.nodes[first].status = "ok"
    record.nodes[target].status = "error"
    record.finish_exchange(target, "error", message)

    await controller._send_exchange_metadata()

    assert record.nodes[target].error is not None
    error_entry = record.nodes[target].error
    assert error_entry is not None
    assert error_entry.message == expected
    assert chat.actions[-1]["data"][1]["error_message"] == expected


def test_v2_error_normalization_is_nfc_whitespace_safe_and_bounded() -> None:
    long_message = "e\u0301\t\r\n" + ("x" * 300)
    normalized = normalize_history_error_message(long_message)

    assert normalized.startswith("é x")
    assert len(normalized) == 256
    assert normalized.endswith("...")
    assert "\t" not in normalized
    assert "\r" not in normalized
    assert "\n" not in normalized
    assert (
        project_history_error_message("unknown legacy error")
        == HISTORY_ERROR_GENERIC
    )
    assert project_history_error_message(HISTORY_ERROR_STREAM_START) == (
        HISTORY_ERROR_STREAM_START
    )
    assert HISTORY_ERROR_MESSAGES == frozenset(
        {
            HISTORY_ERROR_GENERIC,
            HISTORY_ERROR_STREAM_START,
            HISTORY_ERROR_STREAM_TERMINAL,
        }
    )


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["pending", "cancelled"])
async def test_v2_error_detail_is_absent_for_non_error_or_inputless_nodes(
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
    record.nodes[target].error = None
    await controller._send_exchange_metadata()

    assert all(
        "error_message" not in item
        for item in chat.actions[-1]["data"].values()
    )


@pytest.mark.anyio
async def test_v2_error_detail_is_absent_for_inputless_error_node() -> None:
    controller, chat, _adapter, _store, first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.nodes[first].status = "ok"
    record.nodes[target].status = "error"
    record.nodes[target].input = None
    record.nodes[target].error = ErrorEntry(message=HISTORY_ERROR_GENERIC)

    await controller._send_exchange_metadata()

    assert all(
        "error_message" not in item
        for item in chat.actions[-1]["data"].values()
    )


@pytest.mark.anyio
async def test_v2_error_projection_does_not_mutate_failed_node_with_partial_display() -> (
    None
):
    controller, chat, _adapter, _store, first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.nodes[first].status = "ok"
    record.nodes[target].status = "error"
    record.nodes[target].error = ErrorEntry(message="unknown legacy error")
    record.nodes[target].messages.append(
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "partial response"),
            icon=None,
        )
    )
    before = record.nodes[target].model_dump_json()

    await controller._send_exchange_metadata()

    assert chat.actions[-1]["data"][1]["error_message"] == HISTORY_ERROR_GENERIC
    assert record.nodes[target].model_dump_json() == before


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
    controller, store = _make_controller(
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

    await replay_exchange_record(controller, record)
    parent_prefix = [{"role": "system", "content": "parent prefix"}]
    parent_id = record.nodes[target].parent_id
    assert parent_id == "n_0000"

    if status == "pending":
        # An unresolved restore is isolated and read-only: only the parent
        # prefix replays, and a retry of the pending exchange is rejected
        # without touching the record, the model, or the store.
        restored = recorder.record
        assert restored is not None
        assert recorder.read_only
        assert [
            message["segments"][0]["content"]
            for message in chat.restored_messages
        ] == []
        assert adapter.turns == parent_prefix
        before = restored.model_dump(mode="json")
        puts_before = len(store.put_calls)

        # The unresolved exchange is not addressable on the coherent path,
        # so the retry is rejected at message-index resolution.
        with pytest.raises(IndexError, match="out of range"):
            await controller.handle_resubmit(0, "retry", request_id="retry")

        assert restored.model_dump(mode="json") == before
        assert restored.nodes[target].status == "pending"
        assert adapter.turns == parent_prefix
        assert len(store.put_calls) == puts_before
        return

    assert [
        message["segments"][0]["content"] for message in chat.restored_messages
    ] == ["retry this", "partial response"]
    assert adapter.turns == [
        {"role": "system", "content": "parent prefix"},
        {"role": "user", "content": "retry this"},
        {"role": "assistant", "content": "partial response"},
    ]
    original_node = record.nodes[target].model_dump(
        mode="json", exclude={"state"}
    )

    await controller.handle_resubmit(0, "retry", request_id="retry")

    assert chat.actions[-1] == {
        "type": "history_edit_projection",
        "requestId": "retry",
        "index": 0,
        "content": "retry this",
        "attachments": [],
    }
    assert adapter.turns == parent_prefix
    assert record.active_leaf == parent_id
    assert (
        record.nodes[target].model_dump(mode="json", exclude={"state"})
        == original_node
    )
    assert record.nodes[target].status == status
    assert [
        message.as_stored_message().content
        for message in record.nodes[target].messages
    ] == ["partial response"]
    # Leaving the retried branch captures its full turn snapshot, replacing
    # the seeded delta.
    assert record.nodes[target].state["shinychat:turns"] == StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[
            {"role": "system", "content": "parent prefix"},
            {"role": "user", "content": "retry this"},
            {"role": "assistant", "content": "partial response"},
        ],
    )

    await chat._transcript.record_accepted_input_and_notify(original_input)

    sibling = record.active_leaf
    assert sibling is not None
    assert sibling != target
    assert record.nodes[sibling].parent_id == parent_id
    assert record.nodes[sibling].input == original_input
    assert adapter.turns == parent_prefix
    assert (
        record.nodes[target].model_dump(mode="json", exclude={"state"})
        == original_node
    )


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
async def test_v2_recorder_snapshots_chatlas_turns_at_root_close():
    adapter = _FakeAdapter(chatlas=True)
    controller, _ = _make_controller(adapter=adapter)
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
    assert root_state.data == adapter.turns

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
    assert state.mode == "snapshot"
    assert state.data == adapter.turns


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
    controller, _ = _make_controller(adapter=adapter)
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
    assert state.mode == "snapshot"
    assert state.data == adapter.turns

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
    controller, _ = _make_controller(adapter=adapter)
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
    assert state.mode == "snapshot"
    assert state.data == adapter.turns


@pytest.mark.anyio
async def test_v2_recorder_captures_active_node_before_next_input():
    adapter = _FakeAdapter()
    controller, _ = _make_controller(adapter=adapter)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    first_exchange = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "one")
    )
    adapter.turns.append({"role": "user", "content": "one"})
    validated: list[bool] = []
    adapter.get_system_prompt = lambda: validated.append(True)  # type: ignore[attr-defined,method-assign]

    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "two")
    )

    node = recorder.record.nodes[first_exchange]  # type: ignore[union-attr]
    assert node.status == "pending"
    # A pending predecessor writes no turns state; the next input still
    # runs the live client's model-state validation.
    assert "shinychat:turns" not in node.state
    assert validated


@pytest.mark.anyio
async def test_v2_recorder_keeps_terminal_turn_delta_at_node_close():
    adapter = _FakeAdapter()
    controller, _ = _make_controller(adapter=adapter)
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
    assert state.mode == "snapshot"
    assert state.data == adapter.turns


@pytest.mark.anyio
async def test_v2_recorder_replaces_stream_projection_on_its_opening_exchange():
    store = InMemoryConversationStore()
    adapter = _FakeAdapter()
    controller, _ = _make_controller(
        store=store,
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
    assert first.state["shinychat:turns"].mode == "snapshot"
    assert first.state["shinychat:turns"].data == adapter.turns
    assert record.nodes[second_exchange].status == "pending"
    assert "shinychat:turns" not in record.nodes[second_exchange].state
    assert record.active_leaf == second_exchange
    assert recorder._stream_exchanges == {}


@pytest.mark.anyio
async def test_v2_recorder_persists_pre_input_stream_on_pending_root() -> None:
    store = InMemoryConversationStore()
    controller, _ = _make_controller(
        store=store,
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
    # A pending root writes no turns state until its exchange settles.
    assert "shinychat:turns" not in record.nodes[root_id].state
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
async def test_next_input_persists_without_unsaved_streamed_tail() -> None:
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store)
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
    assert await transcript.transition_stream(
        stream_id="stream",
        source_segments=[],
        message=_stored_message("assistant", "partial"),
        operation="append",
        send=_sent,
    )

    # The first exchange is still streaming: its chunk is live-only. The next
    # input's save persists its own node and the first exchange's pending
    # shell, never the unfinished streamed tail.
    second_exchange = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "second")
    )

    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    assert stored.active_leaf == second_exchange
    assert second_exchange in stored.nodes
    assert stored.nodes[first_exchange].messages == []
    assert stored.nodes[first_exchange].status == "pending"
    assert [
        message.as_stored_message().content
        for message in record.nodes[first_exchange].messages
    ] == ["partial"]


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
        assert node.error.message == HISTORY_ERROR_GENERIC
    assert [
        message.as_stored_message().content for message in node.messages
    ] == ["partial"]


@pytest.mark.anyio
async def test_stream_recorder_failure_does_not_rollback_sent_transcript(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
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
    # Chunks never await storage: the failed background snapshot does not
    # roll back the sent transcript and does not raise at the chunk.
    await transcript.transition_stream(
        stream_id="stream",
        source_segments=[],
        message=_stored_message("assistant", "sent partial"),
        operation="append",
        send=_sent,
    )

    assert transcript.read()[-1].message.content == "sent partial"
    assert transcript.active_stream_id == "stream"

    with pytest.raises(RuntimeError, match="durability failure"):
        await recorder.stream_finished("stream", "error", "provider failed")
    assert transcript.read()[-1].message.content == "sent partial"
    store.fail = False
    await recorder.stream_finished("stream", "error", "provider failed")

    stored = await store.get(part(), recorder.record.id)  # type: ignore[union-attr]
    assert isinstance(stored, ConversationRecordV2)
    assert [
        message.as_stored_message().content
        for message in stored.nodes[exchange_id].messages
    ] == ["sent partial"]


@pytest.mark.anyio
async def test_accepted_input_persistence_failure_is_open_and_preserves_input():
    class FailingStore(InMemoryConversationStore):
        async def put(
            self, partition: ConversationPartition, record: Any
        ) -> None:
            raise RuntimeError("durability failure")

    store = FailingStore()
    controller, _ = _make_controller(store=store)
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
    assert node.state["shinychat:turns"].mode == "snapshot"
    assert node.state["shinychat:turns"].data == adapter.turns
    assert node.status == "error"
    assert transcript.active_stream_id is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("checkpoint", "expected_content", "expected_status", "expected_error"),
    [
        # Nothing is written before the input checkpoint, so a kill before
        # any terminal leaves no saved record at all.
        ("pre-input-start", None, None, None),
        ("input", [], "pending", None),
        ("start", [], "pending", None),
        # Chunks (text or tool blocks) are live-only until the terminal, so a
        # kill mid-stream leaves the accepted-input checkpoint on disk.
        ("update-one", [], "pending", None),
        ("update-tool", [], "pending", None),
        # The terminal persists the full streamed tail.
        ("ok", ["first second"], "ok", None),
        ("error", ["first second"], "error", HISTORY_ERROR_GENERIC),
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
        from shinychat._history_recorder import _ExchangeRecorder
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
            controller._save_callbacks = []

            async def send_history_update():
                return None

            controller.send_history_update = send_history_update
            recorder = _ExchangeRecorder(controller)

            # Minimal honest publish semantics for this host double: the
            # id is published iff it is still the active one. Deliberately
            # not a copy of HistoryController._publish_active_id — the
            # crash-recovery path this test pins never observed the real
            # method (the pre-Protocol fallback skipped it too).
            async def publish_active_id(record):
                return controller._active_id_now() == record.id

            controller._publish_active_id = publish_active_id
            transcript = ChatTranscript(
                on_accepted_input=recorder.accepted_input,
                on_stream_started=recorder.stream_started,
                on_stream_updated=recorder.stream_updated,
                on_stream_finished=recorder.stream_finished,
            )
            controller.chat = SimpleNamespace(_transcript=transcript)

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
            if sys.argv[2] in ("update-one", "update-tool"):
                if sys.argv[2] == "update-tool":
                    await transcript.transition_stream(
                        stream_id="stream",
                        source_segments=[],
                        message=StoredMessage(
                            role="assistant",
                            segments=[
                                {
                                    "type": "tool_request",
                                    "version": 1,
                                    "request_id": "r1",
                                    "tool_name": "get_weather",
                                }
                            ],
                        ),
                        operation="append",
                        send=sent,
                    )
                os.kill(os.getpid(), signal.SIGKILL)
            await transcript.transition_stream(
                stream_id="stream",
                source_segments=[],
                message=message("assistant", " second"),
                operation="append",
                send=sent,
            )
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
    if checkpoint == "pre-input-start":
        assert metas == []
        return
    assert len(metas) == 1
    record = await store.get(
        ConversationPartition(chat_id="kill", scope="scope"), metas[0].id
    )
    assert isinstance(record, ConversationRecordV2)
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


async def _finish_pending_exchange(
    transcript: ChatTranscript, recorder: Any, content: str = ""
) -> None:
    """Complete the active accepted-input exchange through a stream terminal.

    Writable restore, save, and delete are only coherent once the exchange
    is terminal; a bare accepted input leaves it pending (interrupted).
    """
    assert recorder.record is not None
    await transcript.start_stream(
        stream_id="finish-pending",
        entry=TranscriptEntry(message=_stored_message("assistant", content)),
        owner_task=None,
        exchange_id=recorder.record.active_leaf,
        send=_sent,
    )
    await transcript.end_stream(
        stream_id="finish-pending", status=None, error=None, send=_sent
    )


async def _sent() -> bool:
    return True


@pytest.mark.anyio
async def test_v2_response_settlement_writes_through_recorder_once():
    store = _RecordingStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )

    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "one")
    )
    # Settlement is coherent only for a completed exchange: finish it first.
    await _finish_pending_exchange(transcript, recorder, "answer")
    assert isinstance(store.put_calls[-1][1], ConversationRecordV2)
    settled_puts = len(store.put_calls)

    await controller.on_response()

    assert len(store.put_calls) == settled_puts + 1
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
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )

    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "durable before bookmark")
    )
    await _finish_pending_exchange(transcript, recorder, "answer")
    record = recorder.record
    assert record is not None

    async def fail_bookmark(
        _record: ConversationRecordV1 | ConversationRecordV2,
    ) -> None:
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
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "hello")
    )

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
    recorder = controller_a._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "hello")
    )
    assert recorder.record is not None
    record_a = recorder.record

    controller_b, _store_b = _make_controller(store=store)
    controller_b.partition = ConversationPartition(
        chat_id="chat-b", scope="browser-1"
    )

    assert await store.get(controller_a.partition, record_a.id) is not None
    assert await store.get(controller_b.partition, record_a.id) is None
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

    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store, save_callbacks=[capture])
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "hello")
    )
    await _finish_pending_exchange(transcript, recorder)
    assert recorder.record is not None
    response_count = recorder.record.response_count

    put_count = 0
    original_persist = recorder.persist_record_locked

    async def persist() -> None:
        nonlocal put_count
        await original_persist()
        put_count += 1

    recorder.persist_record_locked = persist

    assert await controller.save() is True
    assert recorder.record.response_count == response_count
    leaf = recorder.record.active_leaf
    assert leaf is not None
    assert resolve_path_values(recorder.record, leaf) == {
        "artifact": {"version": 2}
    }
    # The callback runs at every capture point: root close, the stream
    # terminal's settlement captures, and this explicit save. The save
    # itself persisted exactly once.
    assert len(saved_values) == 4
    assert put_count == 1
    assert controller._title_task is None


@pytest.mark.anyio
async def test_explicit_save_does_not_start_title_generation():
    title_calls: list[list[dict[str, Any]]] = []

    async def title_fn(turns: list[dict[str, Any]]) -> str:
        title_calls.append(turns)
        return "Generated title"

    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store)
    controller.title_enabled = True
    controller.title_fn = title_fn
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "hello")
    )
    await _finish_pending_exchange(transcript, recorder)
    assert recorder.record is not None
    assert controller._title_task is None

    assert await controller.save() is True
    assert controller._title_task is None
    assert title_calls == []


@pytest.mark.anyio
async def test_explicit_save_runs_history_lifecycle_after_persist():
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "hello")
    )
    await _finish_pending_exchange(transcript, recorder)
    assert recorder.record is not None
    events: list[str] = []

    original_persist = recorder.persist_record_locked

    async def persist() -> None:
        await original_persist()
        events.append("put")

    async def bookmark(record: ConversationRecordV2) -> None:
        events.append("bookmark")

    recorder.persist_record_locked = persist
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

    async def clear_messages(self, *, greeting: bool = False) -> None:
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


def _nav_actions(chat: _FakeChat) -> list[dict[str, Any]]:
    return [a for a in chat.actions if a["type"] == "history_navigate"]


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["new_chat", "delete"])
async def test_active_stream_rejects_destructive_history_paths_before_mutation(
    operation: str,
):
    controller, store, chat = _make_nav_controller()
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "hello")
    )
    active = recorder.record
    assert active is not None
    active_id = active.id
    assert controller._active_id_now() == active_id
    assert store.put_calls[-1][1] == active

    @asynccontextmanager
    async def reject_active_stream():
        raise RuntimeError(
            "Cannot clear or restore messages while a message stream is active."
        )
        yield

    chat._destructive_history_mutation = reject_active_stream  # type: ignore[method-assign]

    put_count = len(store.put_calls)
    with pytest.raises(RuntimeError, match="stream is active"):
        if operation == "new_chat":
            await controller.new_chat()
        else:
            await controller.delete(active_id)

    assert recorder.record is active
    assert controller._active_id_now() == active_id
    # The rejection happened before ANY store mutation: no new put, and
    # delete never reached the store.
    assert len(store.put_calls) == put_count
    assert store.deleted == []
    assert cast(_NavFakeAdapter, controller.adapter).set_calls == []
    assert chat.cleared == 0


@pytest.mark.anyio
async def test_switch_to_nonexistent_id_raises():
    controller, _store, _chat = _make_nav_controller()

    with pytest.raises(RuntimeError, match="no longer exists"):
        await controller.switch_to("does-not-exist")


class _UnsupportedSchemaVersionStore(ConversationStore):
    """Custom store whose get() returns a record from a newer, unsupported
    schema version -- simulates a downgrade against a store written by a
    future version of shinychat."""

    def __init__(self) -> None:
        self.put_calls: list[tuple[ConversationPartition, Any]] = []

    async def list(self, partition: ConversationPartition) -> list[Any]:
        return []

    async def get(
        self, partition: ConversationPartition, conv_id: str
    ) -> ConversationRecordV1 | None:
        rec = new_conversation_record(title="from the future")
        rec.id = conv_id
        cast(Any, rec).schema_version = MAX_SCHEMA_VERSION + 1
        return rec

    async def put(self, partition: ConversationPartition, record: Any) -> None:
        self.put_calls.append((partition, record))

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

    # The rejection installed nothing: no record, no active conversation.
    assert controller._exchange_recorder is not None
    assert controller._exchange_recorder.record is None
    assert controller._active_id_now() is None


@pytest.mark.anyio
async def test_rename_rejects_record_with_unsupported_schema_version_before_writing():
    # #322: an incompatible record must fail before any write. Under the
    # v2-only runtime the rename's inactive branch reads the target through
    # the read-gate first, so a future-version record raises before the
    # store's put() can ever see it.
    controller, store = _make_controller(store=_UnsupportedSchemaVersionStore())

    with pytest.raises(UnsupportedSchemaVersionError):
        await controller.rename("c_future", "new title")

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
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "doomed")
    )
    assert recorder.record is not None
    active_id = recorder.record.id
    await store.put(part(), recorder.record)

    await controller.delete(active_id)

    assert store.deleted == [active_id]
    navs = _nav_actions(chat)
    assert navs == [
        {
            "type": "history_navigate",
            "url": f"?conv={active_id}",
            "active_id": active_id,
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


def _make_v2_deferred_title_controller(
    title_fn: Any = None,
    *,
    title_enabled: bool = True,
    store: ConversationStore | None = None,
    adapter: _FakeAdapter | None = None,
) -> tuple[HistoryController, ConversationStore]:
    resolved_store = store if store is not None else _RecordingStore()
    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=adapter or _FakeAdapter(),  # type: ignore[arg-type]
        store=resolved_store,  # type: ignore[arg-type]
        title_fn=title_fn,
        title_enabled=title_enabled,
        client=None,
    )
    controller.partition = part()
    return controller, resolved_store


async def _v2_exchange(
    controller: HistoryController,
    transcript: ChatTranscript,
    text: str,
) -> None:
    """Drive one completed input-bearing exchange, then settle the response."""
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", text)
    )
    await transcript.append(
        TranscriptEntry(
            message=_stored_message("assistant", "answer"),
            icon=None,
        ),
        exchange_id=exchange_id,
        send=_sent,
    )
    await controller.on_response()


def _v2_transcript(controller: HistoryController) -> ChatTranscript:
    recorder = controller._exchange_recorder
    assert recorder is not None
    return ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
    )


@pytest.mark.anyio
async def test_v2_fallback_title_is_truncated_first_input():
    store = InMemoryConversationStore()
    controller, _ = _make_v2_deferred_title_controller(
        title_fn=lambda turns: "Generated Title",
        store=store,
    )
    transcript = _v2_transcript(controller)

    long_input = "What is the best way to sort a very large list of files?" * 2
    await _v2_exchange(controller, transcript, long_input)

    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    expected = " ".join(long_input.split())
    expected = expected[:47] + "..."
    assert record.title == expected
    assert record.title_source is None
    stored = await store.get(part(), record.id)
    assert stored is not None and stored.title == expected


@pytest.mark.anyio
async def test_v2_titling_fires_after_second_input_exchange_and_publishes():
    store = InMemoryConversationStore()
    controller, _ = _make_v2_deferred_title_controller(
        title_fn=lambda turns: "Generated Title",
        store=store,
    )
    transcript = _v2_transcript(controller)

    await _v2_exchange(controller, transcript, "first question")
    task_after_first_exchange = controller._title_task
    assert task_after_first_exchange is None
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    assert record.title == "first question"

    await _v2_exchange(controller, transcript, "second question")

    title_task = controller._title_task
    assert title_task is not None
    await title_task
    assert record.title == "Generated Title"
    assert record.title_source == "llm"
    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    assert stored.title == "Generated Title"
    assert stored.title_source == "llm"

    fake_chat = cast(_FakeChat, controller.chat)
    update = fake_chat.actions[-1]
    assert update["type"] == "history_update"
    assert update["active_id"] == record.id
    assert [c["title"] for c in update["conversations"]] == ["Generated Title"]


@pytest.mark.anyio
async def test_v2_titling_skipped_when_title_option_absent():
    controller, _ = _make_v2_deferred_title_controller(
        title_fn=None,
        title_enabled=False,
    )
    transcript = _v2_transcript(controller)

    await _v2_exchange(controller, transcript, "first question")
    await _v2_exchange(controller, transcript, "second question")

    assert controller._title_task is None
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    assert record.title == "first question"
    assert record.title_source is None


@pytest.mark.anyio
async def test_v2_rename_between_exchanges_blocks_auto_titling():
    controller, _ = _make_v2_deferred_title_controller(
        title_fn=lambda turns: "Generated Title",
    )
    transcript = _v2_transcript(controller)

    await _v2_exchange(controller, transcript, "first question")
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    await controller.rename(record.id, "My Title")

    await _v2_exchange(controller, transcript, "second question")

    assert controller._title_task is None
    assert record.title == "My Title"
    assert record.title_source == "user"


@pytest.mark.anyio
async def test_v2_titling_noop_when_record_switched_during_generation():
    controller, _ = _make_v2_deferred_title_controller()
    recorder = controller._exchange_recorder
    assert recorder is not None
    transcript = _v2_transcript(controller)

    await _v2_exchange(controller, transcript, "first question")
    target = recorder.record
    assert isinstance(target, ConversationRecordV2)

    async def slow_title(turns: Any) -> str:
        # Simulate the user starting a new chat while the LLM call runs
        recorder.reset()
        return "LLM Title"

    controller.title_fn = slow_title
    await _v2_exchange(controller, transcript, "second question")

    title_task = controller._title_task
    assert title_task is not None
    await title_task
    assert target.title == "first question"
    assert target.title_source is None


@pytest.mark.anyio
async def test_v2_titling_not_rescheduled_for_sibling_after_llm_title():
    store = InMemoryConversationStore()
    controller, _ = _make_v2_deferred_title_controller(
        title_fn=lambda turns: "Generated Title",
        store=store,
    )
    transcript = _v2_transcript(controller)

    await _v2_exchange(controller, transcript, "first question")
    await _v2_exchange(controller, transcript, "second question")

    title_task = controller._title_task
    assert title_task is not None
    await title_task

    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    assert record.title_source == "llm"

    # Resubmit the second input, creating a sibling exchange, then settle
    # another response: the tree-aware count stays at 2 and the LLM title
    # must not be recomputed.
    sibling_id = "sibling-resubmit"
    record.open_exchange(
        sibling_id, _stored_message("user", "second question edited")
    )
    await transcript.append(
        TranscriptEntry(
            message=_stored_message("assistant", "answer"),
            icon=None,
        ),
        exchange_id=sibling_id,
        send=_sent,
    )
    await controller.on_response()

    assert controller._title_task is title_task
    assert record.title == "Generated Title"
    assert record.title_source == "llm"


@pytest.mark.anyio
async def test_v2_retitle_not_rescheduled_at_third_input_exchange():
    """A conversation whose title is still unset gets no second chance:
    once three input-bearing exchanges sit on the active path, the
    tree-aware count no longer equals 2 and no retitle task fires.
    """
    controller, _ = _make_v2_deferred_title_controller(
        title_fn=lambda turns: None,
    )
    transcript = _v2_transcript(controller)

    await _v2_exchange(controller, transcript, "first question")
    await _v2_exchange(controller, transcript, "second question")

    title_task = controller._title_task
    assert title_task is not None
    await title_task

    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert isinstance(record, ConversationRecordV2)
    assert record.title_source is None

    await _v2_exchange(controller, transcript, "third question")

    assert controller._title_task is title_task
    assert record.title_source is None


# --- save/restore callbacks --------------------------------------------------


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
    rec3 = new_conversation_record_v2(title="newest", client_info={})
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
    # The recorder owns the active record: the newest conversation is active
    # and must survive the budget sweep.
    controller._exchange_recorder.record = rec3

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
    rec3 = new_conversation_record_v2(title="newest", client_info={})
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
    controller._exchange_recorder.record = rec3

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
    rec = new_conversation_record_v2(title="big", client_info={})
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
    controller._exchange_recorder.record = rec  # active; nothing else to evict

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
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store)
    fired: list[str] = []

    async def hook(record: Any) -> None:
        fired.append(record.id)

    controller.on_response_saved = hook
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_finished=recorder.stream_finished,
    )

    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "hello")
    )

    async def settle(stream_id: str, exchange: str) -> None:
        await transcript.start_stream(
            stream_id=stream_id,
            entry=TranscriptEntry(message=_stored_message("assistant", "hi")),
            owner_task=None,
            exchange_id=exchange,
            send=_sent,
        )
        await transcript.end_stream(
            stream_id=stream_id, status=None, error=None, send=_sent
        )
        await controller.on_response()

    await settle("stream-1", exchange_id)
    assert fired

    exchange_id2 = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "more")
    )
    await settle("stream-2", exchange_id2)

    assert len(fired) == 2
    assert fired[0] == fired[1]  # same conversation id both times


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


def _user_turn_dict(text: str) -> dict[str, Any]:
    return {
        "role": "user",
        "contents": [{"content_type": "text", "text": text}],
    }


_MATRIX_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "shared"
    / "history-v1-import-matrix.json"
)


async def _released_v1_record(
    tmp_path: Path,
) -> tuple[ConversationRecordV1, dict[str, Any]]:
    """The py 0.7.0 matrix case as a v1 record, plus its pinned expectation."""
    cases = json.loads(_MATRIX_PATH.read_text(encoding="utf-8"))
    case = next(c for c in cases if c["name"] == "py_0_7_0_versioned_ui")
    conv_id = json.loads(case["files"]["record.json"])["id"]
    conv_dir = (
        tmp_path
        / sanitize_scope("chat")
        / sanitize_scope("fixture-scope")
        / conv_id
    )
    conv_dir.mkdir(parents=True)
    for name, text in case["files"].items():
        (conv_dir / name).write_text(text, encoding="utf-8")
    store = FileConversationStore(dir=tmp_path)
    record = await store.get(
        ConversationPartition(chat_id="chat", scope="fixture-scope"), conv_id
    )
    assert isinstance(record, ConversationRecordV1)
    return record, case["expect"]


class _V1EraModelValidatingStore(ConversationStore):
    """A store written against the released v1 API, unmodified.

    Its get() builds records the v1 way: ConversationRecord.model_validate
    on a v1-shaped dict, through the public name that named the v1 model
    back then. Under the versioned types that same code yields an upgraded
    v2 record.
    """

    def __init__(self, v1_record: ConversationRecordV1) -> None:
        self._v1_dict = v1_record.model_dump(mode="json")
        self.returned: Any = None

    async def list(self, partition: ConversationPartition) -> list[Any]:
        return []

    async def get(self, partition: ConversationPartition, conv_id: str) -> Any:
        # Exactly the code a v1-era custom store ran.
        from shinychat.types import ConversationRecord

        self.returned = ConversationRecord.model_validate(self._v1_dict)
        return self.returned

    async def put(self, partition: ConversationPartition, record: Any) -> None:
        pass

    async def delete(
        self, partition: ConversationPartition, conv_id: str
    ) -> None:
        pass


class _V1InstanceReturningStore(ConversationStore):
    """A store that hands back a raw ConversationRecordV1 instance.

    A store that cached instances from before the upgrade (or builds them
    directly) still returns v1 models; the controller must upgrade them on
    read.
    """

    def __init__(self, v1_record: ConversationRecordV1) -> None:
        self._v1_dict = v1_record.model_dump(mode="json")
        self.returned: Any = None

    async def list(self, partition: ConversationPartition) -> list[Any]:
        return []

    async def get(self, partition: ConversationPartition, conv_id: str) -> Any:
        self.returned = ConversationRecordV1.model_validate(self._v1_dict)
        return self.returned

    async def put(self, partition: ConversationPartition, record: Any) -> None:
        pass

    async def delete(
        self, partition: ConversationPartition, conv_id: str
    ) -> None:
        pass


def _assert_full_v2_restore(
    controller: HistoryController,
    v1_record: ConversationRecordV1,
    expected: dict[str, Any],
) -> None:
    """Shared assertions: the switched-to legacy conversation restored as v2."""
    recorder = controller._exchange_recorder
    assert recorder is not None
    restored = recorder.record
    assert restored is not None
    assert isinstance(restored, ConversationRecordV2)
    assert restored.schema_version == 2
    assert restored.id == v1_record.id
    assert restored.active_leaf == expected["active_leaf"]
    assert controller._active_id_now() == v1_record.id
    # The displayed conversation matches the released-writer expectation.
    fake_chat = cast(_FakeChat, controller.chat)
    assert [
        message["segments"][0]["content"]
        for message in fake_chat.restored_messages
    ] == [entry["content"] for entry in expected["display"]]


@pytest.mark.anyio
async def test_v1_era_custom_store_model_validate_yields_v2(tmp_path: Path):
    """Unmodified v1-era store code now yields upgraded v2 records.

    The store's get() calls ConversationRecord.model_validate on a v1 dict
    -- the public name under the v1 API. The D1 upgrade validator turns
    that into a v2 record, so the store keeps working and the controller
    restores it as-is.
    """
    v1_record, expected = await _released_v1_record(tmp_path)
    store = _V1EraModelValidatingStore(v1_record)
    # The released record carries chatlas turns; a chatlas client can
    # re-hydrate them (a plain client would be notified the recorded turns
    # are unavailable, which is covered elsewhere).
    controller, _ = _make_controller(
        store=store,
        adapter=_FakeAdapter(chatlas=True),
    )

    await controller.switch_to(v1_record.id)

    assert isinstance(store.returned, ConversationRecordV2)
    _assert_full_v2_restore(controller, v1_record, expected)
    # The validator's v2 record went through untouched: the restored record
    # is the very object the store returned.
    assert controller._exchange_recorder is not None
    assert controller._exchange_recorder.record == store.returned


@pytest.mark.anyio
async def test_custom_store_returning_a_v1_instance_upgrades_on_read(
    tmp_path: Path,
):
    """A store handing back a ConversationRecordV1 keeps working.

    The controller's read-gate upgrades the v1 instance in memory (plan
    §7.5, D1/D4) and restores the upgraded v2 record.
    """
    v1_record, expected = await _released_v1_record(tmp_path)
    store = _V1InstanceReturningStore(v1_record)
    controller, _ = _make_controller(
        store=store,
        adapter=_FakeAdapter(chatlas=True),
    )

    await controller.switch_to(v1_record.id)

    assert isinstance(store.returned, ConversationRecordV1)
    _assert_full_v2_restore(controller, v1_record, expected)
    # The upgrade happened on the controller side: the restored record is a
    # new v2 record, not the v1 instance the store still holds.
    assert controller._exchange_recorder is not None
    assert controller._exchange_recorder.record is not store.returned


@pytest.mark.anyio
async def test_upgraded_v1_record_writes_back_as_v2_on_its_next_save(
    tmp_path: Path,
):
    """End-to-end lazy conversion (plan section 7.5): read upgrades, save
    converts. A v1 record held by the store is upgraded in memory on the
    read, and its next save writes the v2 record over the v1 one — the
    put() allowance (mechanism D4) is what lets the recorder's persist land.
    """
    v1_record, _expected = await _released_v1_record(tmp_path)
    store = InMemoryConversationStore()
    await store.put(part(), v1_record)

    controller, _ = _make_controller(
        store=store,
        adapter=_FakeAdapter(chatlas=True),
    )
    await controller.switch_to(v1_record.id)
    recorder = controller._exchange_recorder
    assert recorder is not None
    assert isinstance(recorder.record, ConversationRecordV2)

    # The next save of that conversation persists the upgraded record.
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "follow-up")
    )
    await controller.on_response()

    stored = await store.get(part(), v1_record.id)
    assert isinstance(stored, ConversationRecordV2)
    assert stored == recorder.record
    assert stored.schema_version == 2


# --- lossy-import warning surfacing (read-gate) ---------------------------


def _lossy_ui(role: str, texts: list[str]) -> list[dict[str, Any]]:
    """Unversioned stored UI: the import re-derives one display message
    from the node's turns and drops the rest, with a warning."""
    return [
        {
            "role": role,
            "segments": [{"content": text, "content_type": "markdown"}],
        }
        for text in texts
    ]


def _lossy_v1_record(id: str = "c_lossy") -> ConversationRecordV1:
    """A v1 record whose two nodes each carry one genuinely lossy step."""
    return ConversationRecordV1(
        id=id,
        title="Lossy",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        nodes={
            "n_0001": ConversationNode(
                parent=None,
                children=["n_0002"],
                turns=[_user_turn_dict("Hello")],
                ui=_lossy_ui("user", ["Hello", "Hello again"]),
                selected_child="n_0002",
            ),
            "n_0002": ConversationNode(
                parent="n_0001",
                children=[],
                turns=[
                    {
                        "role": "assistant",
                        "contents": [
                            {"content_type": "text", "text": "Hi there"}
                        ],
                    }
                ],
                ui=_lossy_ui("assistant", ["Hi there", "Hi again"]),
                selected_child=None,
            ),
        },
        next_node_seq=3,
        current_leaf="n_0002",
        values={},
    )


def _lossy_warns(conv_id: str) -> list[str]:
    return [
        f"conversation {conv_id}: node {nid!r} carried 2 stored UI "
        "message(s) without a version marker, but only one display "
        "message can be re-derived from its turns; 1 message(s) were "
        "dropped"
        for nid in ("n_0001", "n_0002")
    ]


@pytest.mark.anyio
async def test_lossy_v1_import_warns_once_per_session_per_conversation():
    """The read-gate surfaces each genuinely lossy import step, once.

    One warning per lossy step, wording unchanged from the transform; the
    second read of the same conversation is quiet.
    """
    store = _PartitionCaptureStore()
    store.records["c_lossy"] = _lossy_v1_record()
    controller, _ = _make_controller(store=store)

    with pytest.warns(UserWarning) as caught:
        record = await controller._get_record(part(), "c_lossy")

    assert isinstance(record, ConversationRecordV2)
    assert [str(w.message) for w in caught] == _lossy_warns("c_lossy")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        again = await controller._get_record(part(), "c_lossy")
    assert isinstance(again, ConversationRecordV2)

    # Per conversation, not per session: a second lossy conversation read
    # by the same controller still warns.
    store.records["c_lossy_2"] = _lossy_v1_record(id="c_lossy_2")
    with pytest.warns(UserWarning) as caught_second:
        await controller._get_record(part(), "c_lossy_2")
    assert [str(w.message) for w in caught_second] == _lossy_warns("c_lossy_2")

    # Per session: a fresh controller over the same store warns again for
    # the same conversation.
    fresh, _ = _make_controller(store=store)
    with pytest.warns(UserWarning) as caught_fresh:
        await fresh._get_record(part(), "c_lossy")
    assert [str(w.message) for w in caught_fresh] == _lossy_warns("c_lossy")


@pytest.mark.anyio
async def test_released_v1_forms_never_warn_on_read(tmp_path: Path):
    """The four released-form matrix records import losslessly: the
    read-gate stays silent for every one of them."""
    cases = json.loads(_MATRIX_PATH.read_text(encoding="utf-8"))
    assert {c["name"] for c in cases} == {
        "py_0_6_unversioned_ui",
        "py_0_7_0_versioned_ui",
        "py_0_7_1_attachments",
        "r_0_5_0",
    }
    partition = ConversationPartition(chat_id="chat", scope="fixture-scope")
    for case in cases:
        conv_id = json.loads(case["files"]["record.json"])["id"]
        conv_dir = (
            tmp_path
            / sanitize_scope("chat")
            / sanitize_scope("fixture-scope")
            / conv_id
        )
        conv_dir.mkdir(parents=True)
        for name, text in case["files"].items():
            (conv_dir / name).write_text(text, encoding="utf-8")
        store = FileConversationStore(dir=tmp_path)
        controller, _ = _make_controller(store=store)

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            record = await controller._get_record(partition, conv_id)
        assert isinstance(record, ConversationRecordV2), case["name"]


# --- rename/delete/switch guards (previously the shared v1 behavior matrix)
#
# These engine-independent controller guards used to be pinned cross-language
# by tests/shared/history-behavior-matrix.json, whose Python harness ran the
# v1 runtime and died with it (shinychat#4b9z). R keeps consuming the fixture
# until Phase 6 re-derives the matrix for the single v2 engine; these unit
# pins keep the guards themselves covered in Python until then.


async def _recorder_with_active_record() -> tuple[
    HistoryController, InMemoryConversationStore, str
]:
    """A v2 controller whose recorder owns one settled record."""
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store)
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "hello")
    )
    assert recorder.record is not None
    return controller, store, recorder.record.id


@pytest.mark.anyio
async def test_rename_normalizes_and_truncates_title_at_max_length():
    from shinychat._history_title import MAX_TITLE_LEN

    controller, store, active_id = await _recorder_with_active_record()
    title = "  New   Title  " + "x" * 40

    await controller.rename(active_id, title[: MAX_TITLE_LEN + 10])

    stored = await store.get(part(), active_id)
    assert stored is not None
    assert stored.title == ("New Title " + "x" * 40)[:MAX_TITLE_LEN]
    assert stored.title_source == "user"


@pytest.mark.anyio
async def test_rename_empty_title_is_noop():
    controller, store, active_id = await _recorder_with_active_record()

    await controller.rename(active_id, "   ")

    stored = await store.get(part(), active_id)
    assert stored is not None
    assert stored.title_source is None


@pytest.mark.anyio
async def test_rename_nonexistent_conversation_id_is_noop():
    controller, store, active_id = await _recorder_with_active_record()
    recorder = controller._exchange_recorder
    assert recorder.record is not None
    before = recorder.record.model_dump(mode="json")

    await controller.rename("does-not-exist", "New Title")

    assert recorder.record.model_dump(mode="json") == before
    assert await store.get(part(), "does-not-exist") is None


@pytest.mark.anyio
async def test_delete_nonexistent_conversation_id_is_noop():
    controller, store, active_id = await _recorder_with_active_record()
    recorder = controller._exchange_recorder
    assert recorder.record is not None

    await controller.delete("does-not-exist")

    assert recorder.record is not None
    assert controller._active_id_now() == active_id
    assert await store.get(part(), active_id) is not None


@pytest.mark.anyio
async def test_switch_to_same_active_id_is_noop():
    controller, store, active_id = await _recorder_with_active_record()
    recorder = controller._exchange_recorder
    assert recorder.record is not None
    before = recorder.record.model_dump(mode="json")
    assert controller._active_id_now() == active_id

    await controller.switch_to(active_id)

    assert recorder.record.model_dump(mode="json") == before
    assert controller._active_id_now() == active_id
