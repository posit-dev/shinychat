from __future__ import annotations

import asyncio
import sys
from contextlib import nullcontext
from copy import deepcopy
from typing import Any, Awaitable, Callable, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import shinychat._history as history_module
from shiny import reactive
from shiny.module import ResolvedId
from shiny.session import session_context
from shinychat import Chat
from shinychat._history import ChatHistory, HistoryInputIds
from shinychat._history_store import (
    ConversationPartition,
    FileConversationStore,
    InMemoryConversationStore,
)
from shinychat._history_types import new_conversation_record_v2
from shinychat.types import ChatMessage, HistoryOptions

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockSession:
    ns: ResolvedId = ResolvedId("")
    app: object = None
    id: str = "mock-session-history"
    input: Any

    def __init__(self) -> None:
        from shiny import Inputs

        self.input = Inputs({}, ns=ResolvedId)

    def on_ended(self, callback: Callable[[], None]) -> Callable[[], None]:
        return lambda: None

    def on_destroy(self, callback: object) -> None:
        pass

    def _increment_busy_count(self) -> None:
        pass

    def _decrement_busy_count(self) -> None:
        pass

    def _process_ui(self, ui: Any) -> dict[str, Any]:
        return {"html": str(ui), "deps": []}

    def _send_message_sync(self, message: Any) -> None:
        pass

    async def _unhandled_error(self, error: Any) -> None:
        pass

    def is_stub_session(self) -> bool:
        return True


def _make_chat(history: "bool | HistoryOptions" = True) -> Chat:
    session = cast(Any, _MockSession())
    with session_context(session):
        chat = Chat("test_history", history=history)
    return chat


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_history_attr_always_present():
    chat = _make_chat()
    assert isinstance(chat.history, ChatHistory)


def test_history_config_applied_from_constructor():
    chat = _make_chat(
        history=HistoryOptions(store="memory", restore_mode="none")
    )
    assert chat.history._store == "memory"
    assert chat.history._restore_mode == "none"


def test_history_config_defaults_preserved():
    chat = _make_chat(history=HistoryOptions(store="memory"))
    assert chat.history._store == "memory"
    assert chat.history._restore_mode == "browser"  # default preserved
    assert chat.history._restore_bootstrap == "recorded"


def test_history_config_accepts_live_restore_bootstrap():
    chat = _make_chat(
        history=HistoryOptions(store="memory", restore_bootstrap="live")
    )
    assert chat.history._restore_bootstrap == "live"


def test_on_save_registers_callback():
    chat = _make_chat()

    @chat.history.on_save
    def _cb(data: dict[str, Any]) -> None:
        pass

    assert _cb in chat.history._save_callbacks


def test_on_restore_registers_callback():
    chat = _make_chat()

    @chat.history.on_restore
    def _cb(data: dict[str, Any]) -> None:
        pass

    assert _cb in chat.history._restore_callbacks


def test_on_save_returns_fn():
    chat = _make_chat()

    def _cb(data: dict[str, Any]) -> None:
        pass

    result = chat.history.on_save(_cb)
    assert result is _cb


def test_callbacks_available_before_enabled():
    chat = _make_chat()

    @chat.history.on_save
    def _save_cb(data: dict[str, Any]) -> None:
        pass

    @chat.history.on_restore
    def _restore_cb(data: dict[str, Any]) -> None:
        pass

    assert _save_cb in chat.history._save_callbacks
    assert _restore_cb in chat.history._restore_callbacks


# ---------------------------------------------------------------------------
# Task 3: auto-enable tests
# ---------------------------------------------------------------------------


def _make_chat_with_client(
    client: Any, history: "bool | HistoryOptions" = True
) -> "tuple[Chat, list[int]]":
    start_calls: list[int] = []

    def _fake_start(self: ChatHistory) -> None:
        start_calls.append(1)
        self._started = True

    session = cast(Any, _MockSession())
    with (
        session_context(session),
        patch.object(ChatHistory, "_start", _fake_start),
        patch("shinychat._chat.is_chatlas_chat_client", return_value=True),
    ):
        chat = Chat("test_history", client=client, history=history)
    return chat, start_calls


def test_history_auto_enabled_with_client():
    _, start_calls = _make_chat_with_client(MagicMock())
    assert len(start_calls) == 1


def test_history_not_enabled_when_history_false():
    _, start_calls = _make_chat_with_client(MagicMock(), history=False)
    assert len(start_calls) == 0


def test_history_client_stored_from_constructor():
    fake_client = MagicMock()
    chat, _ = _make_chat_with_client(fake_client)
    assert chat.client is not None
    assert chat.client.value is fake_client


def test_enable_without_client_raises():
    chat = _make_chat()
    with pytest.raises(ValueError, match="requires a client"):
        chat.history.enable()


def test_history_config_max_store_mb_default():
    config = HistoryOptions()
    assert config.max_store_mb == 100.0


def test_history_config_max_store_mb_custom():
    config = HistoryOptions(max_store_mb=50.0)
    assert config.max_store_mb == 50.0


def test_controller_starts_none():
    chat = _make_chat()
    assert chat.history._controller is None


@pytest.mark.anyio
async def test_save_returns_false_before_history_starts():
    chat = _make_chat()

    assert await chat.history.save() is False
    assert chat.history._controller is None


@pytest.mark.anyio
async def test_save_delegates_to_live_controller():
    chat = _make_chat()
    controller = MagicMock()
    controller.save = AsyncMock(return_value=True)
    chat.history._controller = controller

    assert await chat.history.save() is True
    controller.save.assert_awaited_once_with()


@pytest.mark.anyio
async def test_save_propagates_controller_errors():
    chat = _make_chat()
    controller = MagicMock()
    controller.save = AsyncMock(side_effect=OSError("disk full"))
    chat.history._controller = controller

    with pytest.raises(OSError, match="disk full"):
        await chat.history.save()


@pytest.mark.anyio
async def test_setup_greeting_wires_on_settled():
    chat = _make_chat()

    class _FakeController:
        on_settled: "Callable[[bool], Awaitable[None]] | None" = None

    fake_controller = _FakeController()
    chat.history._controller = cast(Any, fake_controller)

    with patch(
        "shinychat._chat_client.resolve_greeting", new=AsyncMock()
    ) as mock_resolve:
        chat.history.setup_greeting("## Hi")
        assert fake_controller.on_settled is not None

        await fake_controller.on_settled(False)
        mock_resolve.assert_awaited_once_with(chat, "## Hi")

        mock_resolve.reset_mock()
        await fake_controller.on_settled(True)
        mock_resolve.assert_not_awaited()


# ---------------------------------------------------------------------------
# Same-id reconstruction / session teardown (shinychat#wsmt)
# ---------------------------------------------------------------------------


class _MockBookmark:
    def __init__(self) -> None:
        self.exclude: list[str] = []
        self.store = "disable"
        self._restore_context: Any = None
        self.bookmark_callbacks: list[Callable[[Any], Any]] = []
        self.bookmarked_callbacks: list[Callable[[str], Any]] = []
        self.bookmark_urls: list[str] = []
        self.bookmark_states: list[dict[str, Any]] = []

    def on_bookmark(self, callback: Callable[[Any], Any]) -> Callable[[], None]:
        self.bookmark_callbacks.append(callback)

        def cancel() -> None:
            self.bookmark_callbacks.remove(callback)

        return cancel

    def on_bookmarked(
        self, callback: Callable[[str], Any]
    ) -> Callable[[], None]:
        self.bookmarked_callbacks.append(callback)

        def cancel() -> None:
            self.bookmarked_callbacks.remove(callback)

        return cancel

    async def do_bookmark(self) -> None:
        state = MagicMock(values={})
        for callback in self.bookmark_callbacks:
            result = callback(state)
            if asyncio.iscoroutine(result):
                await result
        self.bookmark_states.append(state.values)
        url = self.bookmark_urls.pop(0)
        for callback in list(self.bookmarked_callbacks):
            result = callback(url)
            if asyncio.iscoroutine(result):
                await result


