from __future__ import annotations

import asyncio
import inspect
import sys
import threading
import warnings
from contextvars import copy_context
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Callable, cast

import pytest
from htmltools import HTML, HTMLDependency, TagList, tags
from shiny import Session, reactive
from shiny.module import ResolvedId
from shiny.session import session_context
from shinychat import Chat
from shinychat._chat_normalize import message_content, message_content_chunk
from shinychat._chat_types import (
    ChatMessage,
    ChatMessageDict,
    Role,
    StoredMessage,
    StoredSegment,
)
from shinychat._history import HistoryController
from shinychat._history_store import (
    ConversationPartition,
    InMemoryConversationStore,
)
from shinychat._history_types import new_conversation_record
from shinychat._utils_types import MISSING

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


class _MockSession:
    ns: ResolvedId = ResolvedId("")
    app: object = None
    id: str = "mock-session"
    input: Any

    def __init__(self) -> None:
        from shiny import Inputs

        self.input = Inputs({}, ns=ResolvedId)

    def on_ended(self, callback: object) -> Callable[[], None]:
        return lambda: None

    def on_destroy(self, callback: object) -> None:
        pass

    def _increment_busy_count(self) -> None:
        pass

    def _decrement_busy_count(self) -> None:
        pass

    async def send_custom_message(self, type: str, message: Any) -> None:
        pass


class _BookmarkRecorder:
    def __init__(self) -> None:
        self.exclude: list[str] = []
        self.states: list[dict[str, Any]] = []
        self._callbacks: list[Any] = []

    def on_bookmark(self, callback: Any) -> Any:
        self._callbacks.append(callback)
        return callback

    def on_restore(self, callback: Any) -> Any:
        return callback

    def on_bookmarked(self, callback: Any) -> Any:
        return lambda: None

    async def update_query_string(self, url: str) -> None:
        pass

    async def __call__(self) -> None:
        state = SimpleNamespace(values={})
        for callback in self._callbacks:
            result = callback(state)
            if inspect.isawaitable(result):
                await result
        self.states.append(state.values)


class _BookmarkSession(_MockSession):
    def __init__(self) -> None:
        super().__init__()
        self.bookmark = _BookmarkRecorder()

    def is_stub_session(self) -> bool:
        return False

    def root_scope(self) -> "_BookmarkSession":
        return self


class _BookmarkClient:
    async def get_state(self) -> dict[str, object]:
        return {}

    async def set_state(self, state: object) -> None:
        pass


test_session = cast(Session, _MockSession())


def run_async(coro_fn: Any) -> None:
    exc: list[BaseException] = []

    def _run() -> None:
        try:
            asyncio.run(coro_fn())
        except BaseException as err:
            exc.append(err)

    t = threading.Thread(target=_run)
    t.start()
    t.join()
    if exc:
        raise exc[0]


def run_async_result(coro_fn: Any) -> Any:
    result: list[Any] = []

    async def capture() -> None:
        result.append(await coro_fn())

    run_async(capture)
    return result[0]


def stored_message(content: str, role: Role) -> StoredMessage:
    return StoredMessage.from_chat_message(
        ChatMessage(content=content, role=role)
    )


def test_chat_user_input_no_longer_accepts_transform_argument():
    with session_context(test_session):
        chat = Chat(id="chat")

        with pytest.raises(TypeError):
            cast(Any, chat.user_input)(transform=True)


def test_messages_format_raises():
    with session_context(test_session):
        chat = Chat(id="chat")

        with pytest.raises(TypeError, match="format.*removed"):
            chat.messages(format="openai")  # type: ignore[arg-type]


def test_messages_token_limits_raises():
    with session_context(test_session):
        chat = Chat(id="chat")

        with pytest.raises(TypeError, match="token_limits.*removed"):
            chat.messages(token_limits=(100, 0))  # type: ignore[arg-type]


def test_transcript_contains_accepted_input_before_submit_callback():
    session = cast(Session, _MockSession())
    seen: list[tuple[Any, ...]] = []
    public_seen: list[tuple[ChatMessageDict, ...]] = []

    with session_context(session):
        chat = Chat("accepted_input", history=False)

        @chat.on_user_submit
        async def _() -> None:
            seen.append(chat._transcript.read())
            public_seen.append(chat.messages())

        cast(Any, session.input[chat.user_input_id])._set(
            {"text": "message from user", "attachments": []}
        )
        run_async(reactive.flush)

    assert len(seen) == 1
    assert [entry.message.content for entry in seen[0]] == ["message from user"]
    assert chat._transcript.open_exchange_id is not None
    assert public_seen == [
        (ChatMessageDict(content="message from user", role="user"),)
    ]


def test_echoed_slash_command_records_once_before_its_callback():
    session = cast(Session, _MockSession())
    callback_state: list[tuple[str, list[str], str | None]] = []

    with session_context(session):
        chat = Chat("echoed_slash", history=False)

        @chat.slash_command("greet", "Greet the user")
        async def _(user_text: str) -> None:
            callback_state.append(
                (
                    user_text,
                    [
                        entry.message.content
                        for entry in chat._transcript.read()
                    ],
                    chat._transcript.open_exchange_id,
                )
            )

        cast(Any, session.input[chat._slash_command_id])._set(
            {"command": "greet", "userText": "world", "echo": True}
        )
        run_async(reactive.flush)

    assert len(callback_state) == 1
    assert callback_state[0][0] == "world"
    assert callback_state[0][1] == ["/greet world"]
    assert callback_state[0][2] is not None
    assert [entry.message.content for entry in chat._transcript.read()] == [
        "/greet world"
    ]


def test_echoed_slash_command_capture_error_removes_loading_message():
    session = cast(Session, _MockSession())
    actions: list[dict[str, Any]] = []
    errors: list[BaseException] = []

    with session_context(session):
        chat = Chat("echoed_slash_capture_error", history=False)

        async def _capture_error(message: ChatMessage) -> None:
            del message
            raise RuntimeError("capture failed")

        async def _capture_action(action: dict[str, Any], _deps: Any = None) -> None:
            actions.append(action)

        async def _capture_exception(error: BaseException) -> None:
            errors.append(error)

        chat._record_accepted_user_input_with_capture = _capture_error
        chat._raise_exception = _capture_exception  # type: ignore[method-assign]
        chat._send_action = _capture_action  # type: ignore[method-assign]

        cast(Any, session.input[chat._slash_command_id])._set(
            {"command": "greet", "userText": "world", "echo": True}
        )
        run_async(reactive.flush)

    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)
    assert str(errors[0]) == "capture failed"
    assert any(action["type"] == "remove_loading" for action in actions)


def test_side_effect_only_slash_command_preserves_callback_without_echo():
    session = cast(Session, _MockSession())
    callback_state: list[tuple[str, tuple[Any, ...], str | None]] = []

    with session_context(session):
        chat = Chat("side_effect_slash", history=False)

        @chat.slash_command("note", "Record a side effect", echo=False)
        async def _(user_text: str) -> None:
            callback_state.append(
                (
                    user_text,
                    chat._transcript.read(),
                    chat._transcript.open_exchange_id,
                )
            )

        cast(Any, session.input[chat._slash_command_id])._set(
            {"command": "note", "userText": "private", "echo": False}
        )
        run_async(reactive.flush)

    assert callback_state == [("private", (), None)]
    assert chat._transcript.read() == ()


def test_identical_accepted_inputs_open_distinct_exchanges_once_each():
    session = cast(Session, _MockSession())
    callback_exchanges: list[str | None] = []

    with session_context(session):
        chat = Chat("repeated_input", history=False)

        @chat.on_user_submit
        async def _() -> None:
            callback_exchanges.append(chat._transcript.open_exchange_id)

        for seq in (1, 2):
            cast(Any, session.input[chat.user_input_id])._set(
                {"text": "same message", "attachments": [], "seq": seq}
            )
            run_async(reactive.flush)

    assert len(callback_exchanges) == 2
    assert callback_exchanges[0] is not None
    assert callback_exchanges[0] != callback_exchanges[1]
    assert [entry.message.content for entry in chat._transcript.read()] == [
        "same message",
        "same message",
    ]


def test_accepted_input_records_while_an_older_stream_is_active():
    session = cast(Session, _MockSession())
    callback_state: list[tuple[list[str], str | None]] = []

    with session_context(session):
        chat = Chat("input_during_stream", history=False)
        chat._record_accepted_user_input(
            ChatMessage(content="older exchange", role="user")
        )
        older_exchange = chat._transcript.open_exchange_id
        run_async(
            lambda: chat._append_message_chunk(
                "", chunk="start", stream_id="older-stream"
            )
        )

        @chat.on_user_submit
        async def _() -> None:
            callback_state.append(
                (
                    [
                        entry.message.content
                        for entry in chat._transcript.read()
                    ],
                    chat._transcript.open_exchange_id,
                )
            )

        cast(Any, session.input[chat.user_input_id])._set(
            {"text": "next exchange", "attachments": [], "seq": 1}
        )
        run_async(reactive.flush)

    assert len(callback_state) == 1
    assert callback_state[0][0] == [
        "older exchange",
        "",
        "next exchange",
    ]
    assert callback_state[0][1] is not None
    assert callback_state[0][1] != older_exchange
    assert chat._transcript.active_stream_id == "older-stream"


def test_transcript_contains_complete_append_immediately_after_send():
    with session_context(test_session):
        chat = Chat("complete_append", history=False)

        run_async(lambda: chat.append_message("server message"))

        assert [entry.message.content for entry in chat._transcript.read()] == [
            "server message"
        ]


def test_transcript_complete_mutations_invalidate_reactive_dependents():
    with session_context(test_session):
        chat = Chat("transcript_reactive", history=False)
        seen: list[list[str]] = []

        @reactive.effect
        def _():
            chat._transcript_revision()
            seen.append(
                [entry.message.content for entry in chat._transcript.read()]
            )

        run_async(reactive.flush)
        run_async(lambda: chat.append_message("server message"))
        run_async(reactive.flush)
        run_async(chat.clear_messages)
        run_async(reactive.flush)

    assert seen == [[], ["server message"], []]


def test_messages_reactively_reads_the_transcript_revision():
    with session_context(test_session):
        chat = Chat("messages_reactive", history=False)
        seen: list[tuple[ChatMessageDict, ...]] = []

        @reactive.effect
        def _():
            seen.append(chat.messages())

        run_async(reactive.flush)
        run_async(lambda: chat.append_message("server message"))
        run_async(reactive.flush)

    assert seen == [
        (),
        (ChatMessageDict(content="server message", role="assistant"),),
    ]


def test_response_settlement_runs_after_complete_assistant_append():
    settled: list[tuple[ChatMessageDict, ...]] = []

    with session_context(test_session):
        chat = Chat("response_settlement_complete", history=False)

        async def on_settled() -> None:
            settled.append(chat.messages())

        chat._on_response_settled(on_settled)
        run_async(lambda: chat.append_message("out-of-band response"))
        assert settled == []
        run_async(reactive.flush)

    assert settled == [
        (ChatMessageDict(content="out-of-band response", role="assistant"),)
    ]


def test_response_settlement_persists_source_response_before_new_chat():
    settled: list[tuple[ChatMessageDict, ...]] = []

    with session_context(test_session):
        chat = Chat("response_settlement_before_new_chat", history=False)

        async def on_settled() -> None:
            settled.append(chat.messages())

        chat._on_response_settled(on_settled)
        run_async(lambda: chat.append_message("source response"))
        run_async(chat.clear_messages)
        run_async(reactive.flush)

    assert settled == [
        (ChatMessageDict(content="source response", role="assistant"),)
    ]
    assert chat.messages() == ()


def test_response_settlement_auto_bookmarks_source_before_new_chat():
    session = _BookmarkSession()

    with session_context(cast(Session, session)):
        chat = Chat("response_settlement_bookmark", history=False)
        chat.enable_bookmarking(cast(Any, _BookmarkClient()))
        run_async(lambda: chat.append_message("source response"))
        run_async(chat.clear_messages)
        run_async(reactive.flush)

    assert len(session.bookmark.states) == 1
    assert session.bookmark.states[0]["response_settlement_bookmark--msgs"] == [
        {
            "role": "assistant",
            "segments": [
                {"content": "source response", "content_type": "markdown"}
            ],
        }
    ]


def test_new_chat_drains_response_into_the_original_history_record_once():
    class _HistoryAdapter:
        def __init__(self) -> None:
            self.turns = [
                {"role": "user", "content": "prompt"},
                {"role": "assistant", "content": "source response"},
            ]

        def get_turns_json(self) -> list[dict[str, str]]:
            return list(self.turns)

        def get_turns_grouped(self) -> list[list[dict[str, str]]]:
            return [[turn] for turn in self.turns]

        def set_turns_json(self, turns: list[dict[str, str]]) -> None:
            self.turns = list(turns)

        def client_info(self) -> dict[str, str]:
            return {}

    with session_context(test_session):
        chat = Chat("response_settlement_history_new_chat", history=False)
        store = InMemoryConversationStore()
        controller = HistoryController(
            chat=chat,
            adapter=_HistoryAdapter(),  # type: ignore[arg-type]
            store=store,
            title_fn=None,
            title_enabled=False,
            client=None,
        )
        controller.partition = ConversationPartition(
            chat_id=chat.id, scope="response-settlement"
        )
        chat._on_response_settled(controller.on_response)

        run_async(lambda: chat.append_message("source response"))
        run_async(controller.new_chat)
        run_async(reactive.flush)

        partition = controller.partition
        assert partition is not None
        records = run_async_result(lambda: store.list(partition))
        assert len(records) == 1
        record = run_async_result(lambda: store.get(partition, records[0].id))

    assert record is not None
    assert record.response_count == 1
    assert controller.record is None
    assert chat.messages() == ()