class _LiveSession(_MockSession):
    """Non-stub session mock with just enough surface to run ChatHistory._start()."""

    def __init__(self) -> None:
        super().__init__()
        self.bookmark = _MockBookmark()
        self.ended_callbacks: list[Callable[[], None]] = []
        self.messages: list[dict[str, Any]] = []

    def is_stub_session(self) -> bool:
        return False

    def root_scope(self) -> "_LiveSession":
        return self

    def on_ended(self, callback: Callable[[], None]) -> Callable[[], None]:
        self.ended_callbacks.append(callback)

        def _unregister() -> None:
            if callback in self.ended_callbacks:
                self.ended_callbacks.remove(callback)

        return _unregister

    def _decrement_busy_count(self) -> None:
        pass

    async def send_custom_message(self, type: str, message: object) -> None:
        assert type == "shinyChatMessage"
        self.messages.append(cast(dict[str, Any], message))


class _MockClient:
    """Minimal ClientWithTurns stand-in; history requires turn-level access."""

    def __init__(self) -> None:
        self._turns: list[Any] = []

    def get_turns(self) -> list[Any]:
        return list(self._turns)

    def set_turns(self, turns: list[Any]) -> None:
        self._turns = list(turns)


def _make_live_chat(id: str, session: Any) -> Chat:
    with session_context(session):
        return Chat(
            id,
            client=cast(Any, _MockClient()),
            history=HistoryOptions(store="memory"),
        )


def _completion_actions(session: _LiveSession) -> list[dict[str, Any]]:
    return [
        message["action"]
        for message in session.messages
        if message["action"]["type"] == "history_transition_complete"
    ]


def _history_updates(session: _LiveSession) -> list[dict[str, Any]]:
    return [
        message["action"]
        for message in session.messages
        if message["action"]["type"] == "history_update"
    ]


class _CapturedHistoryEffect:
    def __init__(
        self,
        handler: Callable[[], Awaitable[None]],
        handlers: dict[str, Callable[[], Awaitable[None]]],
    ) -> None:
        handlers[handler.__name__] = handler

    def destroy(self) -> None:
        pass


def _capture_history_effects(
    handlers: dict[str, Callable[[], Awaitable[None]]],
) -> Callable[..., Any]:
    def capture_effect(
        handler: Callable[[], Awaitable[None]] | None = None, **_kwargs: Any
    ) -> Any:
        def decorator(
            effect_handler: Callable[[], Awaitable[None]],
        ) -> _CapturedHistoryEffect:
            return _CapturedHistoryEffect(effect_handler, handlers)

        return decorator if handler is None else decorator(handler)

    return capture_effect


@pytest.mark.anyio
@pytest.mark.parametrize("with_client", [False, True])
async def test_history_disabled_publishes_one_initial_withdrawal(
    with_client: bool,
) -> None:
    session = _LiveSession()
    with session_context(cast(Any, session)):
        chat = Chat(
            f"history_disabled_{with_client}",
            client=cast(Any, _MockClient()) if with_client else None,
            history=False,
        )
        try:
            await reactive.flush()
            await reactive.flush()
        finally:
            chat.destroy()

    assert _history_updates(session) == [
        {
            "type": "history_update",
            "enabled": False,
            "conversations": [],
            "active_id": None,
        }
    ]
    assert chat.history._started is False
    assert chat.history._controller is None


@pytest.mark.anyio
async def test_chat_without_client_publishes_initial_history_withdrawal() -> (
    None
):
    session = _LiveSession()
    with session_context(cast(Any, session)):
        chat = Chat("history_unavailable_without_client")
        try:
            await reactive.flush()
            await reactive.flush()
        finally:
            chat.destroy()

    assert _history_updates(session) == [
        {
            "type": "history_update",
            "enabled": False,
            "conversations": [],
            "active_id": None,
        }
    ]
    assert chat.history._started is False
    assert chat.history._controller is None


@pytest.mark.anyio
@pytest.mark.parametrize("restore_bootstrap", ["recorded", "live"])
@pytest.mark.parametrize("target_id", [None, "c_target"])
async def test_v2_initial_readiness_suppresses_capture_until_initial_decision(
    restore_bootstrap: str,
    target_id: str | None,
) -> None:
    chat_id = f"initial_capture_{restore_bootstrap}_{target_id or 'fresh'}"
    session = _LiveSession()
    store = InMemoryConversationStore()
    history_ids = HistoryInputIds.for_chat(ResolvedId(chat_id))
    session.input[history_ids.browser_token] = reactive.Value("token")
    session.input[history_ids.current_id] = reactive.Value(target_id)
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}

    with (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True),
        patch.object(reactive, "effect", _capture_history_effects(handlers)),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            chat_id,
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=store,
                scope="test",
                restore_mode="browser",
                restore_bootstrap=restore_bootstrap,  # type: ignore[arg-type]
            ),
        )

    try:
        controller = chat.history._controller
        assert controller is not None
        recorder = controller._exchange_recorder
        assert recorder is not None
        assert not chat.history._initial_history_initialized
        if target_id is not None:
            await store.put(
                ConversationPartition(chat_id=chat_id, scope="test"),
                new_conversation_record_v2(
                    title="target",
                    id=target_id,
                    client_info={},
                ),
            )
        stored_before = await store.list(
            ConversationPartition(chat_id=chat_id, scope="test")
        )

        await chat._record_accepted_user_input_with_capture(
            ChatMessage(content="blocked input", role="user")
        )
        await chat.append_message(object())
        assert not await chat._append_message_chunk(
            "", chunk="start", stream_id="blocked-stream"
        )
        async with chat.message_stream_context() as stream:
            await stream.append("blocked stream append")
            await stream.replace("blocked stream replace")

        stream_started = False

        async def blocked_stream():
            nonlocal stream_started
            stream_started = True
            yield "blocked stream update"

        with patch.object(
            reactive,
            "extended_task",
            wraps=reactive.extended_task,
        ) as extended_task:
            assert await chat.append_message_stream(blocked_stream()) is None
        extended_task.assert_not_called()
        assert not stream_started
        assert chat._transcript.read() == ()
        assert chat._transcript.active_stream_id is None
        assert recorder.record is None
        assert [message["action"]["type"] for message in session.messages] == []
        assert (
            await store.list(
                ConversationPartition(chat_id=chat_id, scope="test")
            )
        ) == stored_before

        with session_context(cast(Any, session)), reactive.isolate():
            await handlers["_init_history"]()

        assert chat.history._initial_history_initialized
        assert len(_history_updates(session)) == 1
        await chat.append_message("root captured append")
        assert recorder.record is not None
        root_id = recorder.record.active_leaf
        assert root_id is not None
        root = recorder.record.nodes[root_id]
        assert root.input is None
        assert [
            message.as_stored_message().content
            for message in cast(Any, root).messages
        ] == ["root captured append"]

        async def root_stream():
            yield "root captured public stream"

        stream_task = await chat.append_message_stream(root_stream())
        assert stream_task is not None
        stream_status = "running"
        for _ in range(100):
            with reactive.isolate():
                stream_status = stream_task.status()
            if stream_status == "success":
                break
            await asyncio.sleep(0.01)
        assert stream_status == "success"
        assert recorder.record is not None
        stream_root_id = recorder.record.active_leaf
        assert stream_root_id is not None
        stream_root = recorder.record.nodes[stream_root_id]
        assert stream_root.input is None
        assert stream_root.status == "ok"
        assert [
            message.as_stored_message().content
            for message in cast(Any, stream_root).messages
        ] == ["root captured public stream"]

        async with chat.message_stream_context() as stream:
            await stream.append("root captured stream append")
            await stream.replace("root captured stream replace")

        await chat._record_accepted_user_input_with_capture(
            ChatMessage(content="accepted input", role="user")
        )
        await chat._append_message_chunk(
            "", chunk="start", stream_id="accepted-stream"
        )
        await chat._append_message_chunk(
            "accepted stream update", chunk=True, stream_id="accepted-stream"
        )
        await chat._append_message_chunk(
            "", chunk="end", stream_id="accepted-stream"
        )

        assert [entry.message.content for entry in chat._transcript.read()] == [
            "root captured append",
            "root captured public stream",
            "root captured stream replace",
            "accepted input",
            "accepted stream update",
        ]
        assert chat._transcript.active_stream_id is None
        assert recorder.record is not None
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_v2_initial_readiness_stays_false_when_cleanup_update_fails() -> (
    None
):
    chat_id = "initial_readiness_cleanup_send_failure"
    session = _LiveSession()
    store = InMemoryConversationStore()
    history_ids = HistoryInputIds.for_chat(ResolvedId(chat_id))
    session.input[history_ids.browser_token] = reactive.Value("token")
    session.input[history_ids.current_id] = reactive.Value("c_target")
    await store.put(
        ConversationPartition(chat_id=chat_id, scope="test"),
        new_conversation_record_v2(
            title="target",
            id="c_target",
            client_info={},
        ),
    )
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}

    with (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True),
        patch.object(reactive, "effect", _capture_history_effects(handlers)),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            chat_id,
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=store,
                scope="test",
                restore_mode="browser",
            ),
        )

    controller = chat.history._controller
    assert controller is not None
    recorder = controller._exchange_recorder
    assert recorder is not None
    original = RuntimeError("restore failed")
    publication_failure = RuntimeError("history update failed")

    async def fail_replay(_target: Any, _node_ids: tuple[str, ...]) -> None:
        raise original

    async def fail_history_update() -> None:
        raise publication_failure

    controller._replay_exchange_display = fail_replay  # type: ignore[method-assign]
    controller.send_history_update = fail_history_update  # type: ignore[method-assign]
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]
    settled: list[bool] = []

    async def on_settled(restored: bool) -> None:
        settled.append(restored)

    controller.on_settled = on_settled

    try:
        with (
            session_context(cast(Any, session)),
            reactive.isolate(),
            pytest.raises(RuntimeError) as raised,
        ):
            await handlers["_init_history"]()

        assert raised.value is original
        assert not chat.history._initial_history_initialized
        assert settled == [False]
        assert recorder.record is None
        assert controller.record is None
        assert controller._active_id_now() is None
        assert _history_updates(session) == []
        notifier.assert_awaited_once_with(recovery_incomplete=True)
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_v2_initial_readiness_flips_after_history_update_send() -> None:
    session = _LiveSession()
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}
    with (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True),
        patch.object(reactive, "effect", _capture_history_effects(handlers)),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            "initial_readiness_send",
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store="memory",
                scope="test",
                restore_mode="none",
            ),
        )

    try:
        controller = chat.history._controller
        assert controller is not None
        send_started = asyncio.Event()
        release_send = asyncio.Event()
        send_history_update = controller.send_history_update

        async def blocked_history_update() -> None:
            send_started.set()
            await release_send.wait()
            await send_history_update()

        controller.send_history_update = blocked_history_update  # type: ignore[method-assign]
        with session_context(cast(Any, session)), reactive.isolate():
            init = asyncio.ensure_future(handlers["_init_history"]())
        await send_started.wait()
        assert not chat.history._initial_history_initialized

        release_send.set()
        await init
        assert chat.history._initial_history_initialized
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_v2_successful_bookmark_pointer_suppresses_then_admits_root_append() -> (
    None
):
    chat_id = "initial_bookmark_pointer_boundary"
    session = _LiveSession()
    session.bookmark.store = "server"
    session.bookmark._restore_context = MagicMock(
        active=True,
        values={
            f"{chat_id}_history_exchange_pointer": {
                "conversation_id": "c_target",
                "node_id": "n_0000",
            }
        },
    )
    store = InMemoryConversationStore()
    await store.put(
        ConversationPartition(chat_id=chat_id, scope="test"),
        new_conversation_record_v2(
            title="target",
            id="c_target",
            client_info={},
        ),
    )
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}

    with (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True),
        patch.object(reactive, "effect", _capture_history_effects(handlers)),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            chat_id,
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=store,
                scope="test",
                restore_mode="bookmark",
            ),
        )

    try:
        controller = chat.history._controller
        assert controller is not None
        recorder = controller._exchange_recorder
        assert recorder is not None

        await chat.append_message("suppressed bookmark append")
        assert not chat.history._initial_history_initialized
        assert chat._transcript.read() == ()
        assert recorder.record is None
        assert session.messages == []

        with session_context(cast(Any, session)), reactive.isolate():
            await handlers["_init_history"]()

        assert chat.history._initial_history_initialized
        assert len(_history_updates(session)) == 1
        assert recorder.record is not None
        assert recorder.record.id == "c_target"
        assert recorder.record.active_leaf == "n_0000"
        assert controller._active_id_now() == "c_target"

        await chat.append_message("admitted bookmark append")
        assert recorder.record is not None
        active_leaf = recorder.record.active_leaf
        assert active_leaf is not None
        root = recorder.record.nodes[active_leaf]
        assert root.input is None
        assert [
            message.as_stored_message().content
            for message in cast(Any, root).messages
        ] == ["admitted bookmark append"]
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_v2_initial_readiness_rejects_direct_input_without_mutation() -> (
    None
):
    chat_id = "initial_readiness_direct_input"
    session = _LiveSession()
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}

    with (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True),
        patch.object(reactive, "effect", _capture_history_effects(handlers)),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            chat_id,
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store="memory",
                scope="test",
                restore_mode="none",
            ),
        )

    controller = chat.history._controller
    assert controller is not None
    recorder = controller._exchange_recorder
    assert recorder is not None
    controller.partition = ConversationPartition(chat_id=chat_id, scope="test")

    with session_context(cast(Any, session)), reactive.isolate():
        chat._record_accepted_user_input(
            ChatMessage(content="forged input", role="user")
        )
        await chat._record_accepted_user_input_with_capture(
            ChatMessage(content="direct input", role="user")
        )

    assert chat._transcript.read() == ()
    with reactive.isolate():
        assert chat._latest_user_input() is None
        assert chat._normal_user_submission() is None
    assert controller._active_id_now() is None
    assert recorder.record is None


@pytest.mark.anyio
async def test_v2_initial_messages_are_suppressed_while_unresolved() -> None:
    chat_id = "initial_messages_fresh"
    session = _LiveSession()
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}

    with (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True),
        patch.object(reactive, "effect", _capture_history_effects(handlers)),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            chat_id,
            client=cast(Any, _MockClient()),
            messages=["initial message"],
            history=HistoryOptions(
                store="memory",
                scope="test",
                restore_mode="none",
            ),
        )

    try:
        with session_context(cast(Any, session)), reactive.isolate():
            await handlers["_init_chat"]()
        assert chat._transcript.read() == ()

        with session_context(cast(Any, session)), reactive.isolate():
            await handlers["_init_history"]()

        assert chat._transcript.read() == ()
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_v2_initial_messages_follow_real_initialization_order() -> None:
    session = _LiveSession()
    with (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            "initial_messages_effect_order",
            client=cast(Any, _MockClient()),
            messages=["initial message"],
            history=HistoryOptions(
                store="memory",
                scope="test",
                restore_mode="none",
            ),
        )
        try:
            await reactive.flush()
            await reactive.flush()
        finally:
            chat.destroy()

    assert chat.history._initial_history_initialized
    assert [entry.message.content for entry in chat._transcript.read()] == [
        "initial message"
    ]