def test_cancelled_clear_waits_for_the_same_settlement_before_mutating():
    class _HistoryAdapter:
        def __init__(self) -> None:
            self.turns = [
                {"role": "user", "content": "prompt"},
                {"role": "assistant", "content": "source response"},
            ]

        def get_turns_json(self) -> list[dict[str, str]]:
            return list(self.turns)

        def get_turns_grouped(self) -> list[list[dict[str, str]]]:
            return [[turn] for turn in self.turns]

        def set_turns_json(self, turns: list[dict[str, str]]) -> None:
            self.turns = list(turns)

        def client_info(self) -> dict[str, str]:
            return {}

    with session_context(test_session):
        chat = Chat("cancelled_new_chat_settlement", history=False)
        store = InMemoryConversationStore()
        adapter = _HistoryAdapter()
        controller = HistoryController(
            chat=chat,
            adapter=adapter,  # type: ignore[arg-type]
            store=store,
            title_fn=None,
            title_enabled=False,
            client=None,
        )
        partition = ConversationPartition(chat_id=chat.id, scope="cancelled")
        controller.partition = partition
        active = new_conversation_record(title="active")
        controller.record = active
        callback_started = asyncio.Event()
        release_callback = asyncio.Event()
        first_consumer_calls: list[str] = []
        second_consumer_calls: list[str] = []

        async def first_consumer() -> None:
            first_consumer_calls.append("settled")

        async def save_response() -> None:
            second_consumer_calls.append("started")
            callback_started.set()
            await release_callback.wait()
            await controller.on_response()

        chat._on_response_settled(first_consumer)
        chat._on_response_settled(save_response)

        async def _exercise() -> None:
            await store.put(partition, active)
            await chat.append_message("source response")
            clear = asyncio.create_task(chat.clear_messages())
            await callback_started.wait()

            clear.cancel()
            with pytest.raises(asyncio.CancelledError):
                await clear

            assert first_consumer_calls == ["settled"]
            assert second_consumer_calls == ["started"]
            assert chat.messages() == (
                ChatMessageDict(content="source response", role="assistant"),
            )
            assert controller.record is active
            assert active.response_count == 0
            assert len(chat._pending_response_settlements) == 1

            retry = asyncio.create_task(chat.clear_messages())
            await asyncio.sleep(0)
            assert second_consumer_calls == ["started"]
            assert not retry.done()
            assert chat.messages() == (
                ChatMessageDict(content="source response", role="assistant"),
            )

            release_callback.set()
            await retry

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            run_async(_exercise)

    assert first_consumer_calls == ["settled"]
    assert second_consumer_calls == ["started"]
    assert chat.messages() == ()
    assert controller.record is active
    assert adapter.turns == [
        {"role": "user", "content": "prompt"},
        {"role": "assistant", "content": "source response"},
    ]
    assert run_async_result(lambda: store.get(partition, active.id)) is active
    assert len(run_async_result(lambda: store.list(partition))) == 1
    assert active.response_count == 1
    assert not chat._pending_response_settlements


def test_cancelled_settlement_waiter_keeps_the_shared_delivery_running():
    with session_context(test_session):
        chat = Chat("cancelled_settlement_owner_waiter", history=False)
        callback_started = asyncio.Event()
        release_callback = asyncio.Event()

        async def block_settlement() -> None:
            callback_started.set()
            await release_callback.wait()

        chat._on_response_settled(block_settlement)

        async def _exercise() -> None:
            await chat.append_message("source response")
            flush = asyncio.create_task(reactive.flush())
            await callback_started.wait()

            waiter = asyncio.create_task(chat._join_response_settlement_pump())
            await asyncio.sleep(0)
            flush.cancel()

            with pytest.raises(asyncio.CancelledError):
                await flush
            assert len(chat._pending_response_settlements) == 1

            release_callback.set()
            await waiter

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            run_async(_exercise)

    assert chat.messages() == (
        ChatMessageDict(content="source response", role="assistant"),
    )
    assert not chat._pending_response_settlements


def test_cancelled_settlement_does_not_mutate_a_second_destructive_waiter():
    with session_context(test_session):
        chat = Chat("cancelled_settlement_second_waiter", history=False)
        callback_started = asyncio.Event()
        release_callback = asyncio.Event()

        async def block_settlement() -> None:
            callback_started.set()
            await release_callback.wait()

        chat._on_response_settled(block_settlement)

        async def _exercise() -> None:
            await chat.append_message("source response")
            flush = asyncio.create_task(reactive.flush())
            await callback_started.wait()

            first_clear = asyncio.create_task(chat.clear_messages())
            await asyncio.sleep(0)
            second_clear = asyncio.create_task(chat.clear_messages())
            with pytest.raises(
                RuntimeError,
                match="another transcript operation is active",
            ):
                await second_clear

            waiter = asyncio.create_task(chat._join_response_settlement_pump())
            await asyncio.sleep(0)
            assert not waiter.done()

            flush.cancel()
            with pytest.raises(asyncio.CancelledError):
                await flush
            first_clear.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first_clear
            assert len(chat._pending_response_settlements) == 1

            release_callback.set()
            await waiter

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            run_async(_exercise)

    assert chat.messages() == (
        ChatMessageDict(content="source response", role="assistant"),
    )
    assert not chat._pending_response_settlements


def test_clear_waits_for_an_in_flight_flush_settlement():
    with session_context(test_session):
        chat = Chat("settlement_drain_in_flight_flush", history=False)
        callback_started = asyncio.Event()
        release_callback = asyncio.Event()
        settled: list[tuple[ChatMessageDict, ...]] = []

        async def suspend_settlement() -> None:
            callback_started.set()
            await release_callback.wait()
            settled.append(chat.messages())

        chat._on_response_settled(suspend_settlement)

        async def _exercise() -> None:
            await chat.append_message("source response")
            flush = asyncio.create_task(reactive.flush())
            await callback_started.wait()
            assert len(chat._pending_response_settlements) == 1

            clear = asyncio.create_task(chat.clear_messages())
            await asyncio.sleep(0)
            with pytest.raises(
                RuntimeError,
                match="Cannot start a message stream while another",
            ):
                await chat._append_message_chunk(
                    "", chunk="start", stream_id="blocked"
                )

            assert chat.messages() == (
                ChatMessageDict(content="source response", role="assistant"),
            )
            assert not clear.done()
            assert len(chat._pending_response_settlements) == 1
            assert chat.messages() == (
                ChatMessageDict(content="source response", role="assistant"),
            )

            release_callback.set()
            await asyncio.gather(flush, clear)

        run_async(_exercise)

    assert chat.messages() == ()
    assert settled == [
        (ChatMessageDict(content="source response", role="assistant"),)
    ]


def test_settlement_consumer_cannot_clear_before_later_consumers():
    rejected: list[str] = []
    settled: list[tuple[ChatMessageDict, ...]] = []

    with session_context(test_session):
        chat = Chat("settlement_reentrant_clear", history=False)

        async def clear_during_settlement() -> None:
            with pytest.raises(RuntimeError, match="settlement is being delivered"):
                await chat.clear_messages()
            rejected.append("clear")

        async def observe_settlement() -> None:
            settled.append(chat.messages())

        chat._on_response_settled(clear_during_settlement)
        chat._on_response_settled(observe_settlement)
        run_async(lambda: chat.append_message("source response"))
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            run_async(reactive.flush)

    assert rejected == ["clear"]
    assert settled == [
        (ChatMessageDict(content="source response", role="assistant"),)
    ]
    assert chat.messages() == (
        ChatMessageDict(content="source response", role="assistant"),
    )


def test_settlement_consumer_cannot_clear_a_different_chat_before_later_consumers():
    rejected: list[str] = []
    settled: list[tuple[ChatMessageDict, ...]] = []

    with session_context(test_session):
        source = Chat("settlement_source", history=False)
        other = Chat("settlement_other", history=False)

        async def clear_other() -> None:
            with pytest.raises(RuntimeError, match="settlement is being delivered"):
                await other.clear_messages()
            rejected.append("clear")

        async def observe_source() -> None:
            settled.append(source.messages())

        source._on_response_settled(clear_other)
        source._on_response_settled(observe_source)
        run_async(lambda: other.append_message("other response"))
        run_async(lambda: source.append_message("source response"))
        run_async(reactive.flush)

    assert rejected == ["clear"]
    assert settled == [
        (ChatMessageDict(content="source response", role="assistant"),)
    ]
    assert source.messages() == (
        ChatMessageDict(content="source response", role="assistant"),
    )
    assert other.messages() == (
        ChatMessageDict(content="other response", role="assistant"),
    )


def test_reciprocal_settlement_mutations_fail_fast_without_deadlocking():
    rejected: list[str] = []

    with session_context(test_session):
        chat_a = Chat("reciprocal_settlement_a", history=False)
        chat_b = Chat("reciprocal_settlement_b", history=False)

        async def clear_b() -> None:
            with pytest.raises(RuntimeError, match="settlement is being delivered"):
                await chat_b.clear_messages()
            rejected.append("A->B")

        async def clear_a() -> None:
            with pytest.raises(RuntimeError, match="settlement is being delivered"):
                await chat_a.clear_messages()
            rejected.append("B->A")

        chat_a._on_response_settled(clear_b)
        chat_b._on_response_settled(clear_a)

        async def settle_both() -> None:
            await chat_a.append_message("response A")
            await chat_b.append_message("response B")
            await asyncio.wait_for(reactive.flush(), timeout=1)

        run_async(settle_both)

    assert rejected == ["A->B", "B->A"]
    assert chat_a.messages() == (
        ChatMessageDict(content="response A", role="assistant"),
    )
    assert chat_b.messages() == (
        ChatMessageDict(content="response B", role="assistant"),
    )


def test_settlement_consumer_child_task_can_clear_after_delivery_completes():
    rejected: list[str] = []
    settled: list[tuple[ChatMessageDict, ...]] = []

    with session_context(test_session):
        chat = Chat("settlement_child_reentrant_clear", history=False)
        child_task: asyncio.Task[None] | None = None
        child_rejected = asyncio.Event()
        release_child = asyncio.Event()

        async def clear_in_child() -> None:
            with pytest.raises(RuntimeError, match="settlement is being delivered"):
                await chat.clear_messages()
            rejected.append("clear")
            child_rejected.set()
            await release_child.wait()
            await chat.clear_messages()

        async def clear_during_settlement() -> None:
            nonlocal child_task
            child_task = copy_context().run(
                asyncio.create_task, clear_in_child()
            )
            await child_rejected.wait()

        async def observe_settlement() -> None:
            settled.append(chat.messages())

        chat._on_response_settled(clear_during_settlement)
        chat._on_response_settled(observe_settlement)

        async def flush_response() -> None:
            await chat.append_message("source response")
            await asyncio.wait_for(reactive.flush(), timeout=1)
            assert child_task is not None
            assert not chat._pending_response_settlements
            release_child.set()
            await child_task

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            run_async(flush_response)

    assert rejected == ["clear"]
    assert settled == [
        (ChatMessageDict(content="source response", role="assistant"),)
    ]
    assert chat.messages() == ()


def test_nested_settlement_child_stays_blocked_until_outer_delivery_dequeues():
    rejected: list[str] = []
    child_task: asyncio.Task[None] | None = None

    with session_context(test_session):
        chat_a = Chat("nested_settlement_source", history=False)
        chat_b = Chat("nested_settlement_target", history=False)
        b_dequeued = asyncio.Event()
        child_rejected = asyncio.Event()
        retry_child = asyncio.Event()

        async def clear_in_child() -> None:
            await b_dequeued.wait()
            with pytest.raises(RuntimeError, match="settlement is being delivered"):
                await chat_b.clear_messages()
            rejected.append("while A is pending")
            child_rejected.set()
            await retry_child.wait()
            await chat_b.clear_messages()

        async def settle_b() -> None:
            nonlocal child_task
            child_task = copy_context().run(
                asyncio.create_task, clear_in_child()
            )

        async def settle_a() -> None:
            await chat_b.append_message("response B")
            await chat_b._join_response_settlement_pump()
            assert not chat_b._pending_response_settlements
            b_dequeued.set()
            await child_rejected.wait()

        chat_a._on_response_settled(settle_a)
        chat_b._on_response_settled(settle_b)

        async def _exercise() -> None:
            await chat_a.append_message("response A")
            await asyncio.wait_for(reactive.flush(), timeout=1)
            assert child_task is not None
            assert not chat_a._pending_response_settlements
            retry_child.set()
            await child_task

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            run_async(_exercise)

    assert rejected == ["while A is pending"]
    assert chat_a.messages() == (
        ChatMessageDict(content="response A", role="assistant"),
    )
    assert chat_b.messages() == ()


def test_independent_task_is_not_blocked_by_another_chat_settlement():
    with session_context(test_session):
        chat_a = Chat("independent_settlement_source", history=False)
        chat_b = Chat("independent_settlement_target", history=False)
        settlement_started = asyncio.Event()
        release_settlement = asyncio.Event()

        async def settle_a() -> None:
            settlement_started.set()
            await release_settlement.wait()

        chat_a._on_response_settled(settle_a)

        async def _exercise() -> None:
            await chat_a.append_message("response A")
            flush = asyncio.create_task(reactive.flush())
            await settlement_started.wait()

            clear_b = asyncio.create_task(chat_b.clear_messages())
            await asyncio.wait_for(clear_b, timeout=1)

            release_settlement.set()
            await asyncio.wait_for(flush, timeout=1)

        run_async(_exercise)

    assert chat_a.messages() == (
        ChatMessageDict(content="response A", role="assistant"),
    )
    assert chat_b.messages() == ()