@pytest.mark.anyio
async def test_v2_initial_messages_are_suppressed_before_restored_decision() -> (
    None
):
    chat_id = "initial_messages_restored"
    session = _LiveSession()
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}

    with (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True),
        patch.object(reactive, "effect", _capture_history_effects(handlers)),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            chat_id,
            client=cast(Any, _MockClient()),
            messages=["initial message"],
            history=HistoryOptions(
                store="memory",
                scope="test",
                restore_mode="none",
            ),
        )

    try:
        with session_context(cast(Any, session)), reactive.isolate():
            await handlers["_init_chat"]()
        assert chat._transcript.read() == ()
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_v2_initial_messages_suppress_real_restored_target() -> None:
    chat_id = "initial_messages_real_restored_target"
    session = _LiveSession()
    store = InMemoryConversationStore()
    history_ids = HistoryInputIds.for_chat(ResolvedId(chat_id))
    session.input[history_ids.browser_token] = reactive.Value("token")
    session.input[history_ids.current_id] = reactive.Value("c_target")
    await store.put(
        ConversationPartition(chat_id=chat_id, scope="test"),
        new_conversation_record_v2(
            title="target",
            id="c_target",
            client_info={},
        ),
    )

    with (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            chat_id,
            client=cast(Any, _MockClient()),
            messages=["constructor message"],
            history=HistoryOptions(
                store=store,
                scope="test",
                restore_mode="browser",
            ),
        )
        try:
            await reactive.flush()
            await reactive.flush()
        finally:
            chat.destroy()

    assert chat.history._initial_history_initialized
    assert [entry.message.content for entry in chat._transcript.read()] == [
        "constructor message"
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("use_exchange_tree", "transition_protocol"),
    [(False, "completion-v1"), (True, "completion-v2")],
)
async def test_history_enabled_startup_preserves_source_protocol(
    use_exchange_tree: bool,
    transition_protocol: str,
) -> None:
    session = _LiveSession()
    with (
        patch.object(
            history_module,
            "_EXCHANGE_TREE_HISTORY_V2",
            use_exchange_tree,
        ),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            f"history_enabled_{use_exchange_tree}",
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store="memory",
                scope="test",
                restore_mode="none",
            ),
        )
        try:
            await reactive.flush()
            await reactive.flush()
        finally:
            chat.destroy()

    assert _history_updates(session) == [
        {
            "type": "history_update",
            "enabled": True,
            "conversations": [],
            "active_id": None,
            "transition_protocol": transition_protocol,
        }
    ]
    assert chat.history._started is True
    assert chat.history._controller is not None


@pytest.mark.anyio
async def test_v2_server_bookmark_stamps_atomic_history_pointer_only() -> None:
    session = _LiveSession()
    session.bookmark.store = "server"

    class CapturedEffect:
        def __init__(self, _handler: Callable[[], Awaitable[None]]) -> None:
            pass

        def destroy(self) -> None:
            pass

    def capture_effect(
        handler: Callable[[], Awaitable[None]] | None = None, **_kwargs: Any
    ) -> Any:
        def decorator(
            effect_handler: Callable[[], Awaitable[None]],
        ) -> CapturedEffect:
            return CapturedEffect(effect_handler)

        return decorator if handler is None else decorator(handler)

    with (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True),
        patch.object(reactive, "effect", capture_effect),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            "bookmark_pointer",
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=InMemoryConversationStore(),
                scope="test",
                restore_mode="none",
            ),
        )

    controller = chat.history._controller
    assert controller is not None
    recorder = controller._exchange_recorder
    assert recorder is not None
    recorder.record = new_conversation_record_v2(
        title="pointer",
        id="c_pointer",
        client_info={},
    )
    state = MagicMock(values={})

    for callback in session.bookmark.bookmark_callbacks:
        result = callback(state)
        if asyncio.iscoroutine(result):
            await result

    assert state.values == {
        "bookmark_pointer_history_exchange_pointer": {
            "conversation_id": "c_pointer",
            "node_id": "n_0000",
        }
    }


@pytest.mark.anyio
async def test_v2_stale_server_bookmark_pointer_notifies_and_keeps_draft() -> (
    None
):
    session = _LiveSession()
    session.bookmark.store = "server"
    session.bookmark._restore_context = MagicMock(
        active=True,
        values={
            "stale_pointer_history_exchange_pointer": {
                "conversation_id": "missing",
                "node_id": "n_missing",
            }
        },
    )
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}

    class CapturedEffect:
        def __init__(self, handler: Callable[[], Awaitable[None]]) -> None:
            handlers[handler.__name__] = handler

        def destroy(self) -> None:
            pass

    def capture_effect(
        handler: Callable[[], Awaitable[None]] | None = None, **_kwargs: Any
    ) -> Any:
        def decorator(
            effect_handler: Callable[[], Awaitable[None]],
        ) -> CapturedEffect:
            return CapturedEffect(effect_handler)

        return decorator if handler is None else decorator(handler)

    notification = MagicMock()
    with (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True),
        patch.object(reactive, "effect", capture_effect),
        patch("shiny.ui.notification_show", notification),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            "stale_pointer",
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=InMemoryConversationStore(),
                scope="test",
                restore_mode="none",
            ),
        )

    with (
        patch("shiny.ui.notification_show", notification),
        session_context(cast(Any, session)),
        reactive.isolate(),
    ):
        await handlers["_init_history"]()

    controller = chat.history._controller
    assert controller is not None
    assert controller._active_id_now() is None
    assert controller.record is None
    assert controller._exchange_recorder is not None
    assert controller._exchange_recorder.record is None
    assert chat.history._initial_history_initialized
    assert chat.messages() == ()
    notification.assert_called_once()


@pytest.mark.anyio
@pytest.mark.parametrize("restore_mode", ["bookmark", "browser", "url"])
async def test_v2_initial_restore_preflight_failure_recovers(
    restore_mode: str,
) -> None:
    chat_id = f"initial_restore_{restore_mode}"
    session = _LiveSession()
    store = InMemoryConversationStore()
    history_ids = HistoryInputIds.for_chat(ResolvedId(chat_id))
    if restore_mode == "bookmark":
        session.bookmark.store = "server"
        session.bookmark._restore_context = MagicMock(
            active=True,
            values={
                f"{chat_id}_history_exchange_pointer": {
                    "conversation_id": "c_target",
                    "node_id": "n_0000",
                }
            },
        )
    else:
        session.input[history_ids.browser_token] = reactive.Value("token")
        input_id = (
            history_ids.current_id
            if restore_mode == "browser"
            else history_ids.url_id
        )
        session.input[input_id] = reactive.Value("c_target")

    handlers: dict[str, Callable[[], Awaitable[None]]] = {}

    class CapturedEffect:
        def __init__(self, handler: Callable[[], Awaitable[None]]) -> None:
            handlers[handler.__name__] = handler

        def destroy(self) -> None:
            pass

    def capture_effect(
        handler: Callable[[], Awaitable[None]] | None = None, **_kwargs: Any
    ) -> Any:
        def decorator(
            effect_handler: Callable[[], Awaitable[None]],
        ) -> CapturedEffect:
            return CapturedEffect(effect_handler)

        return decorator if handler is None else decorator(handler)

    with (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True),
        patch.object(reactive, "effect", capture_effect),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            chat_id,
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=store,
                scope="test",
                restore_mode=restore_mode,  # type: ignore[arg-type]
            ),
        )

    controller = chat.history._controller
    assert controller is not None
    target = new_conversation_record_v2(
        title="target",
        id="c_target",
        client_info={},
    )
    target_before = target.model_dump(mode="json")
    partition = ConversationPartition(chat_id=chat_id, scope="test")
    await store.put(partition, target)
    expected = ValueError("initial preflight failed")

    def fail_preflight(*_args: Any, **_kwargs: Any) -> Any:
        raise expected

    recorder = controller._exchange_recorder
    assert recorder is not None
    recorder._preflight_restore_state = fail_preflight  # type: ignore[method-assign]
    settled: list[bool] = []

    async def on_settled(restored: bool) -> None:
        settled.append(restored)

    controller.on_settled = on_settled
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    with (
        session_context(cast(Any, session)),
        reactive.isolate(),
        pytest.raises(ValueError) as raised,
    ):
        await handlers["_init_history"]()

    assert raised.value is expected
    assert settled == [False]
    assert controller.record is None
    assert controller._active_id_now() is None
    assert recorder.record is None
    assert target.model_dump(mode="json") == target_before
    assert await store.get(partition, target.id) is target
    updates = [
        message["action"]
        for message in session.messages
        if message["action"]["type"] == "history_update"
    ]
    assert len(updates) == 1
    assert updates[0]["active_id"] is None
    assert updates[0]["transition_protocol"] == "completion-v2"
    assert chat.history._initial_history_initialized
    notifier.assert_awaited_once_with(recovery_incomplete=False)
    with session_context(cast(Any, session)), reactive.isolate():
        await chat._record_accepted_user_input_with_capture(
            ChatMessage(content="fresh after preflight failure", role="user")
        )
    assert recorder.record is not None