def test_cancelled_response_settlement_consumer_skips_pending_delivery():
    settled: list[str] = []

    with session_context(test_session):
        chat = Chat("response_settlement_cancel_pending", history=False)

        async def on_settled() -> None:
            settled.append("settled")

        cancel = chat._on_response_settled(on_settled)
        run_async(lambda: chat.append_message("source response"))
        cancel()
        run_async(reactive.flush)

    assert settled == []


def test_clear_without_a_pending_response_settlement_invokes_no_consumers():
    settled: list[str] = []

    with session_context(test_session):
        chat = Chat("response_settlement_isolated_clear", history=False)

        async def on_settled() -> None:
            settled.append("settled")

        chat._on_response_settled(on_settled)
        run_async(chat.clear_messages)
        run_async(reactive.flush)

    assert settled == []


def test_clear_drains_each_pending_consumer_despite_consumer_failure():
    settled: list[tuple[ChatMessageDict, ...]] = []

    with session_context(test_session):
        chat = Chat("response_settlement_clear_consumer_failure", history=False)

        async def broken_callback() -> None:
            raise RuntimeError("callback failed")

        async def on_settled() -> None:
            settled.append(chat.messages())

        chat._on_response_settled(broken_callback)
        chat._on_response_settled(on_settled)
        run_async(lambda: chat.append_message("source response"))
        with pytest.warns(UserWarning, match="callback failed"):
            run_async(chat.clear_messages)
        run_async(reactive.flush)

    assert settled == [
        (ChatMessageDict(content="source response", role="assistant"),)
    ]


def test_cancelled_settlement_consumer_does_not_cancel_delivery():
    settled: list[str] = []

    with session_context(test_session):
        chat = Chat("response_settlement_cancelled_consumer", history=False)

        async def cancelled_callback() -> None:
            raise asyncio.CancelledError()

        async def on_settled() -> None:
            settled.append("settled")

        chat._on_response_settled(cancelled_callback)
        chat._on_response_settled(on_settled)
        run_async(lambda: chat.append_message("source response"))
        with pytest.warns(UserWarning, match="callback failed"):
            run_async(reactive.flush)

    assert settled == ["settled"]
    assert not chat._pending_response_settlements


def test_consumer_cancellation_does_not_reschedule_shared_delivery():
    with session_context(test_session):
        chat = Chat("simultaneous_settlement_cancellation", history=False)
        owner_task: asyncio.Task[Any] | None = None

        async def cancel_owner_and_consumer() -> None:
            consumer_task = asyncio.current_task()
            assert consumer_task is not None
            consumer_task.cancel()
            try:
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                assert owner_task is not None
                asyncio.get_running_loop().call_soon(owner_task.cancel)
                raise

        cancel_consumer = chat._on_response_settled(cancel_owner_and_consumer)

        async def _exercise() -> None:
            nonlocal owner_task
            await chat.append_message("source response")
            owner_task = asyncio.current_task()
            await reactive.flush()

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with pytest.raises(asyncio.CancelledError):
                run_async(_exercise)

        assert not chat._pending_response_settlements
        cancel_consumer()

    assert chat.messages() == (
        ChatMessageDict(content="source response", role="assistant"),
    )
    assert not chat._pending_response_settlements


def test_cancellation_after_consumer_completion_does_not_rerun_settlement():
    settled: list[str] = []

    with session_context(test_session):
        chat = Chat("settlement_cancellation_wakeup", history=False)
        clear: asyncio.Task[None] | None = None

        async def on_settled() -> None:
            settled.append("settled")
            assert clear is not None
            asyncio.get_running_loop().call_soon(clear.cancel)

        chat._on_response_settled(on_settled)

        async def _exercise() -> None:
            nonlocal clear
            await chat.append_message("source response")
            clear = asyncio.create_task(chat.clear_messages())
            with pytest.raises(asyncio.CancelledError):
                await clear

            assert settled == ["settled"]
            assert chat.messages() == (
                ChatMessageDict(content="source response", role="assistant"),
            )
            assert not chat._pending_response_settlements

            await chat.clear_messages()

        run_async(_exercise)

    assert settled == ["settled"]
    assert chat.messages() == ()


def test_history_like_consumer_mutation_before_await_runs_once_after_clear_cancel():
    mutations: list[str] = []

    with session_context(test_session):
        chat = Chat("settlement_history_like_mutation", history=False)
        started = asyncio.Event()
        release = asyncio.Event()

        async def mutate_then_wait() -> None:
            mutations.append("saved")
            started.set()
            await release.wait()

        chat._on_response_settled(mutate_then_wait)

        async def _exercise() -> None:
            await chat.append_message("source response")
            clear = asyncio.create_task(chat.clear_messages())
            await started.wait()

            clear.cancel()
            with pytest.raises(asyncio.CancelledError):
                await clear
            assert mutations == ["saved"]

            release.set()
            while chat._pending_response_settlements:
                await asyncio.sleep(0)

            await chat.clear_messages()

        run_async(_exercise)

    assert mutations == ["saved"]
    assert chat.messages() == ()


def test_response_settlement_pump_keeps_queued_flush_behind_blocked_drain():
    timeline: list[str] = []
    active_consumer_count = 0
    max_active_consumer_count = 0

    with session_context(test_session):
        chat = Chat("settlement_fifo_pump", history=False)
        history_started = asyncio.Event()
        release_history = asyncio.Event()
        history_delivery_count = 0

        async def persist_history() -> None:
            nonlocal active_consumer_count
            nonlocal max_active_consumer_count
            nonlocal history_delivery_count
            history_delivery_count += 1
            active_consumer_count += 1
            max_active_consumer_count = max(
                max_active_consumer_count, active_consumer_count
            )
            timeline.append(f"history-{history_delivery_count}-start")
            try:
                if history_delivery_count == 1:
                    history_started.set()
                    await release_history.wait()
            finally:
                timeline.append(f"history-{history_delivery_count}-end")
                active_consumer_count -= 1

        async def persist_bookmark() -> None:
            nonlocal active_consumer_count, max_active_consumer_count
            active_consumer_count += 1
            max_active_consumer_count = max(
                max_active_consumer_count, active_consumer_count
            )
            delivery_count = history_delivery_count
            timeline.append(f"bookmark-{delivery_count}-start")
            timeline.append(f"bookmark-{delivery_count}-end")
            active_consumer_count -= 1

        chat._on_response_settled(persist_history)
        chat._on_response_settled(persist_bookmark)

        async def _exercise() -> None:
            await chat.append_message("A")
            clear = asyncio.create_task(chat.clear_messages())
            await history_started.wait()

            clear.cancel()
            with pytest.raises(asyncio.CancelledError):
                await clear

            await chat.append_message("B")
            flush = asyncio.create_task(reactive.flush())
            await asyncio.sleep(0)

            assert timeline == ["history-1-start"]
            assert max_active_consumer_count == 1

            release_history.set()
            await flush

        run_async(_exercise)

    assert timeline == [
        "history-1-start",
        "history-1-end",
        "bookmark-1-start",
        "bookmark-1-end",
        "history-2-start",
        "history-2-end",
        "bookmark-2-start",
        "bookmark-2-end",
    ]
    assert max_active_consumer_count == 1
    assert not chat._pending_response_settlements


def test_destroy_and_session_end_cancel_response_settlement_pump():
    class _TeardownSession(_MockSession):
        def __init__(self) -> None:
            super().__init__()
            self.ended_callbacks: list[Callable[[], None]] = []

        def on_ended(self, callback: object) -> Callable[[], None]:
            callback_fn = cast(Callable[[], None], callback)
            self.ended_callbacks.append(callback_fn)

            def cancel() -> None:
                self.ended_callbacks.remove(callback_fn)

            return cancel

        def end(self) -> None:
            for callback in list(self.ended_callbacks):
                callback()

    session = _TeardownSession()
    scheduled: list[str] = []
    active: list[str] = []

    with session_context(cast(Session, session)):
        scheduled_chat = Chat("settlement_destroy_scheduled", history=False)

        async def scheduled_consumer() -> None:
            scheduled.append("settled")

        scheduled_chat._on_response_settled(scheduled_consumer)
        run_async(lambda: scheduled_chat.append_message("source response"))
        assert len(scheduled_chat._pending_response_settlements) == 1
        scheduled_chat.destroy()
        run_async(reactive.flush)
        assert scheduled == []
        assert not scheduled_chat._pending_response_settlements
        assert scheduled_chat.destroy not in session.ended_callbacks

        active_chat = Chat("settlement_destroy_active", history=False)
        assert session.ended_callbacks.count(active_chat.destroy) == 1
        started = asyncio.Event()

        async def active_consumer() -> None:
            active.append("started")
            started.set()
            await asyncio.Event().wait()

        active_chat._on_response_settled(active_consumer)

        async def _exercise() -> None:
            await active_chat.append_message("A")
            flush = asyncio.create_task(reactive.flush())
            await started.wait()
            await active_chat.append_message("B")
            assert len(active_chat._pending_response_settlements) == 2
            runner = active_chat._response_settlement_runner
            assert runner is not None

            session.end()
            with pytest.raises(asyncio.CancelledError):
                await flush
            assert active_chat.destroy not in session.ended_callbacks
            assert not active_chat._pending_response_settlements
            assert runner.cancelled()

        run_async(_exercise)

    assert active == ["started"]


def test_clear_drains_all_consumers_when_callback_warning_is_an_error():
    settled: list[tuple[ChatMessageDict, ...]] = []

    with session_context(test_session):
        chat = Chat("response_settlement_warning_error", history=False)

        async def broken_callback() -> None:
            raise RuntimeError("callback failed")

        async def on_settled() -> None:
            settled.append(chat.messages())

        chat._on_response_settled(broken_callback)
        chat._on_response_settled(on_settled)

        async def end_errored_stream() -> None:
            await chat._append_message_chunk(
                "", chunk="start", stream_id="stream"
            )
            await chat._append_message_chunk(
                "",
                chunk="end",
                stream_id="stream",
                status="error",
                error="response failed",
            )

        run_async(end_errored_stream)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            run_async(chat.clear_messages)
        run_async(reactive.flush)

    assert len(settled) == 1
    assert settled[0][-1].get("status") == "error"
    assert chat.messages() == ()


def test_multiple_complete_responses_in_one_flush_settle_once_each():
    settled: list[tuple[ChatMessageDict, ...]] = []

    with session_context(test_session):
        chat = Chat("response_settlement_batched_complete", history=False)

        async def on_settled() -> None:
            settled.append(chat.messages())

        chat._on_response_settled(on_settled)
        run_async(lambda: chat.append_message("first response"))
        run_async(lambda: chat.append_message("second response"))
        run_async(reactive.flush)
        run_async(reactive.flush)

    assert settled == [
        (
            ChatMessageDict(content="first response", role="assistant"),
            ChatMessageDict(content="second response", role="assistant"),
        ),
        (
            ChatMessageDict(content="first response", role="assistant"),
            ChatMessageDict(content="second response", role="assistant"),
        ),
    ]


def test_response_settlement_ignores_nonterminal_transcript_mutations():
    settled: list[str] = []

    with session_context(test_session):
        with pytest.warns(Warning, match="Chat\\(messages"):
            chat = Chat(
                "response_settlement_nonterminal",
                history=False,
                messages=["initial"],
            )

        async def on_settled() -> None:
            settled.append("settled")

        chat._on_response_settled(on_settled)
        run_async(reactive.flush)
        run_async(chat.clear_messages)
        chat._record_accepted_user_input(
            ChatMessage(content="accepted", role="user")
        )
        run_async(
            lambda: chat._restore_bookmark_message(
                {
                    "role": "assistant",
                    "segments": [
                        {"content": "restored", "content_type": "markdown"}
                    ],
                }
            )
        )
        run_async(
            lambda: chat._append_message_chunk(
                "", chunk="start", stream_id="partial"
            )
        )
        run_async(
            lambda: chat._append_message_chunk(
                "partial", chunk=True, stream_id="partial"
            )
        )
        run_async(reactive.flush)

    assert settled == []


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (None, None),
        ("error", "response failed"),
        ("cancelled", None),
    ],
)
def test_response_settlement_runs_once_for_each_stream_terminal_outcome(
    status: str | None, error: str | None
):
    settled: list[str] = []

    with session_context(test_session):
        chat = Chat("response_settlement_stream", history=False)

        async def on_settled() -> None:
            settled.append("settled")

        chat._on_response_settled(on_settled)

        async def exercise() -> None:
            await chat._append_message_chunk(
                "", chunk="start", stream_id="stream"
            )
            await chat._append_message_chunk(
                "",
                chunk="end",
                stream_id="stream",
                status=cast(Any, status),
                error=error,
            )

        run_async(exercise)
        run_async(reactive.flush)

    assert settled == ["settled"]