@pytest.mark.anyio
async def test_v2_initial_restore_preflight_cancellation_recovers_once() -> (
    None
):
    chat_id = "initial_preflight_cancel"
    session = _LiveSession()
    store = InMemoryConversationStore()
    history_ids = HistoryInputIds.for_chat(ResolvedId(chat_id))
    session.input[history_ids.browser_token] = reactive.Value("token")
    session.input[history_ids.current_id] = reactive.Value("c_target")
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}

    with (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True),
        patch.object(reactive, "effect", _capture_history_effects(handlers)),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            chat_id,
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=store,
                scope="test",
                restore_mode="browser",
            ),
        )

    controller = chat.history._controller
    assert controller is not None
    target = new_conversation_record_v2(
        title="target",
        id="c_target",
        client_info={},
    )
    target_before = target.model_dump(mode="json")
    partition = ConversationPartition(chat_id=chat_id, scope="test")
    await store.put(partition, target)
    original = asyncio.CancelledError("initial preflight cancelled")
    preflight = MagicMock(side_effect=original)
    replay = AsyncMock(side_effect=AssertionError("replay must not run"))
    controller._prepare_exchange_restore = preflight  # type: ignore[method-assign]
    controller._replay_exchange_display = replay  # type: ignore[method-assign]
    recorder = controller._exchange_recorder
    assert recorder is not None
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]
    settled: list[bool] = []

    async def on_settled(restored: bool) -> None:
        settled.append(restored)

    controller.on_settled = on_settled

    with (
        session_context(cast(Any, session)),
        reactive.isolate(),
        pytest.raises(asyncio.CancelledError) as raised,
    ):
        await handlers["_init_history"]()

    assert raised.value is original
    assert preflight.call_count == 1
    replay.assert_not_awaited()
    assert settled == [False]
    assert controller.record is None
    assert controller._active_id_now() is None
    assert recorder.record is None
    assert target.model_dump(mode="json") == target_before
    assert await store.get(partition, target.id) is target
    updates = _history_updates(session)
    assert len(updates) == 1
    assert updates[0]["active_id"] is None
    assert updates[0]["transition_protocol"] == "completion-v2"
    assert chat.history._initial_history_initialized
    notifier.assert_awaited_once_with(recovery_incomplete=False)

    with session_context(cast(Any, session)), reactive.isolate():
        await handlers["_init_history"]()

    assert preflight.call_count == 1
    replay.assert_not_awaited()
    assert settled == [False]
    assert len(_history_updates(session)) == 1


@pytest.mark.anyio
async def test_v2_initial_restore_cancellation_uses_transaction_recovery() -> (
    None
):
    chat_id = "initial_restore_cancel"
    session = _LiveSession()
    store = InMemoryConversationStore()
    history_ids = HistoryInputIds.for_chat(ResolvedId(chat_id))
    session.input[history_ids.browser_token] = reactive.Value("token")
    session.input[history_ids.current_id] = reactive.Value("c_target")
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}

    class CapturedEffect:
        def __init__(self, handler: Callable[[], Awaitable[None]]) -> None:
            handlers[handler.__name__] = handler

        def destroy(self) -> None:
            pass

    def capture_effect(
        handler: Callable[[], Awaitable[None]] | None = None, **_kwargs: Any
    ) -> Any:
        def decorator(
            effect_handler: Callable[[], Awaitable[None]],
        ) -> CapturedEffect:
            return CapturedEffect(effect_handler)

        return decorator if handler is None else decorator(handler)

    with (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True),
        patch.object(reactive, "effect", capture_effect),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            chat_id,
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=store,
                scope="test",
                restore_mode="browser",
                restore_bootstrap="live",
            ),
        )

    controller = chat.history._controller
    assert controller is not None
    target = new_conversation_record_v2(
        title="target",
        id="c_target",
        client_info={},
    )
    partition = ConversationPartition(chat_id=chat_id, scope="test")
    await store.put(partition, target)
    original = asyncio.CancelledError("initial restore cancelled")
    recorder = controller._exchange_recorder
    assert recorder is not None

    async def cancel_replay(_target: Any, _node_ids: tuple[str, ...]) -> None:
        raise original

    controller._replay_exchange_display = cancel_replay  # type: ignore[method-assign]
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]
    settled: list[bool] = []

    async def on_settled(restored: bool) -> None:
        settled.append(restored)

    controller.on_settled = on_settled

    with (
        session_context(cast(Any, session)),
        reactive.isolate(),
        pytest.raises(asyncio.CancelledError) as raised,
    ):
        await handlers["_init_history"]()

    assert raised.value is original
    assert controller.record is None
    assert controller._active_id_now() is None
    assert recorder.record is None
    assert settled == [False]
    updates = [
        message["action"]
        for message in session.messages
        if message["action"]["type"] == "history_update"
    ]
    assert len(updates) == 1
    assert updates[0]["active_id"] is None
    assert chat.history._initial_history_initialized
    notifier.assert_awaited_once_with(recovery_incomplete=False)

    with (
        session_context(cast(Any, session)),
        reactive.isolate(),
    ):
        await handlers["_init_history"]()

    assert settled == [False]
    assert (
        len(
            [
                message
                for message in session.messages
                if message["action"]["type"] == "history_update"
            ]
        )
        == 1
    )
    with session_context(cast(Any, session)), reactive.isolate():
        await chat._record_accepted_user_input_with_capture(
            ChatMessage(content="fresh after cancellation", role="user")
        )
    assert recorder.record is not None


@pytest.mark.anyio
async def test_v2_bookmark_settlement_updates_url_and_deletes_replaced_state() -> (
    None
):
    session = _LiveSession()
    session.bookmark.store = "server"
    session.bookmark.bookmark_urls = [
        "?_state_id_=state-first",
        "?_state_id_=state-second",
    ]

    class CapturedEffect:
        def __init__(self, _handler: Callable[[], Awaitable[None]]) -> None:
            pass

        def destroy(self) -> None:
            pass

    def capture_effect(
        handler: Callable[[], Awaitable[None]] | None = None, **_kwargs: Any
    ) -> Any:
        def decorator(
            effect_handler: Callable[[], Awaitable[None]],
        ) -> CapturedEffect:
            return CapturedEffect(effect_handler)

        return decorator if handler is None else decorator(handler)

    with (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True),
        patch.object(reactive, "effect", capture_effect),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            "bookmark_settlement",
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=InMemoryConversationStore(),
                scope="test",
                restore_mode="bookmark",
            ),
        )

    controller = chat.history._controller
    assert controller is not None
    recorder = controller._exchange_recorder
    assert recorder is not None
    controller.partition = ConversationPartition(
        chat_id="bookmark_settlement", scope="test"
    )
    record = new_conversation_record_v2(
        title="pointer",
        id="c_pointer",
        client_info={},
    )
    recorder.record = record
    controller._active_id.set(record.id)

    deleted = AsyncMock()
    with patch.object(history_module, "delete_bookmark_state", deleted):
        assert controller.on_response_saved is not None
        await controller.on_response_saved(cast(Any, record))
        record.open_inputless_exchange()
        await controller.on_response_saved(cast(Any, record))

    assert record.bookmark_state_id == "state-second"
    deleted.assert_awaited_once_with("state-first")
    assert session.bookmark.bookmark_states == [
        {
            "bookmark_settlement_history_exchange_pointer": {
                "conversation_id": "c_pointer",
                "node_id": "n_0000",
            }
        },
        {
            "bookmark_settlement_history_exchange_pointer": {
                "conversation_id": "c_pointer",
                "node_id": "n_0001",
            }
        },
    ]
    assert [message["action"]["url"] for message in session.messages] == [
        "?_state_id_=state-first",
        "?_state_id_=state-second",
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("operation", "outcome"),
    [
        ("new", "success"),
        ("new", "failure"),
        ("new", "cancelled"),
        ("delete", "success"),
        ("delete", "failure"),
        ("delete", "cancelled"),
        ("edit", "success"),
        ("edit", "failure"),
        ("edit", "cancelled"),
        ("resubmit", "success"),
        ("resubmit", "failure"),
        ("resubmit", "cancelled"),
        ("navigate", "success"),
        ("navigate", "failure"),
        ("navigate", "cancelled"),
    ],
)
async def test_history_transition_completion_always_matches_request(
    operation: str, outcome: str
) -> None:
    session = _LiveSession()
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}

    class CapturedEffect:
        def __init__(self, handler: Callable[[], Awaitable[None]]) -> None:
            handlers[handler.__name__] = handler

        def destroy(self) -> None:
            pass

    def capture_effect(
        handler: Callable[[], Awaitable[None]] | None = None, **_kwargs: Any
    ) -> Any:
        def decorator(
            effect_handler: Callable[[], Awaitable[None]],
        ) -> CapturedEffect:
            return CapturedEffect(effect_handler)

        return decorator if handler is None else decorator(handler)

    v2_navigation = (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True)
        if operation == "navigate"
        else nullcontext()
    )
    with (
        patch.object(reactive, "effect", capture_effect),
        v2_navigation,
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            "transition",
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store="memory", scope="test", restore_mode="none"
            ),
        )
    controller = chat.history._controller
    assert controller is not None
    controller.partition = cast(Any, object())

    if outcome == "failure":
        operation_fn = AsyncMock(side_effect=RuntimeError("expected failure"))
    elif outcome == "cancelled":

        async def operation_fn(*_args: Any, **_kwargs: Any) -> None:
            raise asyncio.CancelledError()

    else:
        operation_fn = AsyncMock()

    ids = HistoryInputIds.for_chat(ResolvedId("transition"))
    if operation == "new":
        controller.new_chat = operation_fn  # type: ignore[method-assign]
        input_id = ids.new
        payload: object = {"requestId": f"{operation}-{outcome}"}
    elif operation == "delete":
        controller.delete = operation_fn  # type: ignore[method-assign]
        input_id = ids.delete
        payload = {"id": "active", "requestId": f"{operation}-{outcome}"}
    elif operation == "edit":
        controller.handle_edit = operation_fn  # type: ignore[method-assign]
        input_id = ids.message_edit
        payload = {
            "index": 0,
            "content": "edited",
            "attachments": [],
            "requestId": f"{operation}-{outcome}",
        }
    elif operation == "resubmit":
        controller.handle_resubmit = operation_fn  # type: ignore[method-assign]
        input_id = ids.message_resubmit
        payload = {
            "index": 0,
            "kind": "retry",
            "requestId": f"{operation}-{outcome}",
        }
    else:
        controller.handle_navigate = operation_fn  # type: ignore[method-assign]
        input_id = ids.message_navigate
        payload = {
            "index": 0,
            "direction": "prev",
            "requestId": f"{operation}-{outcome}",
        }

    with session_context(cast(Any, session)):
        cast(Any, session.input[input_id])._set(payload)
    try:
        with reactive.isolate():
            await handlers[f"_on_{operation}"]()
    except asyncio.CancelledError:
        pass

    assert _completion_actions(session) == [
        {
            "type": "history_transition_complete",
            "requestId": f"{operation}-{outcome}",
        }
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "operation", ["new", "delete", "edit", "resubmit", "navigate"]
)
async def test_history_transition_legacy_payload_does_not_send_completion(
    operation: str,
) -> None:
    session = _LiveSession()
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}

    class CapturedEffect:
        def __init__(self, handler: Callable[[], Awaitable[None]]) -> None:
            handlers[handler.__name__] = handler

        def destroy(self) -> None:
            pass

    def capture_effect(
        handler: Callable[[], Awaitable[None]] | None = None, **_kwargs: Any
    ) -> Any:
        def decorator(
            effect_handler: Callable[[], Awaitable[None]],
        ) -> CapturedEffect:
            return CapturedEffect(effect_handler)

        return decorator if handler is None else decorator(handler)

    v2_navigation = (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True)
        if operation == "navigate"
        else nullcontext()
    )
    with (
        patch.object(reactive, "effect", capture_effect),
        v2_navigation,
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            "transition_legacy",
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store="memory", scope="test", restore_mode="none"
            ),
        )
    controller = chat.history._controller
    assert controller is not None
    controller.partition = cast(Any, object())

    ids = HistoryInputIds.for_chat(ResolvedId("transition_legacy"))
    if operation == "new":
        controller.new_chat = AsyncMock()  # type: ignore[method-assign]
        input_id = ids.new
        payload: object = 1
    elif operation == "delete":
        controller.delete = AsyncMock()  # type: ignore[method-assign]
        input_id = ids.delete
        payload = {"id": "active"}
    elif operation == "edit":
        controller.handle_edit = AsyncMock()  # type: ignore[method-assign]
        input_id = ids.message_edit
        payload = {"index": 0, "content": "edited", "attachments": []}
    elif operation == "resubmit":
        controller.handle_resubmit = AsyncMock()  # type: ignore[method-assign]
        input_id = ids.message_resubmit
        payload = {"index": 0, "kind": "retry"}
    else:
        controller.handle_navigate = AsyncMock()  # type: ignore[method-assign]
        input_id = ids.message_navigate
        payload = {"index": 0, "direction": "prev"}

    with session_context(cast(Any, session)):
        cast(Any, session.input[input_id])._set(payload)
    with reactive.isolate():
        await handlers[f"_on_{operation}"]()

    assert _completion_actions(session) == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("operation", "outcome"),
    [
        ("new", "success"),
        ("new", "failure"),
        ("new", "cancelled"),
        ("delete", "success"),
        ("delete", "failure"),
        ("delete", "cancelled"),
        ("edit", "success"),
        ("edit", "failure"),
        ("edit", "cancelled"),
        ("resubmit", "success"),
        ("resubmit", "failure"),
        ("resubmit", "cancelled"),
        ("navigate", "success"),
        ("navigate", "failure"),
        ("navigate", "cancelled"),
    ],
)
async def test_completion_delivery_failure_does_not_mask_transition_outcome(
    operation: str, outcome: str
) -> None:
    session = _LiveSession()
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}

    class CapturedEffect:
        def __init__(self, handler: Callable[[], Awaitable[None]]) -> None:
            handlers[handler.__name__] = handler

        def destroy(self) -> None:
            pass

    def capture_effect(
        handler: Callable[[], Awaitable[None]] | None = None, **_kwargs: Any
    ) -> Any:
        def decorator(
            effect_handler: Callable[[], Awaitable[None]],
        ) -> CapturedEffect:
            return CapturedEffect(effect_handler)

        return decorator if handler is None else decorator(handler)

    v2_navigation = (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True)
        if operation == "navigate"
        else nullcontext()
    )
    with (
        patch.object(reactive, "effect", capture_effect),
        v2_navigation,
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            "transition_delivery",
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store="memory", scope="test", restore_mode="none"
            ),
        )
    controller = chat.history._controller
    assert controller is not None
    controller.partition = cast(Any, object())

    if outcome == "failure":
        operation_fn = AsyncMock(side_effect=RuntimeError("expected failure"))
    elif outcome == "cancelled":

        async def operation_fn(*_args: Any, **_kwargs: Any) -> None:
            raise asyncio.CancelledError()

    else:
        operation_fn = AsyncMock()

    ids = HistoryInputIds.for_chat(ResolvedId("transition_delivery"))
    if operation == "new":
        controller.new_chat = operation_fn  # type: ignore[method-assign]
        input_id = ids.new
        payload: object = {"requestId": f"{operation}-{outcome}"}
    elif operation == "delete":
        controller.delete = operation_fn  # type: ignore[method-assign]
        input_id = ids.delete
        payload = {"id": "active", "requestId": f"{operation}-{outcome}"}
    elif operation == "edit":
        controller.handle_edit = operation_fn  # type: ignore[method-assign]
        input_id = ids.message_edit
        payload = {
            "index": 0,
            "content": "edited",
            "attachments": [],
            "requestId": f"{operation}-{outcome}",
        }
    elif operation == "resubmit":
        controller.handle_resubmit = operation_fn  # type: ignore[method-assign]
        input_id = ids.message_resubmit
        payload = {
            "index": 0,
            "kind": "retry",
            "requestId": f"{operation}-{outcome}",
        }
    else:
        controller.handle_navigate = operation_fn  # type: ignore[method-assign]
        input_id = ids.message_navigate
        payload = {
            "index": 0,
            "direction": "prev",
            "requestId": f"{operation}-{outcome}",
        }

    async def fail_completion(action: dict[str, Any]) -> None:
        if action["type"] == "history_transition_complete":
            raise RuntimeError("completion delivery failed")

    chat._send_action = fail_completion  # type: ignore[method-assign]
    with session_context(cast(Any, session)):
        cast(Any, session.input[input_id])._set(payload)

    if outcome == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            with reactive.isolate():
                await handlers[f"_on_{operation}"]()
    else:
        with reactive.isolate():
            await handlers[f"_on_{operation}"]()