def test_response_settlement_runs_after_terminal_stream_send_failure():
    settled: list[str] = []

    with session_context(test_session):
        chat = Chat("response_settlement_terminal_failure", history=False)

        async def on_settled() -> None:
            settled.append("settled")

        chat._on_response_settled(on_settled)

        async def fail_chunk_end(action: Any, deps: Any = None) -> None:
            if action["type"] == "chunk_end":
                raise RuntimeError("terminal send failed")

        chat._send_action = fail_chunk_end  # type: ignore[method-assign]

        async def stream():
            yield "partial"

        with pytest.raises(RuntimeError, match="terminal send failed"):
            run_async(lambda: chat._append_message_stream(stream()))
        run_async(reactive.flush)

    assert settled == ["settled"]
    assert chat.messages()[-1].get("status") == "error"


def test_old_stream_terminal_settles_after_newer_input():
    settled: list[tuple[str, ...]] = []

    with session_context(test_session):
        chat = Chat("response_settlement_old_stream", history=False)
        chat._record_accepted_user_input(
            ChatMessage(content="older input", role="user")
        )

        async def on_settled() -> None:
            settled.append(tuple(message["content"] for message in chat.messages()))

        chat._on_response_settled(on_settled)

        async def exercise() -> None:
            await chat._append_message_chunk(
                "", chunk="start", stream_id="older-stream"
            )
            chat._record_accepted_user_input(
                ChatMessage(content="newer input", role="user")
            )
            await chat._append_message_chunk(
                "",
                chunk="end",
                stream_id="older-stream",
            )

        run_async(exercise)
        run_async(reactive.flush)

    assert settled == [("older input", "", "newer input")]


def test_response_settlement_callback_failure_does_not_mask_stream_outcome():
    with session_context(test_session):
        chat = Chat("response_settlement_failure", history=False)

        async def broken_callback() -> None:
            raise RuntimeError("callback failed")

        chat._on_response_settled(broken_callback)

        async def exercise() -> None:
            await chat._append_message_chunk(
                "", chunk="start", stream_id="stream"
            )
            await chat._append_message_chunk(
                "",
                chunk="end",
                stream_id="stream",
                status="error",
                error="stream failed",
            )

        run_async(exercise)
        with pytest.warns(UserWarning, match="callback failed"):
            run_async(reactive.flush)

    assert chat.messages()[-1].get("status") == "error"


def test_transcript_does_not_commit_system_messages_without_wire_send():
    with session_context(test_session):
        chat = Chat("system_message", history=False)
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _exercise() -> None:
            await chat.append_message(
                ChatMessage(content="not displayed", role="system")
            )
            await chat._restore_bookmark_message(
                {
                    "role": "system",
                    "segments": [
                        {
                            "content": "not restored",
                            "content_type": "markdown",
                        }
                    ],
                }
            )

        run_async(_exercise)

        assert sent == []
        assert chat._transcript.read() == ()


def test_transcript_append_send_failure_leaves_owner_unchanged():
    with session_context(test_session):
        chat = Chat("append_failure", history=False)

        async def _fail(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("send failed")

        chat._send_action = _fail  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="send failed"):
            run_async(lambda: chat.append_message("discarded"))

        assert chat._transcript.read() == ()


def test_transcript_clear_send_failure_leaves_owner_unchanged():
    with session_context(test_session):
        chat = Chat("clear_failure", history=False)

        run_async(lambda: chat.append_message("kept"))

        async def _fail(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("clear failed")

        chat._send_action = _fail  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="clear failed"):
            run_async(chat.clear_messages)

        assert [entry.message.content for entry in chat._transcript.read()] == [
            "kept"
        ]


def test_transcript_captures_complete_message_wire_spec():
    from shinychat._attachments import Attachment

    with session_context(test_session):
        chat = Chat("wire_spec", history=False)
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append({"action": action, "deps": deps})

        async def _transform(content: str, chunk: str, done: bool) -> str:
            assert chunk == ""
            assert done
            return f"{content} transformed"

        chat._send_action = _capture  # type: ignore[method-assign]
        chat._transform_assistant = _transform
        chat._serialize_html_deps = lambda deps: [  # type: ignore[method-assign]
            {"name": "chart", "metadata": {"version": "1.0"}}
        ]
        message = ChatMessage(
            content="source",
            role="assistant",
            attachments=[
                Attachment.from_data(
                    b"chart", mime="image/png", name="chart.png"
                )
            ],
        )
        message.html_deps = [HTMLDependency(name="chart", version="1.0")]

        run_async(
            lambda: chat.append_message(message, icon=HTML("<i>chart</i>"))
        )

        entry = chat._transcript.read()[0]
        assert entry.message.content == "source transformed"
        assert entry.message.attachments[0].name == "chart.png"
        assert entry.message.html_deps == [
            {"name": "chart", "metadata": {"version": "1.0"}}
        ]
        assert entry.icon == "<i>chart</i>"
        assert sent[0]["action"]["message"]["icon"] == "<i>chart</i>"


@pytest.mark.parametrize(
    ("icon", "expected_icon"),
    [
        pytest.param(False, "", id="false"),
        pytest.param(None, None, id="none"),
        pytest.param(True, None, id="true"),
        pytest.param(HTML(""), "", id="empty-html"),
        pytest.param("", "", id="empty-string"),
        pytest.param(HTML("<i>custom</i>"), "<i>custom</i>", id="custom"),
    ],
)
def test_transcript_complete_append_captures_resolved_icon_wire_spec(
    icon: Any, expected_icon: str | None
):
    with session_context(test_session):
        chat = Chat("resolved_icon", history=False)
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        chat._send_action = _capture  # type: ignore[method-assign]

        run_async(lambda: chat.append_message("complete message", icon=icon))

    entry = chat._transcript.read()[0]
    payload = sent[0]["message"]
    assert entry.icon == expected_icon
    if expected_icon is None:
        assert "icon" not in payload
    else:
        assert payload["icon"] == expected_icon


def test_transcript_entries_are_defensive_for_nested_wire_specs():
    from shinychat._attachments import Attachment

    with session_context(test_session):
        chat = Chat("defensive_entry", history=False)
        chat._serialize_html_deps = lambda deps: [  # type: ignore[method-assign]
            {"name": "chart", "metadata": {"version": "1.0"}}
        ]
        message = ChatMessage(
            content="source",
            role="assistant",
            attachments=[
                Attachment.from_data(
                    b"chart", mime="image/png", name="chart.png"
                )
            ],
        )
        message.html_deps = [HTMLDependency(name="chart", version="1.0")]

        run_async(
            lambda: chat.append_message(message, icon=HTML("<i>chart</i>"))
        )

        projection = chat._transcript.read()[0]
        projection.message.attachments[0].name = "mutated.png"
        assert projection.message.html_deps is not None
        metadata = cast(
            dict[str, str], projection.message.html_deps[0]["metadata"]
        )
        metadata["version"] = "mutated"
        projection.icon = "mutated"

        committed = chat._transcript.read()[0]
        assert committed.message.attachments[0].name == "chart.png"
        assert committed.message.html_deps == [
            {"name": "chart", "metadata": {"version": "1.0"}}
        ]
        assert committed.icon == "<i>chart</i>"


def test_tokenizer_raises():
    with session_context(test_session):
        with pytest.raises(TypeError, match="tokenizer.*removed"):
            Chat(id="chat", tokenizer=object())  # type: ignore[arg-type]


def test_transform_user_input_raises():
    with session_context(test_session):
        chat = Chat(id="chat")

        with pytest.raises(TypeError, match="transform_user_input.*removed"):
            chat.transform_user_input(lambda x: x)


def test_stream_replace_discards_stale_html_dependencies():
    with session_context(test_session):
        chat = Chat(id="chat")
        sent: list[dict[str, Any]] = []

        custom_dep = HTMLDependency(
            name="custom-styled-card",
            version="1.0.0",
            source={"subdir": "."},
            stylesheet={"href": "custom.css"},
        )

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append({"action": action, "deps": deps})

        chat._send_action = _capture  # type: ignore[method-assign]
        chat._serialize_html_deps = lambda deps: (  # type: ignore[method-assign]
            None
            if not deps
            else [{"name": dep.name, "version": dep.version} for dep in deps]
        )

        async def _exercise_stream() -> None:
            await chat._append_message_chunk(
                "", chunk="start", stream_id="stream-id"
            )
            await chat._append_message_chunk(
                TagList(custom_dep, tags.div("ephemeral")),
                chunk=True,
                stream_id="stream-id",
            )
            await chat._append_message_chunk(
                "final",
                chunk="end",
                operation="replace",
                stream_id="stream-id",
            )

        run_async(_exercise_stream)

        # The `chunk="end", operation="replace"` send is the "chunk" action
        # carrying the replaced content; find it and confirm the stale
        # dependency from the earlier chunk didn't survive the replace.
        replace_sends = [
            s
            for s in sent
            if s["action"]["type"] == "chunk"
            and s["action"]["operation"] == "replace"
        ]
        assert len(replace_sends) == 1
        final_send = replace_sends[0]
        assert final_send["action"]["content"] == "final"
        dep_names = [d["name"] for d in (final_send["deps"] or [])]
        assert "custom-styled-card" not in dep_names
        assert [
            dep["name"]
            for dep in (chat._transcript.read()[0].message.html_deps or [])
        ] == ["custom-styled-card"]


# ------------------------------------------------------------------------------------
# Unit tests for message_content() and message_content_chunk().
#
# This is where we go from provider's response object to ChatMessage.
#
# The general idea is to check that the provider's output message type match our
# expectations. If these tests fail, it doesn't not necessarily mean that our code is
# wrong (i.e., updating the test may be sufficient), but we'll still want to be aware
# and double-check our code.
# ------------------------------------------------------------------------------------


def test_string_normalization():
    m = message_content("Hello world!")
    assert m.content == "Hello world!"
    assert m.role == "assistant"
    mc = message_content_chunk("Hello world!")
    assert mc.content == "Hello world!"
    assert mc.role == "assistant"


def test_dict_normalization():
    m = message_content({"content": "Hello world!", "role": "assistant"})
    assert m.content == "Hello world!"
    assert m.role == "assistant"
    mc = message_content_chunk({"content": "Hello world!"})
    assert mc.content == "Hello world!"
    assert mc.role == "assistant"


def test_chat_message_normalization():
    m = message_content(ChatMessage(content="Hello world!", role="assistant"))
    assert m.content == "Hello world!"
    assert m.role == "assistant"
    mc = message_content_chunk(ChatMessage(content="Hello world!"))
    assert mc.content == "Hello world!"
    assert mc.role == "assistant"


def test_tagifiable_normalization():
    from shiny.ui import HTML, div

    # Interpreted as markdown (without escaping)
    m = message_content("Hello <span>world</span>!")
    assert m.content == "Hello <span>world</span>!"
    assert m.role == "assistant"

    # Interpreted as HTML (without escaping)
    m = message_content(HTML("Hello <span>world</span>!"))
    assert (
        m.content
        == "\n\n<shiny-chat-raw-html>Hello <span>world</span>!</shiny-chat-raw-html>\n\n"
    )
    assert m.role == "assistant"

    # Interpreted as HTML (if top-level object is tag-like, inner string contents get escaped)
    m = message_content(div("Hello <span>world</span>!"))
    assert (
        m.content
        == "\n\n<shiny-chat-raw-html>\n  <div>Hello &lt;span&gt;world&lt;/span&gt;!</div>\n</shiny-chat-raw-html>\n\n"
    )
    assert m.role == "assistant"


def test_langchain_normalization():
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import BaseMessage, BaseMessageChunk

    # Make sure return type of the .invoke()/.stream() methods haven't changed
    # (If they do, we may need to update the mock and normalization functions)
    assert BaseChatModel.invoke.__annotations__["return"] == "AIMessage"
    assert (
        BaseChatModel.stream.__annotations__["return"]
        == "Iterator[AIMessageChunk]"
    )

    # Mock & normalize return value of BaseChatModel.invoke()
    msg = BaseMessage(content="Hello world!", role="assistant", type="foo")
    m = message_content(msg)
    assert m.content == "Hello world!"
    assert m.role == "assistant"

    # Mock & normalize return value of BaseChatModel.stream()
    chunk = BaseMessageChunk(content="Hello ", type="foo")
    m = message_content_chunk(chunk)
    assert m.content == "Hello "
    assert m.role == "assistant"


def test_google_content_object_normalization():
    # Not available for Python 3.9
    if sys.version_info < (3, 10):
        return

    from google.genai import types

    # Test Content object normalization
    c = types.Content(parts=[types.Part(text="Hello world!")], role="model")
    m = message_content(c)
    assert m.content == "Hello world!"
    assert m.role == "assistant"


def test_google_multimodal_normalization():
    # Not available for Python 3.9
    if sys.version_info < (3, 10):
        return

    from google.genai import types

    # Text part, image part, text part.
    c = types.Content(
        parts=[
            types.Part(text="Here is an image:"),
            types.Part(
                inline_data=types.Blob(mime_type="image/png", data=b"AAAA")
            ),
            types.Part(text=" described above."),
        ],
        role="model",
    )

    m = message_content(c)
    assert m.content == "Here is an image: described above."
    assert m.role == "assistant"


def test_google_normalization():
    # Not available for Python 3.9
    if sys.version_info < (3, 10):
        return

    from google.genai.models import Models
    from google.genai.types import GenerateContentResponse

    assert (
        inspect.signature(Models.generate_content).return_annotation
        == GenerateContentResponse
    )