def _registered_history_cleanups(session: Any) -> list[Callable[[], None]]:
    return [
        cb
        for cb in session.ended_callbacks
        if getattr(cb, "__name__", "") == "_on_session_end"
    ]


def test_same_id_reconstruction_tears_down_prior_history():
    session = cast(Any, _LiveSession())
    chat1 = _make_live_chat("recon", session)
    history1 = chat1.history
    assert history1._controller is not None
    on_end1 = history1._on_session_end
    assert on_end1 in session.ended_callbacks
    effects1 = list(history1._effects)
    assert len(effects1) > 0
    cancel_pending1 = MagicMock()
    history1._controller.cancel_pending = cancel_pending1  # type: ignore[method-assign]

    chat2 = _make_live_chat("recon", session)

    # The replaced history unregistered its session-end callback, ran its
    # cleanup, and destroyed its input effects...
    assert history1._on_session_end is None
    assert history1._session_end_cancel is None
    assert history1._effects == []
    assert all(e._destroyed for e in effects1)
    cancel_pending1.assert_called_once()
    assert on_end1 not in session.ended_callbacks
    # ...leaving the replacement as the sole live history registration.
    assert chat2.history._controller is not None
    assert _registered_history_cleanups(session) == [
        chat2.history._on_session_end
    ]


def test_repeated_same_id_reconstruction_retains_single_registration():
    session = cast(Any, _LiveSession())
    chats = [_make_live_chat("repeat", session) for _ in range(3)]

    for chat in chats[:-1]:
        assert chat.history._on_session_end is None
        assert chat.history._session_end_cancel is None
        assert chat.history._effects == []
    assert _registered_history_cleanups(session) == [
        chats[-1].history._on_session_end
    ]


def test_session_end_runs_history_cleanup_once():
    session = cast(Any, _LiveSession())
    chat = _make_live_chat("teardown", session)
    history = chat.history
    controller = history._controller
    assert controller is not None
    cancel_pending = MagicMock()
    controller.cancel_pending = cancel_pending  # type: ignore[method-assign]

    # Simulate session teardown: fire every registered on_ended callback.
    for cb in list(session.ended_callbacks):
        cb()

    cancel_pending.assert_called_once()
    assert history._session_end_cancel is None
    assert history._on_session_end is None
    # A later Chat.destroy() must not re-run the cleanup.
    chat.destroy()
    cancel_pending.assert_called_once()


def test_chat_destroy_without_history_start_is_safe():
    chat = _make_chat(history=False)
    chat.destroy()  # no session-level registrations to release


async def _make_initialized_live_v2_chat(
    tmp_path: Any, chat_id: str
) -> tuple[Chat, _LiveSession, _MockClient, FileConversationStore]:
    session = _LiveSession()
    client = _MockClient()
    store = FileConversationStore(tmp_path)
    with (
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            chat_id,
            client=cast(Any, client),
            history=HistoryOptions(
                store=store,
                scope="test",
                restore_mode="none",
            ),
        )
        await reactive.flush()
        await reactive.flush()
    assert chat.history._initial_history_initialized
    return chat, session, client, store


def _transcript_snapshot(chat: Chat) -> list[dict[str, Any]]:
    return [
        {
            "message": entry.message.model_dump(mode="json"),
            "icon": entry.icon,
            "status": entry.status,
            "error": deepcopy(entry.error),
            "exchange_id": entry.exchange_id,
        }
        for entry in chat._transcript.read()
    ]


async def _finish_held_clear_task(
    task: asyncio.Task[Any],
    release: asyncio.Event,
    *,
    cancel: bool = False,
) -> None:
    release.set()
    done, _ = await asyncio.wait({task}, timeout=1)
    if task not in done and cancel:
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=1)

    failure: BaseException | None = None
    if task not in done:
        failure = TimeoutError(
            "Held clear task did not finish within 1 second."
        )
    elif task.cancelled():
        if cancel:
            return
        failure = asyncio.CancelledError()
    else:
        failure = task.exception()
    if failure is None:
        return

    active_exception = sys.exc_info()[1]
    if active_exception is not None:
        raise active_exception from failure
    raise failure


@pytest.mark.anyio
async def test_finish_held_clear_task_chains_task_failure_to_body_failure() -> (
    None
):
    async def fail() -> None:
        raise RuntimeError("clear task failed")

    task = asyncio.create_task(fail())
    await asyncio.sleep(0)

    with pytest.raises(AssertionError, match="body failed") as raised:
        try:
            raise AssertionError("body failed")
        finally:
            await _finish_held_clear_task(task, asyncio.Event(), cancel=True)

    assert task.done()
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert str(raised.value.__cause__) == "clear task failed"


@pytest.mark.anyio
async def test_v2_clear_settles_terminal_response_before_clear_mutation(
    tmp_path: Any,
) -> None:
    chat, session, _, _ = await _make_initialized_live_v2_chat(
        tmp_path, "clear_terminal_settlement"
    )
    controller = chat.history._controller
    assert controller is not None
    recorder = controller._exchange_recorder
    assert recorder is not None
    partition = ConversationPartition(
        chat_id="clear_terminal_settlement", scope="test"
    )
    settlements = 0
    original_response_settled = recorder.response_settled

    async def count_settlement() -> bool:
        nonlocal settlements
        settlements += 1
        return await original_response_settled()

    recorder.response_settled = count_settlement  # type: ignore[method-assign]
    await chat._record_accepted_user_input_with_capture(
        ChatMessage(content="before clear", role="user"),
        dispatch_user_submit=False,
    )
    assert await chat._append_message_chunk(
        "", chunk="start", stream_id="terminal-stream"
    )
    assert await chat._append_message_chunk(
        "terminal response", stream_id="terminal-stream"
    )
    assert await chat._append_message_chunk(
        "", chunk="end", stream_id="terminal-stream"
    )
    assert settlements == 0
    assert len(chat._pending_response_settlements) == 1

    clear_dispatched = asyncio.Event()
    release_clear = asyncio.Event()
    original_send = session.send_custom_message

    async def hold_after_clear_dispatch(type: str, message: object) -> None:
        await original_send(type, message)
        if cast(dict[str, Any], message)["action"]["type"] == "clear":
            clear_dispatched.set()
            await release_clear.wait()

    session.send_custom_message = hold_after_clear_dispatch  # type: ignore[method-assign]
    clear_task = asyncio.create_task(chat.clear_messages())
    try:
        try:
            await asyncio.wait_for(clear_dispatched.wait(), timeout=1)

            assert settlements == 1
            assert (
                chat._transcript.read()[-1].message.content
                == "terminal response"
            )
            assert recorder.record is not None
            active_leaf = recorder.record.active_leaf
            assert active_leaf is not None
            assert recorder.record.nodes[active_leaf].status == "ok"
            stored_before_clear = await FileConversationStore(tmp_path).get(
                partition, recorder.record.id
            )
            assert stored_before_clear is not None
            assert stored_before_clear.response_count == 1
            stored_active_leaf = stored_before_clear.active_leaf
            assert stored_active_leaf is not None
            assert stored_before_clear.nodes[stored_active_leaf].status == "ok"

            await _finish_held_clear_task(clear_task, release_clear)

            assert settlements == 1
            assert chat._transcript.read() == ()
            assert [
                message["action"]
                for message in session.messages
                if message["action"]["type"] == "clear"
            ] == [{"type": "clear"}]
        finally:
            await _finish_held_clear_task(
                clear_task, release_clear, cancel=True
            )
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_v2_clear_rejects_active_stream_without_mutating_state(
    tmp_path: Any,
) -> None:
    chat, session, client, _ = await _make_initialized_live_v2_chat(
        tmp_path, "clear_active_stream"
    )
    controller = chat.history._controller
    assert controller is not None
    recorder = controller._exchange_recorder
    assert recorder is not None
    partition = ConversationPartition(
        chat_id="clear_active_stream", scope="test"
    )
    client.set_turns([{"role": "user", "content": "client turn"}])
    await chat._record_accepted_user_input_with_capture(
        ChatMessage(content="active input", role="user"),
        dispatch_user_submit=False,
    )
    assert await chat._append_message_chunk(
        "", chunk="start", stream_id="active-stream"
    )
    assert await chat._append_message_chunk(
        "partial response", stream_id="active-stream"
    )
    assert recorder.record is not None
    persisted = await FileConversationStore(tmp_path).get(
        partition, recorder.record.id
    )
    assert persisted is not None
    before = {
        "transcript": _transcript_snapshot(chat),
        "recorder": {
            "record": recorder.record.model_dump(mode="json"),
            "stream_exchanges": deepcopy(recorder._stream_exchanges),
        },
        "client_turns": deepcopy(client.get_turns()),
        "active_id": controller._active_id_now(),
        "persisted": persisted.model_dump(mode="json"),
        "wire": deepcopy(session.messages),
    }

    with pytest.raises(
        RuntimeError,
        match="Cannot clear or restore messages while a message stream",
    ):
        await chat.clear_messages()

    persisted_after = await FileConversationStore(tmp_path).get(
        partition, recorder.record.id
    )
    assert persisted_after is not None
    after = {
        "transcript": _transcript_snapshot(chat),
        "recorder": {
            "record": recorder.record.model_dump(mode="json"),
            "stream_exchanges": deepcopy(recorder._stream_exchanges),
        },
        "client_turns": deepcopy(client.get_turns()),
        "active_id": controller._active_id_now(),
        "persisted": persisted_after.model_dump(mode="json"),
        "wire": deepcopy(session.messages),
    }
    assert after == before

    await chat._append_message_chunk("", chunk="end", stream_id="active-stream")
    chat.destroy()


@pytest.mark.anyio
async def test_v2_clear_retains_input_admitted_after_clear_dispatch(
    tmp_path: Any,
) -> None:
    chat, session, _, _ = await _make_initialized_live_v2_chat(
        tmp_path, "clear_tail_exchange"
    )
    controller = chat.history._controller
    assert controller is not None
    recorder = controller._exchange_recorder
    assert recorder is not None
    partition = ConversationPartition(
        chat_id="clear_tail_exchange", scope="test"
    )
    await chat._record_accepted_user_input_with_capture(
        ChatMessage(content="old input", role="user"),
        dispatch_user_submit=False,
    )
    await chat.append_message("old response")
    await reactive.flush()
    await reactive.flush()
    assert recorder.record is not None
    old_leaf = recorder.record.active_leaf
    assert old_leaf is not None

    clear_dispatched = asyncio.Event()
    release_clear = asyncio.Event()
    original_send = session.send_custom_message

    async def hold_after_clear_dispatch(type: str, message: object) -> None:
        await original_send(type, message)
        if cast(dict[str, Any], message)["action"]["type"] == "clear":
            clear_dispatched.set()
            await release_clear.wait()

    session.send_custom_message = hold_after_clear_dispatch  # type: ignore[method-assign]
    clear_task = asyncio.create_task(chat.clear_messages())
    try:
        try:
            await asyncio.wait_for(clear_dispatched.wait(), timeout=1)

            await chat._record_accepted_user_input_with_capture(
                ChatMessage(content="tail input", role="user"),
                dispatch_user_submit=False,
            )
            assert chat._transcript.read()[-1].message.content == "tail input"
            await _finish_held_clear_task(clear_task, release_clear)
            await chat.append_message("tail response")
            await reactive.flush()
            await reactive.flush()

            assert [
                entry.message.content for entry in chat._transcript.read()
            ] == ["tail input", "tail response"]
            assert recorder.record is not None
            tail_leaf = recorder.record.active_leaf
            assert tail_leaf is not None
            assert tail_leaf != old_leaf
            tail_node = recorder.record.nodes[tail_leaf]
            assert tail_node.input is not None
            assert tail_node.input.content == "tail input"
            assert [
                message.as_stored_message().content
                for message in tail_node.messages
            ] == ["tail response"]

            persisted = await FileConversationStore(tmp_path).get(
                partition, recorder.record.id
            )
            assert persisted is not None
            persisted_tail = persisted.nodes[persisted.active_leaf]  # type: ignore[index]
            assert persisted_tail.input is not None
            assert persisted_tail.input.content == "tail input"
            assert [
                message.as_stored_message().content
                for message in persisted_tail.messages
            ] == ["tail response"]
            assert persisted.active_leaf == tail_leaf
            assert [
                message["action"]
                for message in session.messages
                if message["action"]["type"] == "clear"
            ] == [{"type": "clear"}]
        finally:
            await _finish_held_clear_task(
                clear_task, release_clear, cancel=True
            )
    finally:
        chat.destroy()