def test_anthropic_normalization():
    if sys.version_info < (3, 11):
        pytest.skip("Anthropic is only available for Python 3.11+")

    from anthropic import (  # pyright: ignore[reportMissingImports]
        Anthropic,
        AsyncAnthropic,
    )
    from anthropic.resources.messages import (  # pyright: ignore[reportMissingImports]
        AsyncMessages,
        Messages,
    )
    from anthropic.types import (  # pyright: ignore[reportMissingImports]
        TextBlock,
        Usage,
    )
    from anthropic.types.message import (  # pyright: ignore[reportMissingImports]
        Message,
    )
    from anthropic.types.raw_content_block_delta_event import (  # pyright: ignore[reportMissingImports]
        RawContentBlockDeltaEvent,
    )
    from anthropic.types.text_delta import (  # pyright: ignore[reportMissingImports]
        TextDelta,
    )

    # Make sure return type of Anthropic().messages.create() hasn't changed
    assert isinstance(Anthropic().messages, Messages)
    assert isinstance(AsyncAnthropic().messages, AsyncMessages)

    # Make sure return type of llm.messages.create() hasn't changed
    assert (
        AsyncMessages.create.__annotations__["return"]
        == "Message | AsyncStream[RawMessageStreamEvent]"
    )
    assert (
        Messages.create.__annotations__["return"]
        == "Message | Stream[RawMessageStreamEvent]"
    )

    # Mock return object from Anthropic().messages.create()
    msg = Message(
        content=[
            TextBlock(type="text", text="Hello world!"),
        ],
        role="assistant",
        id="foo",
        type="message",
        model="foo",
        usage=Usage(input_tokens=0, output_tokens=0),
    )

    m = message_content(msg)
    assert m.content == "Hello world!"
    assert m.role == "assistant"

    # Mock return object from Anthropic().messages.create(stream=True)
    chunk = RawContentBlockDeltaEvent(
        delta=TextDelta(type="text_delta", text="Hello "),
        type="content_block_delta",
        index=0,
    )

    m = message_content_chunk(chunk)
    assert m.content == "Hello "
    assert m.role == "assistant"


def test_openai_normalization():
    import openai.types.chat.chat_completion as cc
    import openai.types.chat.chat_completion_chunk as ccc
    from openai import AsyncOpenAI, OpenAI
    from openai.resources.chat.completions import AsyncCompletions, Completions
    from openai.types.chat import (
        ChatCompletion,
        ChatCompletionChunk,
        ChatCompletionMessage,
    )

    # Make sure return type of OpenAI().chat.completions hasn't changed
    assert isinstance(OpenAI(api_key="fake").chat.completions, Completions)
    assert isinstance(
        AsyncOpenAI(api_key="fake").chat.completions, AsyncCompletions
    )

    assert (
        Completions.create.__annotations__["return"]
        == "ChatCompletion | Stream[ChatCompletionChunk]"
    )
    assert (
        AsyncCompletions.create.__annotations__["return"]
        == "ChatCompletion | AsyncStream[ChatCompletionChunk]"
    )

    # Mock return object from OpenAI().chat.completions.create()
    completion = ChatCompletion(
        id="foo",
        model="gpt-4",
        object="chat.completion",
        choices=[
            cc.Choice(
                finish_reason="stop",
                index=0,
                message=ChatCompletionMessage(
                    content="Hello world!",
                    role="assistant",
                ),
            )
        ],
        created=int(datetime.now().timestamp()),
    )

    m = message_content(completion)
    assert m.content == "Hello world!"
    assert m.role == "assistant"

    # Mock return object from OpenAI().chat.completions.create(stream=True)
    chunk = ChatCompletionChunk(
        id="foo",
        object="chat.completion.chunk",
        model="gpt-4o",
        created=int(datetime.now().timestamp()),
        choices=[
            ccc.Choice(
                index=0,
                delta=ccc.ChoiceDelta(
                    content="Hello ",
                    role="assistant",
                ),
            )
        ],
    )

    m = message_content_chunk(chunk)
    assert m.content == "Hello "
    assert m.role == "assistant"


def test_ollama_normalization():
    from ollama import ChatResponse
    from ollama import Message as OllamaMessage

    # Mock return object from ollama.chat()
    msg = ChatResponse(
        message=OllamaMessage(content="Hello world!", role="assistant"),
    )

    msg_dict = {"content": "Hello world!", "role": "assistant"}
    m = message_content(msg)
    assert m.content == msg_dict["content"]
    assert m.role == msg_dict["role"]

    m = message_content_chunk(msg)
    assert m.content == msg_dict["content"]
    assert m.role == msg_dict["role"]


# ------------------------------------------------------------------------------------
# Unit tests for as_provider_message()
#
# This is where we go from our ChatMessage to a provider's message object
#
# The general idea is to check that the provider's input message type match our
# expectations. If these tests fail, it doesn't not necessarily mean that our code is
# wrong (i.e., updating the test may be sufficient), but we'll still want to be aware
# and double-check our code.
# ------------------------------------------------------------------------------------


def test_stored_message_content_joins_segments():
    from shinychat._chat_types import StoredMessage, StoredSegment

    msg = StoredMessage(
        role="assistant",
        segments=[
            StoredSegment(content="a ", content_type="markdown"),
            StoredSegment(content="<b>b</b>", content_type="html"),
        ],
    )
    assert msg.content == "a <b>b</b>"


def test_stored_message_from_chat_message_makes_one_segment():
    from shinychat._chat_types import ChatMessage, StoredMessage

    sm = StoredMessage.from_chat_message(
        ChatMessage(content="hi", role="assistant")
    )
    assert len(sm.segments) == 1
    seg0 = sm.segments[0]
    assert isinstance(seg0, StoredSegment)
    assert seg0.content == "hi"
    assert seg0.content_type == "markdown"


def test_stored_message_from_chat_message_preserves_content_type():
    from htmltools import HTML
    from shinychat._chat_types import ChatMessage, StoredMessage

    html_msg = ChatMessage(content=HTML("<b>bold</b>"), role="assistant")
    sm_html = StoredMessage.from_chat_message(html_msg)
    assert isinstance(sm_html.segments[0], StoredSegment)
    assert sm_html.segments[0].content_type == "html"

    thinking_msg = ChatMessage(
        content="reasoning", role="assistant", content_type="thinking"
    )
    sm_thinking = StoredMessage.from_chat_message(thinking_msg)
    assert isinstance(sm_thinking.segments[0], StoredSegment)
    assert sm_thinking.segments[0].content_type == "thinking"


def test_slash_command_errors_on_duplicate_name():
    with session_context(test_session):
        chat = Chat(id="chat")
        chat.slash_command("greet", "Say hello", fn=lambda: None)
        with pytest.raises(ValueError, match="already registered"):
            chat.slash_command("greet", "Say hi", fn=lambda: None)


def test_slash_command_allows_overwrite_with_force():
    with session_context(test_session):
        chat = Chat(id="chat")
        chat.slash_command("greet", "Say hello", fn=lambda: None)
        chat.slash_command("greet", "Say hi", fn=lambda: None, force=True)
        with reactive.isolate():
            cmds = chat._slash_commands()
            assert cmds is not None
            assert cmds["greet"].definition["description"] == "Say hi"


def test_slash_command_remove():
    with session_context(test_session):
        chat = Chat(id="chat")
        remove = chat.slash_command("greet", "Say hello", fn=lambda: None)
        with reactive.isolate():
            cmds = chat._slash_commands()
            assert cmds is not None
            assert "greet" in cmds

        remove()
        with reactive.isolate():
            assert "greet" not in (chat._slash_commands() or {})

        # After removal, re-registering without force should succeed
        chat.slash_command("greet", "Say hello again", fn=lambda: None)
        with reactive.isolate():
            cmds = chat._slash_commands()
            assert cmds is not None
            assert cmds["greet"].definition["description"] == "Say hello again"


def test_slash_command_remove_by_name():
    with session_context(test_session):
        chat = Chat(id="chat")
        chat.slash_command("greet", "Say hello", fn=lambda: None)
        with reactive.isolate():
            cmds = chat._slash_commands()
            assert cmds is not None
            assert "greet" in cmds

        chat.remove_slash_command("greet")
        with reactive.isolate():
            assert "greet" not in (chat._slash_commands() or {})

        # Removing a non-existent command is a no-op
        chat.remove_slash_command("greet")


def test_slash_command_echo_defaults_to_handler_presence():
    with session_context(test_session):
        chat = Chat(id="chat")

        @chat.slash_command("withhandler", "Has a handler")
        async def _(): ...

        chat.slash_command("nohandler", "No handler", fn=None)

        with reactive.isolate():
            cmds = chat._slash_commands()
            assert cmds is not None
            assert cmds["withhandler"].definition["echo"] is True
            assert cmds["nohandler"].definition["echo"] is False
            assert cmds["nohandler"].handler is None


def test_slash_command_echo_explicit_override():
    with session_context(test_session):
        chat = Chat(id="chat")

        @chat.slash_command("sideeffect", "Side effect only", echo=False)
        async def _(): ...

        with reactive.isolate():
            cmds = chat._slash_commands()
            assert cmds is not None
            assert cmds["sideeffect"].definition["echo"] is False
            assert cmds["sideeffect"].handler is not None


def test_slash_command_fn_none_returns_remover():
    with session_context(test_session):
        chat = Chat(id="chat")

        remove = chat.slash_command("temp", "Temp", fn=None)
        with reactive.isolate():
            cmds = chat._slash_commands()
            assert cmds is not None
            assert "temp" in cmds
        remove()
        with reactive.isolate():
            assert "temp" not in (chat._slash_commands() or {})


def test_slash_command_fn_none_with_explicit_echo_true():
    with session_context(test_session):
        chat = Chat(id="chat")

        chat.slash_command(
            "clientecho", "Client-side but echoed", fn=None, echo=True
        )

        with reactive.isolate():
            cmds = chat._slash_commands()
            assert cmds is not None
            assert cmds["clientecho"].definition["echo"] is True
            assert cmds["clientecho"].handler is None


def test_bookmark_round_trips_echoed_slash_command():
    # An echoed slash command stores the `/cmd args` text as a normal user
    # message (mirroring `_on_slash_command`), so it rides the generic
    # stored-message bookmark mechanism: saved, then restored as a static entry.
    from shiny import reactive

    with session_context(test_session):
        chat = Chat(id="chat")
        chat._record_accepted_user_input(
            ChatMessage(content="/greet world", role="user")
        )
        run_async(lambda: chat.append_message("Hello! You said: world"))
        with reactive.isolate():
            saved = chat._messages_for_bookmark()

    assert saved == [
        {
            "role": "user",
            "segments": [
                {"content": "/greet world", "content_type": "markdown"}
            ],
        },
        {
            "role": "assistant",
            "segments": [
                {
                    "content": "Hello! You said: world",
                    "content_type": "markdown",
                }
            ],
        },
    ]

    async def restore() -> list[tuple[Role, str]]:
        with session_context(test_session):
            restored = Chat(id="chat_restored")
            sent: list[dict[str, Any]] = []

            async def _capture(action: Any, deps: Any = None) -> None:
                sent.append(action)

            restored._send_action = _capture  # type: ignore[method-assign]

            for message_dict in saved:
                await restored._restore_bookmark_message(message_dict)

            # `_restore_bookmark_message` re-sends each message to the client.
            return [
                (
                    cast(Role, a["message"]["role"]),
                    a["message"]["segments"][0]["content"],
                )
                for a in sent
                if a["type"] == "message"
            ]

    result: list[tuple[Role, str]] = []

    async def run() -> None:
        result.extend(await restore())

    run_async(run)

    assert result == [
        ("user", "/greet world"),
        ("assistant", "Hello! You said: world"),
    ]


def test_bookmark_omits_side_effect_only_slash_command():
    # A side-effect-only command (echo=False) never reports anything to the
    # client, so it never contributes to the bookmark even though its
    # handler runs.
    from shiny import reactive

    with session_context(test_session):
        chat = Chat(id="chat")
        chat.slash_command("note", "Side-effect only", echo=False)
        chat._record_accepted_user_input(
            ChatMessage(content="real message", role="user")
        )
        with reactive.isolate():
            saved = chat._messages_for_bookmark()

    assert saved == [
        {
            "role": "user",
            "segments": [
                {"content": "real message", "content_type": "markdown"}
            ],
        },
    ]


def test_restore_bookmark_message_warns_and_skips_malformed():
    # A malformed stored message (e.g. a bookmark written by an incompatible
    # shinychat version) must not abort the whole restore loop -- letting it
    # raise would hit Shiny's generic on_restore error handling, which shows
    # a banner and silently drops every message after the bad one.
    with session_context(test_session):
        chat = Chat(id="chat_restore_malformed")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        chat._send_action = _capture  # type: ignore[method-assign]

        saved: list[Any] = [
            {
                "role": "user",
                "segments": [{"content": "before", "content_type": "markdown"}],
            },
            {"role": "user"},  # missing required `segments`
            {
                "role": "assistant",
                "segments": [{"content": "after", "content_type": "markdown"}],
            },
        ]

        async def _exercise() -> None:
            with pytest.warns(
                UserWarning, match="incompatible shinychat version"
            ):
                for message_dict in saved:
                    await chat._restore_bookmark_message(message_dict)

        run_async(_exercise)

    contents = [
        a["message"]["segments"][0]["content"]
        for a in sent
        if a["type"] == "message"
    ]
    assert contents == ["before", "after"]


def test_restore_bookmark_message_warning_omits_the_offending_value():
    # pydantic's default ValidationError string embeds the invalid input
    # value, which for a chat message is arbitrary (and possibly sensitive)
    # content -- the warning must not repeat it.
    with session_context(test_session):
        chat = Chat(id="chat_restore_malformed_no_leak")
        secret = "sk-super-secret-token-do-not-log-me"

        async def _exercise() -> None:
            with pytest.warns(UserWarning) as record:
                # The invalid *value* here is the secret itself: content_type
                # only accepts a fixed set of literals, so a bogus string
                # fails validation with that string as the reported input.
                await chat._restore_bookmark_message(
                    {
                        "role": "user",
                        "segments": [{"content": "hi", "content_type": secret}],
                    }
                )
            assert secret not in str(record[0].message)

        run_async(_exercise)


def test_user_input_reads_latest_stored():
    from shiny import reactive
    from shinychat._chat import UserInput

    session = cast(Session, _MockSession())

    with session_context(session):
        chat = Chat(id="chat")

        with reactive.isolate():
            assert chat.user_input() is None

            from shinychat._attachments import Attachment
            from shinychat._chat_types import ChatMessage, StoredMessage

            attachments = [
                Attachment(
                    mime="image/png",
                    data_url="data:image/png;base64,AAA",
                    name="a.png",
                )
            ]
            stored = StoredMessage.from_chat_message(
                ChatMessage(content="hi", role="user", attachments=attachments)
            )
            chat._latest_user_input.set(stored)
            result = chat.user_input()
            assert result == UserInput(text="hi", attachments=attachments)
            assert result is not None
            text, atts = result
            assert text == "hi"
            assert atts == attachments


def test_chat_ui_allow_attachments_attribute():
    from shinychat import chat_ui

    def attachment_attr(ui_tag: object) -> object:
        return ui_tag.attrs.get("allow-attachments")  # type: ignore[attr-defined]

    assert attachment_attr(chat_ui("c", allow_attachments=MISSING)) is None
    assert attachment_attr(chat_ui("c", allow_attachments=True)) == "true"
    assert attachment_attr(chat_ui("c", allow_attachments=False)) == "false"


def test_chat_ui_accept_list_and_max_attachment_size(
    monkeypatch: pytest.MonkeyPatch,
):
    from shinychat import chat_ui

    monkeypatch.setenv("SHINYCHAT_MAX_ATTACHMENT_SIZE", "5000000")
    tag = chat_ui("c", allow_attachments=["application/pdf"])
    assert tag.attrs.get("allow-attachments") == "true"
    assert tag.attrs.get("attachment-accept") == "application/pdf"
    assert tag.attrs.get("max-attachment-size") == "5000000"

    with pytest.raises(ValueError):
        chat_ui("c", allow_attachments=["application/msword"])


def test_user_submit_function_union_includes_two_arg_form():
    from typing import get_args

    from shinychat._chat import UserSubmitFunction, UserSubmitFunction2

    two_arg_forms = get_args(UserSubmitFunction2)
    top_level_forms = get_args(UserSubmitFunction)
    assert all(form in top_level_forms for form in two_arg_forms)


class MyObject:
    content = "Hello world!"


class MyObjectChunk:
    content = "Hello world!"


@message_content.register
def _(message: MyObject) -> ChatMessage:
    return ChatMessage(content=message.content, role="assistant")


@message_content_chunk.register
def _(chunk: MyObjectChunk) -> ChatMessage:
    return ChatMessage(content=chunk.content, role="assistant")


def test_custom_objects():
    obj = MyObject()
    m = message_content(obj)
    assert m.content == "Hello world!"
    assert m.role == "assistant"

    chunk = MyObjectChunk()
    m = message_content_chunk(chunk)
    assert m.content == "Hello world!"
    assert m.role == "assistant"


def test_stream_thinking_creates_thinking_segment():
    with session_context(test_session):
        chat = Chat(id="chat")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append({"action": action, "deps": deps})

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _exercise() -> None:
            await chat._append_message_chunk("", chunk="start", stream_id="s1")
            await chat._append_message_chunk(
                ChatMessage(
                    content="reasoning",
                    role="assistant",
                    content_type="thinking",
                ),
                chunk=True,
                stream_id="s1",
            )
            await chat._append_message_chunk(
                "answer", chunk=True, stream_id="s1"
            )
            await chat._append_message_chunk("", chunk="end", stream_id="s1")

        run_async(_exercise)

        # Each chunk is sent individually on the wire; the client assembles
        # segments from the (content, content_type) pairs of each chunk.
        chunk_actions = [
            s["action"] for s in sent if s["action"]["type"] == "chunk"
        ]
        by_content = {a["content"]: a["content_type"] for a in chunk_actions}
        assert by_content["reasoning"] == "thinking"
        assert by_content["answer"] == "markdown"
        assert [
            (segment.content, segment.content_type)
            for segment in chat._transcript.read()[0].message.segments
        ] == [("reasoning", "thinking"), ("answer", "markdown")]


def test_message_stream_context_rejects_complete_appends():
    with session_context(test_session):
        chat = Chat(id="chat")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _exercise() -> None:
            async with chat.message_stream_context() as stream:
                await stream.append("streamed")
                with pytest.raises(
                    RuntimeError, match="complete message.*stream is active"
                ):
                    await chat.append_message("rejected")

        run_async(_exercise)

        assert [entry.message.content for entry in chat._transcript.read()] == [
            "streamed"
        ]


def test_nested_message_stream_context_restores_outer_checkpoint():
    with session_context(test_session):
        chat = Chat(id="nested_stream", history=False)

        async def _exercise() -> None:
            async with chat.message_stream_context() as outer:
                await outer.append("prefix")
                async with chat.message_stream_context() as inner:
                    await inner.append(" draft")
                    await inner.replace(" final")
                await outer.append(" done")

        run_async(_exercise)

    assert [entry.message.content for entry in chat._transcript.read()] == [
        "prefix final done"
    ]


def test_stream_preserves_sent_partial_on_chunk_failure():
    with session_context(test_session):
        chat = Chat(id="partial_error", history=False)
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)
            if action.get("type") == "chunk" and action["content"] == "lost":
                raise RuntimeError("chunk send failed")

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _stream():
            yield "kept"
            yield "lost"

        with pytest.raises(RuntimeError, match="chunk send failed"):
            run_async(lambda: chat._append_message_stream(_stream()))

    entry = chat._transcript.read()[0]
    assert entry.message.content == "kept"
    assert entry.status == "error"
    assert entry.error == {"message": "chunk send failed"}
    assert chat.messages() == (
        {
            "content": "kept",
            "role": "assistant",
            "status": "error",
            "error": {"message": "chunk send failed"},
        },
    )
    assert sent[-1] == {"type": "chunk_end"}


def test_stream_start_send_failure_does_not_commit():
    with session_context(test_session):
        chat = Chat(id="start_error", history=False)

        async def _fail(action: Any, deps: Any = None) -> None:
            if action.get("type") == "chunk_start":
                raise RuntimeError("start send failed")

        chat._send_action = _fail  # type: ignore[method-assign]

        async def _stream():
            yield "not sent"

        with pytest.raises(RuntimeError, match="start send failed"):
            run_async(lambda: chat._append_message_stream(_stream()))

    assert chat._transcript.read() == ()
    assert chat._transcript.active_stream_id is None


def test_stream_start_persistence_failure_closes_sent_stream():
    with session_context(test_session):
        chat = Chat(id="start_persistence_error", history=False)
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        async def _fail_started(
            _stream_id: str, _exchange_id: str | None, _entry: Any
        ) -> None:
            raise RuntimeError("start persistence failed")

        chat._send_action = _capture  # type: ignore[method-assign]
        chat._transcript.set_capture_callbacks(
            on_accepted_input=None,
            on_message_committed=None,
            on_stream_started=_fail_started,
            on_stream_updated=None,
            on_stream_finished=None,
        )

        async def _stream():
            yield "not reached"

        with pytest.raises(RuntimeError, match="start persistence failed"):
            run_async(lambda: chat._append_message_stream(_stream()))

    entry = chat._transcript.read()[0]
    assert entry.status == "error"
    assert entry.error == {"message": "start persistence failed"}
    assert chat._transcript.active_stream_id is None
    assert sent[-1] == {"type": "chunk_end"}


def test_stream_finish_persistence_failure_preserves_the_callback_error():
    with session_context(test_session):
        chat = Chat(id="finish_persistence_error", history=False)
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        async def _fail_finished(
            _stream_id: str, _status: str, _error: str | None
        ) -> None:
            raise RuntimeError("finish persistence failed")

        chat._send_action = _capture  # type: ignore[method-assign]
        chat._transcript.set_capture_callbacks(
            on_accepted_input=None,
            on_message_committed=None,
            on_stream_started=None,
            on_stream_updated=None,
            on_stream_finished=_fail_finished,
        )

        async def _stream():
            yield "kept"

        with pytest.raises(RuntimeError, match="finish persistence failed"):
            run_async(lambda: chat._append_message_stream(_stream()))

    assert chat._transcript.read()[0].message.content == "kept"
    assert chat._transcript.active_stream_id is None
    assert [action["type"] for action in sent].count("chunk_end") == 1


def test_stream_preserves_sent_partial_when_terminal_send_fails():
    with session_context(test_session):
        chat = Chat(id="terminal_error", history=False)

        async def _capture(action: Any, deps: Any = None) -> None:
            if action.get("type") == "chunk_end":
                raise RuntimeError("end send failed")

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _stream():
            yield "kept"

        with pytest.raises(RuntimeError, match="end send failed"):
            run_async(lambda: chat._append_message_stream(_stream()))

    entry = chat._transcript.read()[0]
    assert entry.message.content == "kept"
    assert entry.status == "error"
    assert entry.error == {"message": "end send failed"}
    assert chat._transcript.active_stream_id is None


def test_stream_commits_final_transformed_content_before_chunk_end_failure():
    with session_context(test_session):
        chat = Chat(id="terminal_transformed_error", history=False)

        async def _capture(action: Any, deps: Any = None) -> None:
            if action.get("type") == "chunk_end":
                raise RuntimeError("end send failed")

        async def _transform(content: str, chunk: str, done: bool) -> str:
            return f"{content} final" if done else content

        chat._send_action = _capture  # type: ignore[method-assign]
        chat._transform_assistant = _transform

        async def _stream():
            yield "partial"

        with pytest.raises(RuntimeError, match="end send failed"):
            run_async(lambda: chat._append_message_stream(_stream()))

    entry = chat._transcript.read()[0]
    assert entry.message.content == "partial final"
    assert entry.status == "error"
    assert entry.error == {"message": "end send failed"}


def test_stream_transform_error_best_effort_closes_the_wire_and_owner():
    with session_context(test_session):
        chat = Chat(id="terminal_transform_error", history=False)
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        async def _transform(content: str, chunk: str, done: bool) -> str:
            if done:
                raise RuntimeError("terminal transform failed")
            return content

        chat._send_action = _capture  # type: ignore[method-assign]
        chat._transform_assistant = _transform

        async def _stream():
            yield "kept"

        with pytest.raises(RuntimeError, match="terminal transform failed"):
            run_async(lambda: chat._append_message_stream(_stream()))

    entry = chat._transcript.read()[0]
    assert entry.message.content == "kept"
    assert entry.status == "error"
    assert entry.error == {"message": "terminal transform failed"}
    assert chat._transcript.active_stream_id is None
    assert sent[-1] == {"type": "chunk_end"}


def test_stream_generator_error_survives_terminal_cleanup_failure():
    with session_context(test_session):
        chat = Chat(id="generator_error_cleanup_failure", history=False)

        async def _capture(action: Any, deps: Any = None) -> None:
            if action.get("type") == "chunk_end":
                raise RuntimeError("terminal cleanup failed")

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _stream():
            yield "kept"
            raise RuntimeError("generator failed")

        with pytest.raises(RuntimeError, match="generator failed"):
            run_async(lambda: chat._append_message_stream(_stream()))

    entry = chat._transcript.read()[0]
    assert entry.message.content == "kept"
    assert entry.status == "error"
    assert entry.error == {"message": "generator failed"}
    assert chat._transcript.active_stream_id is None


def test_stream_generator_empty_error_survives_terminal_cleanup_failure():
    with session_context(test_session):
        chat = Chat(id="generator_empty_error_cleanup_failure", history=False)

        async def _capture(action: Any, deps: Any = None) -> None:
            if action.get("type") == "chunk_end":
                raise RuntimeError("terminal cleanup failed")

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _stream():
            yield "kept"
            raise RuntimeError("")

        with pytest.raises(RuntimeError, match="^$"):
            run_async(lambda: chat._append_message_stream(_stream()))

    entry = chat._transcript.read()[0]
    assert entry.message.content == "kept"
    assert entry.status == "error"
    assert entry.error == {"message": ""}
    assert chat._transcript.active_stream_id is None


def test_stream_generator_cancellation_survives_terminal_cleanup_failure():
    with session_context(test_session):
        chat = Chat(id="generator_cancel_cleanup_failure", history=False)

        async def _capture(action: Any, deps: Any = None) -> None:
            if action.get("type") == "chunk_end":
                raise RuntimeError("terminal cleanup failed")

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _stream():
            yield "kept"
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            run_async(lambda: chat._append_message_stream(_stream()))

    entry = chat._transcript.read()[0]
    assert entry.message.content == "kept"
    assert entry.status == "cancelled"
    assert entry.error is None
    assert chat._transcript.active_stream_id is None


def test_stream_terminal_cancellation_aborts_without_error():
    with session_context(test_session):
        chat = Chat(id="stream_terminal_cancelled", history=False)

        async def _capture(action: Any, deps: Any = None) -> None:
            if action.get("type") == "chunk_end":
                raise asyncio.CancelledError()

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _stream():
            yield "kept"

        with pytest.raises(asyncio.CancelledError):
            run_async(lambda: chat._append_message_stream(_stream()))

    entry = chat._transcript.read()[0]
    assert entry.message.content == "kept"
    assert entry.status == "cancelled"
    assert entry.error is None
    assert chat._transcript.active_stream_id is None


def test_stream_context_error_survives_terminal_cleanup_failure():
    with session_context(test_session):
        chat = Chat(id="context_error_cleanup_failure", history=False)

        async def _capture(action: Any, deps: Any = None) -> None:
            if action.get("type") == "chunk_end":
                raise RuntimeError("terminal cleanup failed")

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _exercise() -> None:
            async with chat.message_stream_context() as stream:
                await stream.append("kept")
                raise RuntimeError("body failed")

        with pytest.raises(RuntimeError, match="body failed"):
            run_async(_exercise)

    entry = chat._transcript.read()[0]
    assert entry.message.content == "kept"
    assert entry.status == "error"
    assert entry.error == {"message": "body failed"}
    assert chat._transcript.active_stream_id is None


def test_stream_context_empty_error_survives_terminal_cleanup_failure():
    with session_context(test_session):
        chat = Chat(id="context_empty_error_cleanup_failure", history=False)

        async def _capture(action: Any, deps: Any = None) -> None:
            if action.get("type") == "chunk_end":
                raise RuntimeError("terminal cleanup failed")

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _exercise() -> None:
            async with chat.message_stream_context() as stream:
                await stream.append("kept")
                raise RuntimeError("")

        with pytest.raises(RuntimeError, match="^$"):
            run_async(_exercise)

    entry = chat._transcript.read()[0]
    assert entry.message.content == "kept"
    assert entry.status == "error"
    assert entry.error == {"message": ""}
    assert chat._transcript.active_stream_id is None


def test_stream_context_cancellation_survives_terminal_cleanup_failure():
    with session_context(test_session):
        chat = Chat(id="context_cancel_cleanup_failure", history=False)

        async def _capture(action: Any, deps: Any = None) -> None:
            if action.get("type") == "chunk_end":
                raise RuntimeError("terminal cleanup failed")

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _exercise() -> None:
            async with chat.message_stream_context() as stream:
                await stream.append("kept")
                raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            run_async(_exercise)

    entry = chat._transcript.read()[0]
    assert entry.message.content == "kept"
    assert entry.status == "cancelled"
    assert entry.error is None
    assert chat._transcript.active_stream_id is None


def test_stream_context_terminal_cancellation_aborts_without_error():
    with session_context(test_session):
        chat = Chat(id="context_terminal_cancelled", history=False)

        async def _capture(action: Any, deps: Any = None) -> None:
            if action.get("type") == "chunk_end":
                raise asyncio.CancelledError()

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _exercise() -> None:
            async with chat.message_stream_context() as stream:
                await stream.append("kept")

        with pytest.raises(asyncio.CancelledError):
            run_async(_exercise)

    entry = chat._transcript.read()[0]
    assert entry.message.content == "kept"
    assert entry.status == "cancelled"
    assert entry.error is None
    assert chat._transcript.active_stream_id is None


def test_stream_final_display_error_best_effort_closes_the_wire_and_owner():
    with session_context(test_session):
        chat = Chat(id="terminal_display_error", history=False)
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)
            if (
                action.get("type") == "chunk"
                and action["content"] == "kept final"
            ):
                raise RuntimeError("terminal display failed")

        async def _transform(content: str, chunk: str, done: bool) -> str:
            return f"{content} final" if done else content

        chat._send_action = _capture  # type: ignore[method-assign]
        chat._transform_assistant = _transform

        async def _stream():
            yield "kept"

        with pytest.raises(RuntimeError, match="terminal display failed"):
            run_async(lambda: chat._append_message_stream(_stream()))

    entry = chat._transcript.read()[0]
    assert entry.message.content == "kept"
    assert entry.status == "error"
    assert entry.error == {"message": "terminal display failed"}
    assert chat._transcript.active_stream_id is None
    assert sent[-1] == {"type": "chunk_end"}


def test_stream_suppressed_terminal_transform_closes_and_preserves_content():
    with session_context(test_session):
        chat = Chat(id="suppressed_terminal", history=False)
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        async def _transform(
            content: str, chunk: str, done: bool
        ) -> str | None:
            return None if done else content

        chat._send_action = _capture  # type: ignore[method-assign]
        chat._transform_assistant = _transform

        async def _stream():
            yield "kept"

        run_async(lambda: chat._append_message_stream(_stream()))

    entry = chat._transcript.read()[0]
    assert entry.message.content == "kept"
    assert entry.status is None
    assert chat._transcript.active_stream_id is None
    assert sent[-1] == {"type": "chunk_end"}


def test_suppressed_chunk_commits_source_without_mutating_display():
    with session_context(test_session):
        chat = Chat(id="suppressed_chunk", history=False)

        async def _transform(
            content: str, chunk: str, done: bool
        ) -> str | None:
            return None if chunk == "hidden" else content

        chat._transform_assistant = _transform

        async def _stream():
            yield "hidden"
            yield "shown"

        run_async(lambda: chat._append_message_stream(_stream()))

    assert chat._transcript.read()[0].message.content == "hiddenshown"


def test_transformed_replacement_keeps_dependencies_from_suppressed_chunks():
    with session_context(test_session):
        chat = Chat(id="suppressed_chunk_dependencies", history=False)
        hidden_dep = HTMLDependency(name="hidden", version="1.0")
        visible_dep = HTMLDependency(name="visible", version="1.0")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append({"action": action, "deps": deps})

        async def _transform(
            content: str, chunk: str, done: bool
        ) -> str | None:
            return None if chunk == "hidden" else content.upper()

        chat._send_action = _capture  # type: ignore[method-assign]
        chat._transform_assistant = _transform
        chat._serialize_html_deps = lambda deps: (  # type: ignore[method-assign]
            [{"name": dep.name, "version": str(dep.version)} for dep in deps]
            if deps
            else None
        )

        async def _stream():
            hidden = ChatMessage(content="hidden", role="assistant")
            hidden.html_deps = [hidden_dep]
            yield hidden
            visible = ChatMessage(content="shown", role="assistant")
            visible.html_deps = [visible_dep]
            yield visible

        run_async(lambda: chat._append_message_stream(_stream()))

    expected_deps = [
        {"name": "hidden", "version": "1.0"},
        {"name": "visible", "version": "1.0"},
    ]
    entry = chat._transcript.read()[0]
    assert entry.message.content == "HIDDENSHOWN"
    assert entry.message.html_deps == expected_deps
    visible_chunk = next(
        item
        for item in sent
        if item["action"].get("type") == "chunk"
        and item["action"]["content"] == "HIDDENSHOWN"
    )
    assert visible_chunk["deps"] == expected_deps


def test_terminal_transformed_replacement_keeps_suppressed_dependencies():
    with session_context(test_session):
        chat = Chat(id="terminal_suppressed_dependencies", history=False)
        hidden_dep = HTMLDependency(name="hidden", version="1.0")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append({"action": action, "deps": deps})

        async def _transform(
            content: str, chunk: str, done: bool
        ) -> str | None:
            if chunk == "hidden":
                return None
            return f"{content} final" if done else content.upper()

        chat._send_action = _capture  # type: ignore[method-assign]
        chat._transform_assistant = _transform
        chat._serialize_html_deps = lambda deps: (  # type: ignore[method-assign]
            [{"name": dep.name, "version": str(dep.version)} for dep in deps]
            if deps
            else None
        )

        async def _stream():
            hidden = ChatMessage(content="hidden", role="assistant")
            hidden.html_deps = [hidden_dep]
            yield hidden

        run_async(lambda: chat._append_message_stream(_stream()))

    expected_deps = [{"name": "hidden", "version": "1.0"}]
    entry = chat._transcript.read()[0]
    assert entry.message.content == "hidden final"
    assert entry.message.html_deps == expected_deps
    final_chunk = next(
        item
        for item in sent
        if item["action"].get("type") == "chunk"
        and item["action"]["content"] == "hidden final"
    )
    assert final_chunk["deps"] == expected_deps


def test_suppressed_terminal_transform_surfaces_end_send_failure():
    with session_context(test_session):
        chat = Chat(id="suppressed_terminal_error", history=False)

        async def _capture(action: Any, deps: Any = None) -> None:
            if action.get("type") == "chunk_end":
                raise RuntimeError("end send failed")

        async def _transform(
            content: str, chunk: str, done: bool
        ) -> str | None:
            return None if done else content

        chat._send_action = _capture  # type: ignore[method-assign]
        chat._transform_assistant = _transform

        async def _stream():
            yield "kept"

        with pytest.raises(RuntimeError, match="end send failed"):
            run_async(lambda: chat._append_message_stream(_stream()))

    entry = chat._transcript.read()[0]
    assert entry.message.content == "kept"
    assert entry.status == "error"
    assert entry.error == {"message": "end send failed"}
    assert chat._transcript.active_stream_id is None


def test_stream_cancellation_preserves_sent_partial():
    with session_context(test_session):
        chat = Chat(id="partial_cancelled", history=False)

        async def _stream():
            yield "kept"
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            run_async(lambda: chat._append_message_stream(_stream()))

    entry = chat._transcript.read()[0]
    assert entry.message.content == "kept"
    assert entry.status == "cancelled"
    assert entry.error is None


def test_stream_captures_exchange_before_newer_input():
    with session_context(test_session):
        chat = Chat(id="stream_exchange", history=False)
        chat._record_accepted_user_input(
            ChatMessage(content="old request", role="user")
        )
        old_exchange = chat._transcript.open_exchange_id

        async def _exercise() -> None:
            await chat._append_message_chunk(
                "", chunk="start", stream_id="old-stream"
            )
            chat._record_accepted_user_input(
                ChatMessage(content="new request", role="user")
            )
            await chat._append_message_chunk(
                "old response", chunk=True, stream_id="old-stream"
            )
            await chat._append_message_chunk(
                "", chunk="end", stream_id="old-stream"
            )

        run_async(_exercise)

    stream_entry = chat._transcript.read()[1]
    assert stream_entry.exchange_id == old_exchange
    assert chat._transcript.open_exchange_id != old_exchange
    assert stream_entry.message.content == "old response"


def test_complete_append_captures_exchange_before_async_transform():
    with session_context(test_session):
        chat = Chat(id="complete_transform_exchange", history=False)
        chat._record_accepted_user_input(
            ChatMessage(content="old request", role="user")
        )
        old_exchange = chat._transcript.open_exchange_id
        transform_started = asyncio.Event()
        release_transform = asyncio.Event()

        async def _transform(content: str, chunk: str, done: bool) -> str:
            transform_started.set()
            await release_transform.wait()
            return content

        chat._transform_assistant = _transform

        async def _exercise() -> None:
            append = asyncio.create_task(chat.append_message("old response"))
            await transform_started.wait()
            chat._record_accepted_user_input(
                ChatMessage(content="new request", role="user")
            )
            release_transform.set()
            await append

        run_async(_exercise)

    assert chat._transcript.read()[-1].exchange_id == old_exchange
    assert chat._transcript.open_exchange_id != old_exchange


def test_stream_start_captures_exchange_before_async_transform():
    with session_context(test_session):
        chat = Chat(id="stream_transform_exchange", history=False)
        chat._record_accepted_user_input(
            ChatMessage(content="old request", role="user")
        )
        old_exchange = chat._transcript.open_exchange_id
        transform_started = asyncio.Event()
        release_transform = asyncio.Event()

        async def _transform(content: str, chunk: str, done: bool) -> str:
            transform_started.set()
            await release_transform.wait()
            return content

        chat._transform_assistant = _transform

        async def _exercise() -> None:
            start = asyncio.create_task(
                chat._append_message_chunk(
                    "", chunk="start", stream_id="old-stream"
                )
            )
            await transform_started.wait()
            chat._record_accepted_user_input(
                ChatMessage(content="new request", role="user")
            )
            release_transform.set()
            await start
            await chat._append_message_chunk(
                "", chunk="end", stream_id="old-stream"
            )

        run_async(_exercise)

    assert chat._transcript.read()[-1].exchange_id == old_exchange
    assert chat._transcript.open_exchange_id != old_exchange


def test_complete_append_reserves_admission_before_async_transform():
    with session_context(test_session):
        chat = Chat(id="complete_transform_admission", history=False)
        transform_started = asyncio.Event()
        release_transform = asyncio.Event()

        async def _transform(content: str, chunk: str, done: bool) -> str:
            transform_started.set()
            await release_transform.wait()
            return content

        chat._transform_assistant = _transform

        async def _exercise() -> None:
            append = asyncio.create_task(chat.append_message("complete"))
            await transform_started.wait()
            with pytest.raises(
                RuntimeError, match="another transcript operation"
            ):
                await chat._append_message_chunk(
                    "", chunk="start", stream_id="blocked"
                )
            release_transform.set()
            await append

        run_async(_exercise)

    assert [entry.message.content for entry in chat._transcript.read()] == [
        "complete"
    ]


def test_stream_start_reserves_admission_before_async_transform():
    with session_context(test_session):
        chat = Chat(id="stream_transform_admission", history=False)
        transform_started = asyncio.Event()
        release_transform = asyncio.Event()

        async def _transform(content: str, chunk: str, done: bool) -> str:
            transform_started.set()
            await release_transform.wait()
            return content

        chat._transform_assistant = _transform

        async def _exercise() -> None:
            start = asyncio.create_task(
                chat._append_message_chunk(
                    "", chunk="start", stream_id="reserved"
                )
            )
            await transform_started.wait()
            with pytest.raises(
                RuntimeError, match="another transcript operation"
            ):
                await chat.append_message("blocked")
            release_transform.set()
            await start
            await chat._append_message_chunk(
                "", chunk="end", stream_id="reserved"
            )

        run_async(_exercise)

    assert [entry.message.content for entry in chat._transcript.read()] == [""]


def test_clear_greeting_waits_for_successful_transport():
    with session_context(test_session):
        chat = Chat(id="clear_greeting_failure", history=False)
        chat._greeting_content = "welcome"

        async def _fail(action: Any, deps: Any = None) -> None:
            raise RuntimeError("clear failed")

        chat._send_action = _fail  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="clear failed"):
            run_async(lambda: chat.clear_messages(greeting=True))

    assert chat.get_greeting() == "welcome"


def test_second_root_stream_is_rejected():
    with session_context(test_session):
        chat = Chat(id="second_stream", history=False)

        async def _exercise() -> None:
            await chat._append_message_chunk("", chunk="start", stream_id="one")
            with pytest.raises(RuntimeError, match="second message stream"):
                await chat._append_message_chunk(
                    "", chunk="start", stream_id="two"
                )
            await chat._append_message_chunk("", chunk="end", stream_id="one")

        run_async(_exercise)


def test_clear_and_restore_reject_an_active_stream_without_invalidating_it():
    with session_context(test_session):
        chat = Chat(id="clear_during_stream", history=False)

        async def _exercise() -> None:
            await chat._append_message_chunk(
                "", chunk="start", stream_id="stream"
            )
            with pytest.raises(RuntimeError, match="clear or restore"):
                await chat.clear_messages()
            with pytest.raises(RuntimeError, match="clear or restore"):
                await chat._restore_bookmark_message(
                    {
                        "role": "assistant",
                        "segments": [
                            {
                                "content": "restored",
                                "content_type": "markdown",
                            }
                        ],
                    }
                )
            await chat._append_message_chunk(
                "still active", chunk=True, stream_id="stream"
            )
            await chat._append_message_chunk(
                "", chunk="end", stream_id="stream"
            )

        run_async(_exercise)

    assert [entry.message.content for entry in chat._transcript.read()] == [
        "still active"
    ]


def test_thinking_stream_stores_segment_not_tags():
    with session_context(test_session):
        chat = Chat(id="chat")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append({"action": action, "deps": deps})

        chat._send_action = _capture  # type: ignore[method-assign]

        async def gen():
            yield ChatMessage(
                content="thinking hard",
                role="assistant",
                content_type="thinking",
            )
            yield "the answer"

        async def _exercise() -> None:
            await chat.append_message_stream(gen())

        run_async(_exercise)

        # The thinking chunk must travel as bare content paired with
        # content_type="thinking" -- not wrapped in literal <thinking> tags.
        chunk_actions = [
            s["action"] for s in sent if s["action"]["type"] == "chunk"
        ]
        thinking_actions = [
            a for a in chunk_actions if a["content_type"] == "thinking"
        ]
        assert len(thinking_actions) == 1
        assert thinking_actions[0]["content"] == "thinking hard"
        assert all("<thinking>" not in a["content"] for a in chunk_actions)


def test_send_message_payload_has_segments_with_thinking():
    with session_context(test_session):
        chat = Chat(id="chat")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        chat._send_action = _capture  # type: ignore[method-assign]
        stored = StoredMessage(
            role="assistant",
            segments=[
                StoredSegment(content="reasoning", content_type="thinking"),
                StoredSegment(content="answer", content_type="markdown"),
            ],
        )

        async def _exercise() -> None:
            await chat._send_append_message(stored)

        run_async(_exercise)
        assert sent[0]["type"] == "message"
        assert sent[0]["message"]["segments"] == [
            {"content": "reasoning", "content_type": "thinking"},
            {"content": "answer", "content_type": "markdown"},
        ]


def test_bookmark_roundtrip_thinking_segment():
    from shiny import reactive

    with session_context(test_session):
        chat = Chat(id="chat")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        chat._send_action = _capture  # type: ignore[method-assign]
        stored = StoredMessage(
            role="assistant",
            segments=[
                StoredSegment(content="reasoning", content_type="thinking"),
                StoredSegment(content="answer", content_type="markdown"),
            ],
        )
        run_async(
            lambda: chat._restore_bookmark_message(
                stored.model_dump(exclude_none=True)
            )
        )
        with reactive.isolate():
            saved = chat._messages_for_bookmark()
        assert saved[0]["segments"][0]["content_type"] == "thinking"

        async def _exercise() -> None:
            await chat._restore_bookmark_message(saved[0])

        run_async(_exercise)
        assert sent[0]["type"] == "message"
        assert sent[0]["message"]["segments"][0]["content_type"] == "thinking"


def test_send_append_message_serializes_attachments():
    """Attachments in the outgoing payload must be plain dicts, not Attachment objects.

    json.dumps (used by Shiny's send_custom_message) cannot serialize Pydantic
    models, so _send_append_message must call model_dump() before building the
    wire payload.
    """
    import json

    from shinychat._attachments import Attachment

    with session_context(test_session):
        chat = Chat(id="chat")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        chat._send_action = _capture  # type: ignore[method-assign]

        att = Attachment.from_data(
            b"hello", mime="text/plain", name="hello.txt"
        )
        stored = StoredMessage(
            role="assistant",
            segments=[
                StoredSegment(content="here you go", content_type="markdown")
            ],
            attachments=[att],
        )

        run_async(lambda: chat._send_append_message(stored))

        payload = sent[0]["message"]
        # Must not raise — the payload must be JSON-serializable.
        json.dumps(payload)

        # Attachments must arrive as plain dicts with the expected keys.
        assert payload["attachments"] == [
            {
                "mime": "text/plain",
                "name": "hello.txt",
                "size": 5,
                "data_url": att.data_url,
            }
        ]


def test_stored_message_content_wraps_thinking_in_tags():
    from shinychat._chat_types import StoredMessage, StoredSegment

    msg = StoredMessage(
        role="assistant",
        segments=[
            StoredSegment(content="reasoning", content_type="thinking"),
            StoredSegment(content="the answer", content_type="markdown"),
        ],
    )
    assert msg.content == "<thinking>\nreasoning\n</thinking>\n\nthe answer"


def test_append_message_stream_return_includes_tagged_thinking():
    # The single-string return value must agree with StoredMessage.content:
    # thinking is included, wrapped in <thinking> tags.
    from shinychat._chat_types import ChatMessage

    with session_context(test_session):
        chat = Chat(id="chat")

        async def _noop_send(*a: object, **k: object) -> None:
            return None

        chat._send_action = _noop_send  # type: ignore[method-assign]

        async def gen():
            yield ChatMessage(
                content="reasoning", role="assistant", content_type="thinking"
            )
            yield "the answer"

        result: list[str] = []

        async def _exercise() -> None:
            result.append(await chat._append_message_stream(gen()))

        run_async(_exercise)
        assert result[0] == "<thinking>\nreasoning\n</thinking>\n\nthe answer"


def test_streaming_thinking_chunk_wire_content_not_empty():
    """Regression: a streamed thinking chunk must carry its text on the wire.

    The streaming chunk action's `content` must include the thinking text or the
    client renders an empty thinking panel.
    """
    from shinychat._chat_types import ChatMessage

    with session_context(test_session):
        chat = Chat(id="chat")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _exercise() -> None:
            await chat._append_message_chunk("", chunk="start", stream_id="s1")
            await chat._append_message_chunk(
                ChatMessage(
                    content="reasoning",
                    role="assistant",
                    content_type="thinking",
                ),
                chunk=True,
                stream_id="s1",
            )
            await chat._append_message_chunk("", chunk="end", stream_id="s1")

        run_async(_exercise)

        thinking_chunks = [
            a
            for a in sent
            if a.get("type") == "chunk" and a.get("content_type") == "thinking"
        ]
        assert thinking_chunks, "no thinking chunk action was sent"
        assert thinking_chunks[0]["content"] == "reasoning"


def test_streaming_chunk_content_type_follows_segment():
    """Each streamed chunk action carries the content_type of its own segment.

    Pins the wire content_type derivation across a mixed thinking->markdown
    stream so it stays correct after _send_append_message infers the type
    from the message segments rather than an explicitly threaded argument.
    """
    from shinychat._chat_types import ChatMessage

    with session_context(test_session):
        chat = Chat(id="chat")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _exercise() -> None:
            await chat._append_message_chunk("", chunk="start", stream_id="s1")
            await chat._append_message_chunk(
                ChatMessage(
                    content="reasoning",
                    role="assistant",
                    content_type="thinking",
                ),
                chunk=True,
                stream_id="s1",
            )
            await chat._append_message_chunk(
                ChatMessage(
                    content="answer", role="assistant", content_type="markdown"
                ),
                chunk=True,
                stream_id="s1",
            )
            await chat._append_message_chunk("", chunk="end", stream_id="s1")

        run_async(_exercise)

        chunk_types = [
            (a["content"], a["content_type"])
            for a in sent
            if a.get("type") == "chunk"
        ]
        assert ("reasoning", "thinking") in chunk_types
        assert ("answer", "markdown") in chunk_types


def test_stored_message_attachments_stored_separately():
    from shinychat._attachments import Attachment
    from shinychat._chat_types import StoredMessage, StoredSegment

    msg = StoredMessage(
        role="user",
        segments=[StoredSegment(content="see this", content_type="markdown")],
        attachments=[
            Attachment(
                data_url="data:image/png;base64,AAAA",
                name="chart.png",
                mime="image/png",
                size=3,
            )
        ],
    )
    assert msg.content == "see this"
    assert len(msg.attachments) == 1
    assert msg.attachments[0].name == "chart.png"


def test_chat_message_attachments_become_stored_attachments():
    from shinychat._attachments import Attachment
    from shinychat._chat_types import ChatMessage, StoredMessage

    sm = StoredMessage.from_chat_message(
        ChatMessage(
            content="here",
            role="assistant",
            attachments=[
                Attachment.from_data(b"x", mime="image/png", name="c.png")
            ],
        )
    )
    assert len(sm.segments) == 1
    assert len(sm.attachments) == 1
    assert sm.attachments[0].name == "c.png"


def test_user_message_with_attachments_stores_correctly():
    from shinychat._attachments import Attachment
    from shinychat._chat_types import ChatMessage, StoredMessage

    sm = StoredMessage.from_chat_message(
        ChatMessage(
            content="look",
            role="user",
            attachments=[
                Attachment.from_data(b"x", mime="image/png", name="c.png")
            ],
        )
    )
    assert len(sm.segments) == 1
    assert len(sm.attachments) == 1
    assert sm.content == "look"


def test_bookmark_roundtrip_preserves_attachments():
    from shinychat._attachments import Attachment
    from shinychat._chat_types import StoredMessage, StoredSegment

    stored = StoredMessage(
        role="user",
        segments=[StoredSegment(content="look", content_type="markdown")],
        attachments=[
            Attachment(
                data_url="data:image/png;base64,AAAA",
                name="c.png",
                mime="image/png",
                size=3,
            )
        ],
    )
    dumped = stored.model_dump(exclude_none=True)
    restored = StoredMessage.model_validate(dumped)
    assert len(restored.attachments) == 1
    assert restored.attachments[0].name == "c.png"
    assert restored.content == "look"


def test_wire_segments_excludes_attachments():
    from shinychat._attachments import Attachment
    from shinychat._chat_types import StoredMessage, StoredSegment

    stored = StoredMessage(
        role="assistant",
        segments=[StoredSegment(content="hi", content_type="markdown")],
        attachments=[
            Attachment(
                data_url="data:,x",
                name="c.png",
                mime="image/png",
                size=1,
            )
        ],
    )
    segs = stored.wire_segments()
    assert len(segs) == 1
    assert segs[0] == {"content": "hi", "content_type": "markdown"}
    assert len(stored.attachments) == 1
    assert stored.attachments[0].name == "c.png"


def test_messages_surfaces_attachments():
    from shiny import reactive
    from shinychat._attachments import Attachment
    from shinychat._chat_types import ChatMessage

    with session_context(test_session):
        chat = Chat(id="chat")

        run_async(
            lambda: chat.append_message(
                ChatMessage(
                    "see attached",
                    role="assistant",
                    attachments=[
                        Attachment.from_data(
                            b"\x89PNG\r\n", mime="image/png", name="a.png"
                        ),
                    ],
                )
            )
        )
        run_async(lambda: chat.append_message(ChatMessage("plain text")))

        with reactive.isolate():
            msgs = chat.messages()

        # First message: assistant with attachment. No `format=` was passed, so
        # messages() returns ChatMessageDict entries.
        att_msg = cast(ChatMessageDict, msgs[0])
        assert "attachments" in att_msg
        atts = att_msg["attachments"]
        assert len(atts) == 1
        assert atts[0].mime == "image/png"
        assert atts[0].name == "a.png"
        assert atts[0].data_url.startswith("data:image/png;base64,")

        # Second message: plain text — no attachments key
        assert "attachments" not in msgs[1]
