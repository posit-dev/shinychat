from __future__ import annotations

import asyncio
import logging
import sys
import warnings
from copy import deepcopy
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import shinychat._history as history_module
import shinychat._history_plan as history_plan_module
from shiny import reactive
from shiny._utils import AsyncCallbacks, wrap_async
from shiny.module import ResolvedId
from shiny.session import session_context
from shinychat import Chat
from shinychat._history import ChatHistory, HistoryInputIds
from shinychat._history_store import (
    ConversationPartition,
    FileConversationStore,
    InMemoryConversationStore,
)
from shinychat._history_types import (
    ConversationRecordV2,
    new_conversation_record,
    new_conversation_record_v2,
)
from shinychat.types import ChatMessage, HistoryOptions
from test_history_controller import _restore_target

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

    def on_ended(
        self, callback: Callable[[], None] | Callable[[], Awaitable[None]]
    ) -> Callable[[], None]:
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
        self.ended_callbacks: list[
            Callable[[], None] | Callable[[], Awaitable[None]]
        ] = []
        self.messages: list[dict[str, Any]] = []

    def is_stub_session(self) -> bool:
        return False

    def root_scope(self) -> "_LiveSession":
        return self

    def on_ended(
        self, callback: Callable[[], None] | Callable[[], Awaitable[None]]
    ) -> Callable[[], None]:
        self.ended_callbacks.append(callback)

        def _unregister() -> None:
            if callback in self.ended_callbacks:
                self.ended_callbacks.remove(callback)

        return _unregister

    async def end(self) -> None:
        # Use Shiny's real invocation semantics, including its registration
        # order and snapshot of callbacks that cleanup can unregister.
        callbacks = AsyncCallbacks()
        for callback in self.ended_callbacks:
            callbacks.register(wrap_async(callback))
        await callbacks.invoke()

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
@pytest.mark.parametrize("target_id", [None, "c_target"])
async def test_v2_initial_readiness_suppresses_capture_until_initial_decision(
    target_id: str | None,
) -> None:
    chat_id = f"initial_capture_{target_id or 'fresh'}"
    session = _LiveSession()
    store = InMemoryConversationStore()
    history_ids = HistoryInputIds.for_chat(ResolvedId(chat_id))
    session.input[history_ids.browser_token] = reactive.Value("token")
    session.input[history_ids.current_id] = reactive.Value(target_id)
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}

    with (
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

        with warnings.catch_warnings():
            # User-input recording stays silent (direct submissions have the
            # P5.4 rejection path); scope the filter so only this call's
            # warnings become errors.
            warnings.simplefilter("error")
            await chat._record_accepted_user_input_with_capture(
                ChatMessage(content="blocked input", role="user")
            )
        with pytest.warns(UserWarning, match="The append was ignored because"):
            await chat.append_message(object())
        # The internal chunk-start guard is defense in depth for private
        # misuse; like the public stream entry points, it raises.
        with pytest.raises(
            RuntimeError, match="chat history is still initializing"
        ):
            await chat._append_message_chunk(
                "", chunk="start", stream_id="blocked-stream"
            )
        # Suppressed stream entry points now raise instead of silently
        # dismissing: the producer is unconsumed and the caller keeps
        # ownership of it (D1).
        with pytest.raises(
            RuntimeError, match="chat history is still initializing"
        ):
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
            with pytest.raises(
                RuntimeError, match="chat history is still initializing"
            ):
                await chat.append_message_stream(blocked_stream())
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

        # Client-triggered slash commands during the window are dropped
        # silently (like user input): the handler does not run and no
        # warning fires. (The effect's finally still clears the client's
        # loading indicator — pre-existing UX, not a transcript write.)
        slash_calls: list[str] = []

        @chat.slash_command("blocked", "Blocked command")
        async def _(user_text: str) -> None:
            slash_calls.append(user_text)

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            cast(Any, session.input[chat._slash_command_id])._set(
                {"command": "blocked", "userText": "nope", "echo": True}
            )
            with session_context(cast(Any, session)), reactive.isolate():
                await handlers["_on_slash_command"]()
        assert slash_calls == []
        assert chat._transcript.read() == ()

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

        # Post-admission, the same slash command runs — proving the earlier
        # suppression was the admission guard, not a dead handler.
        cast(Any, session.input[chat._slash_command_id])._set(
            {"command": "blocked", "userText": "works", "echo": True}
        )
        with session_context(cast(Any, session)), reactive.isolate():
            await handlers["_on_slash_command"]()
        assert slash_calls == ["works"]
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
            pytest.warns(
                UserWarning,
                match=r"Chat history restore failed "
                r"\(failed while replaying the conversation display\): "
                r"RuntimeError\('restore failed'\)",
            ),
        ):
            # The recoverable failure is handled at the effect boundary:
            # it must NOT escape `_init_history` (a real Shiny effect
            # routes escaped exceptions to the session-closing
            # unhandled-error path). Admission still stays closed because
            # the cleanup's authoritative history_update send failed.
            await handlers["_init_history"]()

        assert not chat.history._initial_history_initialized
        assert settled == [False]
        assert recorder.record is None
        assert controller._active_id_now() is None
        assert _history_updates(session) == []
        notifier.assert_awaited_once_with(
            recovery_incomplete=True,
            detail="failed while replaying the conversation display",
        )
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_v2_initial_readiness_flips_after_history_update_send() -> None:
    session = _LiveSession()
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}
    with (
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

        with pytest.warns(UserWarning, match="The append was ignored because"):
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

        with warnings.catch_warnings():
            warnings.simplefilter("error")
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
async def test_history_enabled_startup_advertises_completion_v2() -> None:
    session = _LiveSession()
    with session_context(cast(Any, session)):
        chat = Chat(
            "history_enabled_v2",
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
            "transition_protocol": "completion-v2",
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
    settled: list[bool] = []

    async def on_settled(restored: bool) -> None:
        settled.append(restored)

    controller.on_settled = on_settled
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    with (
        patch.object(history_plan_module, "preflight_state", fail_preflight),
        session_context(cast(Any, session)),
        reactive.isolate(),
        pytest.warns(
            UserWarning,
            match=r"Chat history restore failed \(failed while validating the saved conversation\): "
            r"ValueError\('initial preflight failed'\)",
        ),
    ):
        # Handled at the effect boundary: the failure must not escape the
        # init effect (it would close the session via Shiny's unhandled
        # error path); the chat recovers to a usable fresh state.
        await handlers["_init_history"]()

    assert settled == [False]
    # Cleanup never triggers a failure-driven hard reload (bookmark mode's
    # intentional New chat reload must not fire for failure recovery).
    navs = [
        message["action"]
        for message in session.messages
        if message["action"]["type"] == "history_navigate"
    ]
    assert all("reload" not in nav for nav in navs)
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
    notifier.assert_awaited_once_with(
        recovery_incomplete=False,
        detail="failed while validating the saved conversation",
    )
    with session_context(cast(Any, session)), reactive.isolate():
        await chat._record_accepted_user_input_with_capture(
            ChatMessage(content="fresh after preflight failure", role="user")
        )
    assert recorder.record is not None


@pytest.mark.anyio
async def test_v2_initial_restore_failure_real_effect_recovers_without_session_error(
    request: pytest.FixtureRequest,
) -> None:
    """A failed initial restore runs inside a REAL Shiny effect/flush.

    The recoverable failure is cleaned up and handled at the effect
    boundary, so it never reaches ``session._unhandled_error`` — the path
    AppSession uses to close the session on effect errors. Admission is
    released by the cleanup's authoritative history_update, exactly one
    sanitized toast is shown, and the fresh chat is usable afterwards.
    """
    chat_id = "initial_restore_real_effect"
    store = InMemoryConversationStore()
    partition = ConversationPartition(chat_id=chat_id, scope="test")
    await store.put(
        partition,
        new_conversation_record_v2(
            title="target", id="c_target", client_info={}
        ),
    )

    class _RecordingSession(_LiveSession):
        def __init__(self) -> None:
            super().__init__()
            self.unhandled_errors: list[Any] = []

        async def _unhandled_error(self, error: Any) -> None:
            self.unhandled_errors.append(error)

    session = _RecordingSession()
    history_ids = HistoryInputIds.for_chat(ResolvedId(chat_id))
    session.input[history_ids.browser_token] = reactive.Value("token")
    session.input[history_ids.current_id] = reactive.Value("c_target")

    def fail_preflight(*_args: Any, **_kwargs: Any) -> Any:
        raise ValueError("initial preflight failed")

    toasts: list[str] = []

    def record_notification(message: Any, *_args: Any, **_kwargs: Any) -> None:
        toasts.append(str(message))

    import shiny.ui as shiny_ui

    with session_context(cast(Any, session)):
        chat = Chat(
            chat_id,
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=store,
                scope="test",
                restore_mode="browser",
            ),
        )
        request.addfinalizer(chat.destroy)
        # Real effects + real flush: no captured-handler shortcut, so a
        # failure escaping the init effect would take Shiny's real
        # Effect_ error route to session._unhandled_error.
        with (
            patch.object(
                history_plan_module, "preflight_state", fail_preflight
            ),
            patch.object(shiny_ui, "notification_show", record_notification),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("ignore")
            await reactive.flush()
            await reactive.flush()

    controller = chat.history._controller
    assert controller is not None
    # The decisive assertion: the handled restore failure never reached
    # Shiny's session-fatal error path.
    assert session.unhandled_errors == []
    assert chat.history._initial_history_initialized
    updates = _history_updates(session)
    assert len(updates) == 1
    assert updates[0]["active_id"] is None
    assert toasts == [
        "Could not restore conversation: failed while validating the saved "
        "conversation. A fresh chat is ready."
    ]

    with session_context(cast(Any, session)), reactive.isolate():
        await chat._record_accepted_user_input_with_capture(
            ChatMessage(content="fresh after failed restore", role="user")
        )
    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.record is not None


@pytest.mark.anyio
async def test_v2_bookmark_initial_restore_failure_clears_url_without_reload() -> (
    None
):
    """Bookmark-mode cleanup of a failed initial restore clears the stale
    ``?_state_id_=`` query with a soft navigation — not the hard reload the
    intentional New chat path uses, which would discard the recovered
    fresh draft and the failure toast."""
    chat_id = "bookmark_restore_failure_soft_nav"
    session = _LiveSession()
    store = InMemoryConversationStore()
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
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}
    with (
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

    partition = ConversationPartition(chat_id=chat_id, scope="test")
    await store.put(
        partition,
        new_conversation_record_v2(
            title="target", id="c_target", client_info={}
        ),
    )

    def fail_preflight(*_args: Any, **_kwargs: Any) -> Any:
        raise ValueError("initial preflight failed")

    try:
        with (
            patch.object(
                history_plan_module, "preflight_state", fail_preflight
            ),
            session_context(cast(Any, session)),
            reactive.isolate(),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("ignore")
            await handlers["_init_history"]()
    finally:
        chat.destroy()

    navs = [
        message["action"]
        for message in session.messages
        if message["action"]["type"] == "history_navigate"
    ]
    assert navs == [
        {"type": "history_navigate", "url": None, "active_id": None}
    ]
    assert chat.history._initial_history_initialized


@pytest.mark.anyio
async def test_v2_bookmark_new_chat_keeps_hard_reload() -> None:
    """The intentional New chat transition in bookmark mode keeps its hard
    reload (a genuinely new chat must re-run without the restored bookmark
    state); only failure cleanup soft-navigates."""
    chat_id = "bookmark_new_chat_reload"
    session = _LiveSession()
    store = InMemoryConversationStore()
    session.bookmark.store = "server"
    session.bookmark._restore_context = MagicMock(active=True, values={})
    history_ids = HistoryInputIds.for_chat(ResolvedId(chat_id))
    # A truthy payload: the effect's @reactive.event gate req()s the input.
    session.input[history_ids.new] = reactive.Value({"ts": 1})
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}
    with (
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
        with (
            session_context(cast(Any, session)),
            reactive.isolate(),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("ignore")
            await handlers["_init_history"]()
        assert chat.history._initial_history_initialized

        session.messages.clear()
        with session_context(cast(Any, session)), reactive.isolate():
            await handlers["_on_new"]()
    finally:
        chat.destroy()

    navs = [
        message["action"]
        for message in session.messages
        if message["action"]["type"] == "history_navigate"
    ]
    assert navs == [
        {
            "type": "history_navigate",
            "url": None,
            "active_id": None,
            "reload": True,
        }
    ]


@pytest.mark.anyio
@pytest.mark.parametrize("sanitize_errors", [False, True])
async def test_v2_failed_switch_notifies_once_with_sanitized_message(
    sanitize_errors: bool,
) -> None:
    """A failed in-session switch shows exactly one toast — the cleanup's
    sanitized message — through the real ``_on_select`` boundary. The
    outer handler keeps the raw exception in its developer warning instead
    of a second toast carrying hook internals."""
    chat_id = "switch_single_notification"
    session = _LiveSession()
    session.app = SimpleNamespace(sanitize_errors=sanitize_errors)
    store = InMemoryConversationStore()
    history_ids = HistoryInputIds.for_chat(ResolvedId(chat_id))
    session.input[history_ids.browser_token] = reactive.Value("token")
    session.input[history_ids.current_id] = reactive.Value(None)
    session.input[history_ids.select] = reactive.Value({"id": "c_other"})

    handlers: dict[str, Callable[[], Awaitable[None]]] = {}
    with (
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

    partition = ConversationPartition(chat_id=chat_id, scope="test")
    await store.put(partition, _restore_target(id="c_other"))

    toasts: list[str] = []

    def record_notification(message: Any, *_args: Any, **_kwargs: Any) -> None:
        toasts.append(str(message))

    import shiny.ui as shiny_ui

    def fail_plan(*_args: Any, **_kwargs: Any) -> Any:
        raise history_plan_module.StateHookError(
            "shinychat:app_state",
            ValueError("PRIVATE_HOOK_DETAIL_SENTINEL"),
        )

    try:
        with (
            patch.object(shiny_ui, "notification_show", record_notification),
            session_context(cast(Any, session)),
            reactive.isolate(),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("ignore")
            await handlers["_init_history"]()
        assert chat.history._initial_history_initialized

        with (
            patch.object(history_plan_module, "run_plan", fail_plan),
            patch.object(shiny_ui, "notification_show", record_notification),
            session_context(cast(Any, session)),
            reactive.isolate(),
            pytest.warns(UserWarning, match="Could not open conversation"),
        ):
            await handlers["_on_select"]()
    finally:
        chat.destroy()

    assert toasts == [
        "Could not restore conversation: the 'shinychat:app_state' state "
        "entry failed to apply. A fresh chat is ready."
    ]


@pytest.mark.anyio
async def test_v2_select_missing_conversation_still_notifies_rejection() -> (
    None
):
    """Ordinary pre-restore rejections (no restore cleanup ran) keep their
    direct notification: the handled-failure marker only suppresses the
    duplicate toast after a cleanup already notified."""
    chat_id = "select_missing_notifies"
    session = _LiveSession()
    store = InMemoryConversationStore()
    history_ids = HistoryInputIds.for_chat(ResolvedId(chat_id))
    session.input[history_ids.browser_token] = reactive.Value("token")
    session.input[history_ids.current_id] = reactive.Value(None)
    session.input[history_ids.select] = reactive.Value({"id": "c_missing"})

    handlers: dict[str, Callable[[], Awaitable[None]]] = {}
    with (
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

    toasts: list[str] = []

    def record_notification(message: Any, *_args: Any, **_kwargs: Any) -> None:
        toasts.append(str(message))

    import shiny.ui as shiny_ui

    try:
        with (
            patch.object(shiny_ui, "notification_show", record_notification),
            session_context(cast(Any, session)),
            reactive.isolate(),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("ignore")
            await handlers["_init_history"]()
        assert chat.history._initial_history_initialized

        with (
            patch.object(shiny_ui, "notification_show", record_notification),
            session_context(cast(Any, session)),
            reactive.isolate(),
            pytest.warns(UserWarning, match="Could not open conversation"),
        ):
            await handlers["_on_select"]()
    finally:
        chat.destroy()

    assert toasts == ["Could not open conversation"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("operation", "method", "input_name", "payload", "prefix"),
    [
        (
            "select",
            "switch_to",
            "select",
            {"id": "c_other"},
            "Could not open conversation",
        ),
        (
            "rename",
            "rename",
            "rename",
            {"id": "c_other", "title": "renamed"},
            "Could not rename conversation",
        ),
        ("new", "new_chat", "new", {}, "Could not start a new chat"),
        (
            "delete",
            "delete",
            "delete",
            {"id": "c_other"},
            "Could not delete conversation",
        ),
        (
            "edit",
            "handle_edit",
            "message_edit",
            {"index": 0, "content": "edited"},
            "Could not edit message",
        ),
        (
            "resubmit",
            "handle_resubmit",
            "message_resubmit",
            {"index": 0, "kind": "retry"},
            "Could not retry message",
        ),
        (
            "navigate",
            "handle_navigate",
            "message_navigate",
            {"index": 0, "direction": "prev"},
            "Could not navigate messages",
        ),
    ],
)
@pytest.mark.parametrize("sanitize_errors", [False, True])
async def test_history_action_errors_keep_exception_details_out_of_notifications(
    sanitize_errors: bool,
    operation: str,
    method: str,
    input_name: str,
    payload: dict[str, Any],
    prefix: str,
    request: pytest.FixtureRequest,
) -> None:
    session = _LiveSession()
    session.app = SimpleNamespace(sanitize_errors=sanitize_errors)
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}
    with (
        patch.object(reactive, "effect", _capture_history_effects(handlers)),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            "sanitized_history_errors",
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store="memory", scope="test", restore_mode="none"
            ),
        )
    request.addfinalizer(chat.destroy)
    controller = chat.history._controller
    assert controller is not None
    assert chat.on_error == ("sanitize" if sanitize_errors else "actual")
    with session_context(cast(Any, session)), reactive.isolate():
        await handlers["_init_history"]()
    ids = HistoryInputIds.for_chat(chat.id)
    cast(Any, session.input[getattr(ids, input_name)])._set(
        {**payload, "requestId": "sanitized-error"}
    )

    with (
        patch.object(
            controller,
            method,
            AsyncMock(side_effect=ValueError("PRIVATE_DETAIL_SENTINEL")),
        ),
        patch("shiny.ui.notification_show") as notification,
        session_context(cast(Any, session)),
        reactive.isolate(),
        pytest.warns(UserWarning, match=f"{prefix}: PRIVATE_DETAIL_SENTINEL"),
    ):
        await handlers[f"_on_{operation}"]()

    notification.assert_called_once_with(prefix, type="error")


@pytest.mark.anyio
@pytest.mark.parametrize("entry_point", ["capture", "event", "slash"])
async def test_read_only_history_rejects_submission_before_acceptance(
    entry_point: str,
    request: pytest.FixtureRequest,
) -> None:
    session = _LiveSession()
    store = InMemoryConversationStore()
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}
    with (
        patch.object(reactive, "effect", _capture_history_effects(handlers)),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            "read_only_admission",
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=store, scope="test", restore_mode="none"
            ),
        )
    request.addfinalizer(chat.destroy)
    controller = chat.history._controller
    assert controller is not None
    partition = ConversationPartition(chat_id=chat.id, scope="test")
    target = _restore_target()
    target.nodes[target.root_id].state["shinychat:turns"].version = 2
    await store.put(partition, target)
    with session_context(cast(Any, session)), reactive.isolate():
        await handlers["_init_history"]()
        with pytest.warns(UserWarning, match="version"):
            await controller.switch_to(target.id)
    before = _transcript_snapshot(chat)
    messages_before = len(session.messages)
    calls: list[str] = []

    @chat.slash_command("blocked", "Blocked command")
    async def blocked(user_text: str) -> None:
        calls.append(user_text)

    with session_context(cast(Any, session)), reactive.isolate():
        if entry_point == "capture":
            await chat._record_accepted_user_input_with_capture(
                ChatMessage(content="forged", role="user")
            )
        elif entry_point == "event":
            cast(Any, session.input[chat.user_input_id])._set(
                {"text": "forged", "attachments": []}
            )
            await handlers["_on_user_input"]()
        else:
            cast(Any, session.input[chat._slash_command_id])._set(
                {"command": "blocked", "userText": "forged", "echo": False}
            )
            await handlers["_on_slash_command"]()
        assert chat._latest_user_input() is None
        assert chat._normal_user_submission() is None

    assert calls == []
    assert _transcript_snapshot(chat) == before
    assert await store.get(partition, target.id) == target
    assert not any(
        message["action"]["type"] in ("message", "chunk_start")
        for message in session.messages[messages_before:]
    )


@pytest.mark.anyio
async def test_v2_recovered_initial_error_does_not_hide_a_later_rejection(
    request: pytest.FixtureRequest,
) -> None:
    chat_id = "initial_error_notification_lifetime"
    session = _LiveSession()
    store = InMemoryConversationStore()
    ids = HistoryInputIds.for_chat(ResolvedId(chat_id))
    session.input[ids.browser_token] = reactive.Value("token")
    session.input[ids.current_id] = reactive.Value("c_target")
    session.input[ids.select] = reactive.Value({"id": "c_other"})
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}
    with (
        patch.object(reactive, "effect", _capture_history_effects(handlers)),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            chat_id,
            client=cast(Any, _MockClient()),
            history=HistoryOptions(store=store, scope="test"),
        )
    request.addfinalizer(chat.destroy)
    controller = chat.history._controller
    assert controller is not None
    await store.put(
        ConversationPartition(chat_id=chat_id, scope="test"),
        new_conversation_record_v2(
            title="target", id="c_target", client_info={}
        ),
    )
    failure = ValueError("storage unavailable")

    def fail_preflight(*_args: Any, **_kwargs: Any) -> Any:
        raise failure

    toasts: list[str] = []

    def record_notification(message: Any, *_args: Any, **_kwargs: Any) -> None:
        toasts.append(str(message))

    import shiny.ui as shiny_ui

    with (
        patch.object(history_plan_module, "preflight_state", fail_preflight),
        patch.object(shiny_ui, "notification_show", record_notification),
        session_context(cast(Any, session)),
        reactive.isolate(),
        warnings.catch_warnings(),
    ):
        warnings.simplefilter("ignore")
        await handlers["_init_history"]()
    assert len(toasts) == 1
    assert chat.history._initial_history_initialized

    # An app/store may reuse an exception instance. This later lookup has
    # not run restore cleanup and must report its own failure normally.
    with (
        patch.object(controller, "_get_record", AsyncMock(side_effect=failure)),
        patch.object(shiny_ui, "notification_show", record_notification),
        session_context(cast(Any, session)),
        reactive.isolate(),
        pytest.warns(UserWarning, match="Could not open conversation"),
    ):
        await handlers["_on_select"]()
    assert toasts == [
        "Could not restore conversation: failed while validating the saved "
        "conversation. A fresh chat is ready.",
        "Could not open conversation",
    ]


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
    assert controller._active_id_now() is None
    assert recorder.record is None
    assert target.model_dump(mode="json") == target_before
    assert await store.get(partition, target.id) is target
    updates = _history_updates(session)
    assert len(updates) == 1
    assert updates[0]["active_id"] is None
    assert updates[0]["transition_protocol"] == "completion-v2"
    assert chat.history._initial_history_initialized
    # Cancellation keeps the generic message: no detail to attribute.
    notifier.assert_awaited_once_with(recovery_incomplete=False, detail=None)

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
    # Cancellation keeps the generic message: no detail to attribute.
    notifier.assert_awaited_once_with(recovery_incomplete=False, detail=None)

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
@pytest.mark.parametrize("state_id", ["state-target", None])
async def test_v2_bookmark_switch_restore_soft_navigates_without_reload(
    state_id: str | None,
) -> None:
    """The _start()-wired on_switch_restored updates the URL in place.

    A v2 in-place switch targets the restored record's bookmark state id
    (or clears the stale query when it has none) via the existing
    history_navigate action, with no `reload` key (mfb3 / D5).
    """
    session = _LiveSession()
    session.bookmark.store = "server"

    with (
        patch.object(reactive, "effect", _capture_history_effects({})),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            "bookmark_switch_restore",
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=InMemoryConversationStore(),
                scope="test",
                restore_mode="bookmark",
            ),
        )

    controller = chat.history._controller
    assert controller is not None
    assert controller.on_switch_restored is not None

    record = new_conversation_record_v2(
        title="target",
        id="c_target",
        client_info={},
    )
    record.bookmark_state_id = state_id
    await controller.on_switch_restored(cast(Any, record))

    navs = [
        message["action"]
        for message in session.messages
        if message["action"]["type"] == "history_navigate"
    ]
    expected_url = f"?_state_id_={state_id}" if state_id is not None else None
    assert navs == [
        {
            "type": "history_navigate",
            "url": expected_url,
            "active_id": "c_target",
        }
    ]
    # Soft navigation only: no reload key, so the client replaceState's.
    assert "reload" not in navs[0]


@pytest.mark.anyio
async def test_v2_bookmark_eviction_clears_bookmark_state_for_v2_records():
    """Bookmark-mode _on_evict clears evicted v2 records' bookmark state.

    Pins the existing eviction contract (gwg3): the wired on_evict finds the
    record's bookmark_state_id — via the active recorder record when set,
    else through _get_record — and deletes that server bookmark state. A v2
    record without a state id evicts without deleting anything. Under v2 the
    recorder owns the active record, so even the active conversation goes
    through the _get_record fallback.
    """
    session = _LiveSession()
    session.bookmark.store = "server"

    store = InMemoryConversationStore()
    with (
        patch.object(reactive, "effect", _capture_history_effects({})),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            "bookmark_eviction",
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=store,
                scope="test",
                restore_mode="bookmark",
            ),
        )

    controller = chat.history._controller
    assert controller is not None
    assert controller.on_evict is not None
    recorder = controller._exchange_recorder
    assert recorder is not None
    partition = ConversationPartition(chat_id="bookmark_eviction", scope="test")
    controller.partition = partition

    # An inactive v2 record with a bookmark state id.
    inactive = new_conversation_record_v2(
        title="inactive", id="c_inactive", client_info={}
    )
    inactive.bookmark_state_id = "state-inactive"
    await store.put(partition, inactive)

    # The active v2 record: the recorder owns it.
    active = new_conversation_record_v2(
        title="active", id="c_active", client_info={}
    )
    active.bookmark_state_id = "state-active"
    recorder.record = active
    controller._active_id.set(active.id)
    await store.put(partition, active)

    # A v2 record with no bookmark state id.
    await store.put(
        partition,
        new_conversation_record_v2(title="bare", id="c_bare", client_info={}),
    )

    deleted = AsyncMock()
    with patch.object(history_module, "delete_bookmark_state", deleted):
        await controller.on_evict("c_inactive")
        deleted.assert_awaited_once_with("state-inactive")

        deleted.reset_mock()
        await controller.on_evict("c_active")
        deleted.assert_awaited_once_with("state-active")

        deleted.reset_mock()
        await controller.on_evict("c_bare")
        deleted.assert_not_awaited()


@pytest.mark.anyio
async def test_v2_bookmark_eviction_of_v1_record_clears_state():
    """Evicting a v1 record clears its bookmark state like a v2 record.

    Originally pinned as a strict xfail while the lazy v1→v2 read-gate was
    missing (shinychat#e0x2): a v1 record raised in _on_evict's _get_record
    fallback. Now the read-gate upgrades the v1 record in memory, so eviction
    resolves its bookmark_state_id exactly like a v2 record's.
    """
    session = _LiveSession()
    session.bookmark.store = "server"

    store = InMemoryConversationStore()
    with (
        patch.object(reactive, "effect", _capture_history_effects({})),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            "bookmark_eviction_v1",
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=store,
                scope="test",
                restore_mode="bookmark",
            ),
        )

    controller = chat.history._controller
    assert controller is not None
    assert controller.on_evict is not None
    partition = ConversationPartition(
        chat_id="bookmark_eviction_v1", scope="test"
    )
    controller.partition = partition

    legacy = new_conversation_record(title="legacy", id="c_v1")
    legacy.bookmark_state_id = "state-v1"
    await store.put(partition, legacy)

    deleted = AsyncMock()
    with patch.object(history_module, "delete_bookmark_state", deleted):
        await controller.on_evict("c_v1")
    deleted.assert_awaited_once_with("state-v1")


@pytest.mark.anyio
@pytest.mark.parametrize("restore_mode", ["none", "browser", "url"])
async def test_v2_non_bookmark_modes_wire_no_switch_restore_navigator(
    restore_mode: str,
) -> None:
    """Only bookmark mode wires on_switch_restored; other modes must not."""
    session = _LiveSession()

    with (
        patch.object(reactive, "effect", _capture_history_effects({})),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            f"no_switch_restore_{restore_mode}",
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=InMemoryConversationStore(),
                scope="test",
                restore_mode=cast(Any, restore_mode),
            ),
        )

    controller = chat.history._controller
    assert controller is not None
    assert controller.on_switch_restored is None


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

    with (
        patch.object(reactive, "effect", capture_effect),
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

    with (
        patch.object(reactive, "effect", capture_effect),
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
@pytest.mark.parametrize("operation", ["edit", "navigate", "resubmit"])
async def test_v2_message_actions_reject_before_initial_history_readiness(
    operation: str,
) -> None:
    session = _LiveSession()
    store = InMemoryConversationStore()
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}
    with (
        patch.object(reactive, "effect", _capture_history_effects(handlers)),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            f"forged_{operation}",
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=store, scope="test", restore_mode="none"
            ),
        )

    try:
        controller = chat.history._controller
        assert controller is not None
        recorder = controller._exchange_recorder
        assert recorder is not None
        controller.partition = ConversationPartition(
            chat_id=f"forged_{operation}", scope="test"
        )
        record = new_conversation_record_v2(
            title="before", id="c_before", client_info={}
        )
        recorder.record = record
        await store.put(controller.partition, record)
        controller.adapter.set_turns_json(
            [{"role": "user", "content": "before"}]
        )
        controller._active_id.set(record.id)
        operation_fn = AsyncMock()
        setattr(controller, f"handle_{operation}", operation_fn)

        ids = HistoryInputIds.for_chat(ResolvedId(f"forged_{operation}"))
        payload: dict[str, Any] = {
            "index": 0,
            "requestId": f"forged-{operation}",
        }
        if operation == "edit":
            payload.update(content="after", attachments=[])
        elif operation == "navigate":
            payload["direction"] = "next"
        else:
            payload["kind"] = "retry"
        input_id = getattr(ids, f"message_{operation}")
        with session_context(cast(Any, session)):
            cast(Any, session.input[input_id])._set(payload)

        record_before = record.model_copy(deep=True)
        turns_before = controller.adapter.get_turns_json()
        active_id_before = controller._active_id_now()
        transcript_before = chat._transcript.read()
        store_before = await store.list(controller.partition)

        with reactive.isolate():
            await handlers[f"_on_{operation}"]()

        operation_fn.assert_not_awaited()
        assert recorder.record == record_before
        assert controller.adapter.get_turns_json() == turns_before
        assert controller._active_id_now() == active_id_before
        assert chat._transcript.read() == transcript_before
        assert await store.list(controller.partition) == store_before

        chat.history._initial_history_initialized = True
        with reactive.isolate():
            await handlers[f"_on_{operation}"]()
        operation_fn.assert_awaited_once()
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_v2_new_chat_drawer_action_rejects_before_initial_history_readiness() -> (
    None
):
    session = _LiveSession()
    store = InMemoryConversationStore()
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}
    with (
        patch.object(reactive, "effect", _capture_history_effects(handlers)),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            "forged_new",
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=store, scope="test", restore_mode="none"
            ),
        )

    try:
        controller = chat.history._controller
        assert controller is not None
        recorder = controller._exchange_recorder
        assert recorder is not None
        controller.partition = ConversationPartition(
            chat_id="forged_new", scope="test"
        )
        record = new_conversation_record_v2(
            title="before", id="c_before", client_info={}
        )
        recorder.record = record
        await store.put(controller.partition, record)
        controller.adapter.set_turns_json(
            [{"role": "user", "content": "before"}]
        )
        controller._active_id.set(record.id)
        new_chat_fn = AsyncMock()
        controller.new_chat = new_chat_fn

        ids = HistoryInputIds.for_chat(ResolvedId("forged_new"))
        payload: dict[str, Any] = {"requestId": "forged-new"}
        with session_context(cast(Any, session)):
            cast(Any, session.input[ids.new])._set(payload)

        record_before = record.model_copy(deep=True)
        turns_before = controller.adapter.get_turns_json()
        active_id_before = controller._active_id_now()
        transcript_before = chat._transcript.read()
        store_before = await store.list(controller.partition)

        with reactive.isolate():
            await handlers["_on_new"]()

        # The request is dropped without touching the active conversation,
        # mirroring the edit/navigate/resubmit input effects...
        new_chat_fn.assert_not_awaited()
        assert recorder.record == record_before
        assert controller.adapter.get_turns_json() == turns_before
        assert controller._active_id_now() == active_id_before
        assert chat._transcript.read() == transcript_before
        assert await store.list(controller.partition) == store_before
        # ...but the transition request still completes so the drawer's
        # busy state clears.
        assert _completion_actions(session) == [
            {"type": "history_transition_complete", "requestId": "forged-new"}
        ]

        chat.history._initial_history_initialized = True
        with reactive.isolate():
            await handlers["_on_new"]()
        new_chat_fn.assert_awaited_once()
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_v2_client_new_chat_closes_record_and_renews_greeting(
    tmp_path: Any,
) -> None:
    session = _LiveSession()
    store = FileConversationStore(tmp_path)
    with (
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            "v2_new_chat_greeting",
            client=cast(Any, _MockClient()),
            greeting="## Hello",
            history=HistoryOptions(
                store=store, scope="test", restore_mode="none"
            ),
        )
        try:
            await reactive.flush()
            await reactive.flush()
            assert chat.history._initial_history_initialized
            controller = chat.history._controller
            assert controller is not None
            chat_client = chat.client
            assert chat_client is not None
            recorder = controller._exchange_recorder
            assert recorder is not None
            partition = controller.partition
            assert partition is not None

            # One completed exchange in the first conversation.
            await chat._record_accepted_user_input_with_capture(
                ChatMessage(content="first question", role="user"),
                dispatch_user_submit=False,
            )
            await chat.append_message(
                ChatMessage(content="first answer", role="assistant")
            )
            assert recorder.record is not None
            closed_id = recorder.record.id

            session.messages.clear()
            with reactive.isolate():
                await chat_client.new_chat(greeting=True)

            actions = [message["action"] for message in session.messages]
            # The clear carries the greeting flag...
            assert [a for a in actions if a["type"] == "clear"] == [
                {"type": "clear", "greeting": True}
            ]
            # ...the configured greeting is resolved again for the fresh
            # conversation (the greeting stays the ambient slot)...
            greeting_actions = [a for a in actions if a["type"] == "greeting"]
            assert [a.get("content") for a in greeting_actions] == ["## Hello"]
            # ...and the closed record stays listed with no active conversation.
            updates = [a for a in actions if a["type"] == "history_update"]
            assert updates
            assert updates[-1]["active_id"] is None
            assert [c["id"] for c in updates[-1]["conversations"]] == [
                closed_id
            ]
            reset_record = recorder.record
            assert reset_record is None
            with reactive.isolate():
                assert chat.history.conversation_id() is None

            # The greeting never entered the record: the stored closed record
            # holds exactly its own exchange.
            stored_closed = await store.get(partition, closed_id)
            assert stored_closed is not None
            assert isinstance(stored_closed, ConversationRecordV2)
            contents: list[str] = []
            for node in stored_closed.nodes.values():
                if node.input is not None:
                    contents.append(node.input.content)
                for message in node.messages:
                    contents.append(message.as_stored_message().content)
            assert contents == ["first question", "first answer"]

            # A second conversation gets a fresh record with fresh identity.
            await chat._record_accepted_user_input_with_capture(
                ChatMessage(content="second question", role="user"),
                dispatch_user_submit=False,
            )
            await chat.append_message(
                ChatMessage(content="second answer", role="assistant")
            )
            fresh = recorder.record
            assert fresh is not None
            assert fresh.id != closed_id
            fresh_contents: list[str] = []
            for node in fresh.nodes.values():
                if node.input is not None:
                    fresh_contents.append(node.input.content)
                for message in node.messages:
                    fresh_contents.append(message.as_stored_message().content)
            assert fresh_contents == ["second question", "second answer"]
        finally:
            chat.destroy()


@pytest.mark.anyio
async def test_v2_client_new_chat_rejected_before_initial_history_readiness() -> (
    None
):
    session = _LiveSession()
    with (
        patch.object(reactive, "effect", _capture_history_effects({})),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            "v2_new_chat_unresolved",
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store="memory", scope="test", restore_mode="none"
            ),
        )
        try:
            # The initial history effect is captured and never run, so the
            # v2 initial history decision is still unresolved.
            assert not chat.history._initial_history_initialized
            chat_client = chat.client
            assert chat_client is not None

            with pytest.raises(RuntimeError, match="still initializing"):
                await chat_client.new_chat()

            # Rejected before any mutation: nothing was cleared and no
            # history_update was published.
            assert list(chat._transcript.read()) == []
            assert not any(
                message["action"]["type"] == "clear"
                for message in session.messages
            )
            assert not any(
                message["action"]["type"] == "history_update"
                for message in session.messages
            )
        finally:
            chat.destroy()


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

    with (
        patch.object(reactive, "effect", capture_effect),
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
    # Model an admitted post-initialization v2 action: every message/drawer
    # transition effect drops requests that land before the initial history
    # decision, so the operation itself needs an admitted session.
    chat.history._initial_history_initialized = True

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


def test_same_id_reconstruction_tears_down_prior_history(
    monkeypatch: pytest.MonkeyPatch,
):
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
    flush_pending1 = AsyncMock()
    monkeypatch.setattr(history1, "_flush_pending", flush_pending1)

    chat2 = _make_live_chat("recon", session)

    # The replaced history unregistered its session-end callback, ran its
    # cleanup, and destroyed its input effects...
    assert history1._on_session_end is None
    assert history1._session_end_cancel is None
    assert history1._effects == []
    assert all(e._destroyed for e in effects1)
    cancel_pending1.assert_called_once()
    flush_pending1.assert_not_called()
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


@pytest.mark.anyio
async def test_session_end_runs_history_cleanup_once():
    session = cast(Any, _LiveSession())
    chat = _make_live_chat("teardown", session)
    history = chat.history
    controller = history._controller
    assert controller is not None
    cancel_pending = MagicMock()
    controller.cancel_pending = cancel_pending  # type: ignore[method-assign]

    # The first registration awaits persistence before synchronous cleanup.
    await session.end()

    cancel_pending.assert_called_once()
    assert history._session_end_cancel is None
    assert history._on_session_end is None
    # A later Chat.destroy() must not re-run the cleanup.
    chat.destroy()
    cancel_pending.assert_called_once()


@pytest.mark.anyio
async def test_session_end_waits_for_history_flush_before_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _LiveSession()
    chat = _make_live_chat("await_end_flush", cast(Any, session))
    history = chat.history
    assert history._controller is not None
    effects = list(history._effects)
    started = asyncio.Event()
    release = asyncio.Event()

    async def flush() -> None:
        started.set()
        await release.wait()

    monkeypatch.setattr(history, "_flush_pending", flush)
    cleanup = MagicMock()
    monkeypatch.setattr(history._controller, "cancel_pending", cleanup)
    ended = asyncio.create_task(session.end())
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        assert not ended.done()
        assert all(not effect._destroyed for effect in effects)
        cleanup.assert_not_called()
    finally:
        await _finish_held_clear_task(ended, release)
        chat.destroy()

    assert all(effect._destroyed for effect in effects)
    cleanup.assert_called_once()
    assert history._on_session_end is None


@pytest.mark.anyio
async def test_session_end_flush_error_is_logged_and_later_cleanup_runs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    session = _LiveSession()
    chat = _make_live_chat("failed_end_flush", cast(Any, session))
    history = chat.history
    assert history._controller is not None
    effects = list(history._effects)
    error = RuntimeError("final save failed")
    flush = AsyncMock(side_effect=error)
    monkeypatch.setattr(history, "_flush_pending", flush)
    cleanup = MagicMock()
    monkeypatch.setattr(history._controller, "cancel_pending", cleanup)
    later: list[str] = []
    session.on_ended(lambda: later.append("later cleanup"))

    # Unrelated records can carry boolean exc_info (e.g. asyncio task cleanup).
    logging.getLogger("asyncio").error("unrelated task cleanup", exc_info=False)

    # Developer reporting must not stop Shiny's callback chain, including
    # when application warning filters turn warnings into exceptions.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await session.end()

    flush.assert_awaited_once()
    assert later == ["later cleanup"]
    assert any(
        record.name == "shinychat._chat"
        and "Failed to flush captured history" in record.getMessage()
        and isinstance(record.exc_info, tuple)
        and record.exc_info[1] is error
        for record in caplog.records
    )
    assert "failed_end_flush" in caplog.text
    assert all(effect._destroyed for effect in effects)
    assert history._on_session_end is None
    cleanup.assert_called_once()
    chat.destroy()
    cleanup.assert_called_once()


@pytest.mark.anyio
async def test_session_end_cancellation_still_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _LiveSession()
    chat = _make_live_chat("cancelled_end_flush", cast(Any, session))
    history = chat.history
    assert history._controller is not None
    effects = list(history._effects)
    error = asyncio.CancelledError()
    flush = AsyncMock(side_effect=error)
    monkeypatch.setattr(history, "_flush_pending", flush)
    cleanup = MagicMock()
    monkeypatch.setattr(history._controller, "cancel_pending", cleanup)

    with pytest.raises(asyncio.CancelledError) as caught:
        await session.end()

    assert caught.value is error
    flush.assert_awaited_once()
    assert all(effect._destroyed for effect in effects)
    assert history._on_session_end is None
    cleanup.assert_called_once()
    chat.destroy()
    cleanup.assert_called_once()


@pytest.mark.anyio
async def test_session_end_without_started_history_is_safe() -> None:
    session = _LiveSession()
    with session_context(cast(Any, session)):
        chat = Chat("no_history_end", history=False)
    await session.end()
    assert chat.history._controller is None
    assert chat._cancel_session_end is None
    chat.destroy()


@pytest.mark.anyio
async def test_session_end_keeps_last_checkpoint_then_old_stream_finishes(
    tmp_path: Any,
    request: pytest.FixtureRequest,
) -> None:
    chat, session, _, _ = await _make_initialized_live_v2_chat(
        tmp_path, "terminal_end_checkpoint"
    )
    request.addfinalizer(chat.destroy)
    controller = chat.history._controller
    assert controller is not None
    partition = ConversationPartition(chat_id=chat.id, scope="test")
    with session_context(cast(Any, session)), reactive.isolate():
        await chat._record_accepted_user_input_with_capture(
            ChatMessage(content="question", role="user")
        )
        async with chat.message_stream_context() as stream:
            await stream.append("unsaved live response")
            record = controller._exchange_recorder.record
            assert record is not None and record.active_leaf is not None
            exchange_id = record.active_leaf
            before = await FileConversationStore(tmp_path).get(
                partition, record.id
            )
            assert isinstance(before, ConversationRecordV2)
            assert before.nodes[exchange_id].messages == []
            save_calls: list[str] = []

            @chat.history.on_save
            def save(values: dict[str, Any]) -> None:
                save_calls.append("called")

            effects = list(chat.history._effects)
            await session.end()
            stored = await FileConversationStore(tmp_path).get(
                partition, record.id
            )
            assert stored == before
            assert all(effect._destroyed for effect in effects)
            assert save_calls == []
        # Session destruction does not fence the old response task's terminal put.
        terminal = await FileConversationStore(tmp_path).get(
            partition, record.id
        )
        assert isinstance(terminal, ConversationRecordV2)
        assert terminal.nodes[exchange_id].status == "ok"
        assert [
            m.as_stored_message().content
            for m in terminal.nodes[exchange_id].messages
        ] == ["unsaved live response"]


def test_chat_destroy_without_history_start_is_safe():
    chat = _make_chat(history=False)
    chat.destroy()  # no session-level registrations to release


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["message", "stream"])
async def test_app_output_in_read_only_history_is_displayed_but_not_saved(
    operation: str,
    tmp_path: Any,
    request: pytest.FixtureRequest,
) -> None:
    chat, session, _, store = await _make_initialized_live_v2_chat(
        tmp_path, "read_only_app_output"
    )
    request.addfinalizer(chat.destroy)
    controller = chat.history._controller
    assert controller is not None
    partition = ConversationPartition(chat_id=chat.id, scope="test")
    target = _restore_target()
    target.nodes[target.root_id].state["shinychat:turns"].version = 2
    await store.put(partition, target)
    with session_context(cast(Any, session)), reactive.isolate():
        with pytest.warns(UserWarning, match="version"):
            await controller.switch_to(target.id)
    stored_before = await store.get(partition, target.id)
    messages_before = len(session.messages)

    with session_context(cast(Any, session)), reactive.isolate():
        if operation == "message":
            await chat.append_message("session-only app output")
        else:
            async with chat.message_stream_context() as stream:
                await stream.append("session-only app output")

    assert (
        chat._transcript.read()[-1].message.content == "session-only app output"
    )
    assert len(session.messages) > messages_before
    assert await store.get(partition, target.id) == stored_before
    assert controller._exchange_recorder.record == stored_before
    assert controller._exchange_recorder.read_only


async def _make_initialized_live_v2_chat(
    tmp_path: Any, chat_id: str
) -> tuple[Chat, _LiveSession, _MockClient, FileConversationStore]:
    session = _LiveSession()
    client = _MockClient()
    store = FileConversationStore(tmp_path)
    with (
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
    clear_task = asyncio.create_task(chat._clear_messages_screen_only())
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
            assert isinstance(stored_before_clear, ConversationRecordV2)
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
        await chat._clear_messages_screen_only()

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
    clear_task = asyncio.create_task(chat._clear_messages_screen_only())
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
            assert isinstance(persisted, ConversationRecordV2)
            assert persisted.active_leaf is not None
            persisted_tail = persisted.nodes[persisted.active_leaf]
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


@pytest.mark.anyio
async def test_v2_public_clear_messages_rejects_without_mutation(
    tmp_path: Any,
) -> None:
    chat, session, client, _ = await _make_initialized_live_v2_chat(
        tmp_path, "public_clear_guard"
    )
    try:
        controller = chat.history._controller
        assert controller is not None
        recorder = controller._exchange_recorder
        assert recorder is not None
        partition = ConversationPartition(
            chat_id="public_clear_guard", scope="test"
        )
        client.set_turns([{"role": "user", "content": "client turn"}])
        await chat.set_greeting("Stay")
        await chat._record_accepted_user_input_with_capture(
            ChatMessage(content="first question", role="user"),
            dispatch_user_submit=False,
        )
        await chat.append_message("first answer")
        await reactive.flush()
        await reactive.flush()
        assert recorder.record is not None
        persisted = await FileConversationStore(tmp_path).get(
            partition, recorder.record.id
        )
        assert persisted is not None
        before = {
            "transcript": _transcript_snapshot(chat),
            "recorder": recorder.record.model_dump(mode="json"),
            "client_turns": deepcopy(client.get_turns()),
            "active_id": controller._active_id_now(),
            "persisted": persisted.model_dump(mode="json"),
            "wire": deepcopy(session.messages),
        }

        for kwargs in ({}, {"greeting": True}):
            with pytest.raises(
                ValueError,
                match="Can't clear messages while conversation history is enabled",
            ):
                await chat.clear_messages(**kwargs)

        # Rejected before any send or mutation: the screen, the saved
        # record, the client turns (model context), the active pointer, and
        # the greeting are all untouched, and no clear action went out.
        persisted_after = await FileConversationStore(tmp_path).get(
            partition, recorder.record.id
        )
        assert persisted_after is not None
        after = {
            "transcript": _transcript_snapshot(chat),
            "recorder": recorder.record.model_dump(mode="json"),
            "client_turns": deepcopy(client.get_turns()),
            "active_id": controller._active_id_now(),
            "persisted": persisted_after.model_dump(mode="json"),
            "wire": deepcopy(session.messages),
        }
        assert after == before
        assert chat._greeting_content == "Stay"
        assert not any(
            message["action"]["type"] == "clear" for message in session.messages
        )
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_v2_public_clear_rejection_preserves_exchange_indices(
    tmp_path: Any,
) -> None:
    # The reviewer scenario: Q1/A1, a rejected Clear, then Q2/A2. Because
    # the clear never happened, the recorded display indices keep mapping
    # to the exchanges the user actually sees, and Q2 stays a child of Q1
    # rather than becoming editable against the root.
    chat, session, _, _ = await _make_initialized_live_v2_chat(
        tmp_path, "public_clear_indices"
    )
    try:
        controller = chat.history._controller
        assert controller is not None
        recorder = controller._exchange_recorder
        assert recorder is not None

        await chat._record_accepted_user_input_with_capture(
            ChatMessage(content="Q1", role="user"),
            dispatch_user_submit=False,
        )
        await chat.append_message("A1")
        await reactive.flush()
        await reactive.flush()

        with pytest.raises(
            ValueError,
            match="Can't clear messages while conversation history is enabled",
        ):
            await chat.clear_messages()

        await chat._record_accepted_user_input_with_capture(
            ChatMessage(content="Q2", role="user"),
            dispatch_user_submit=False,
        )
        await chat.append_message("A2")
        await reactive.flush()
        await reactive.flush()

        assert [entry.message.content for entry in chat._transcript.read()] == [
            "Q1",
            "A1",
            "Q2",
            "A2",
        ]
        record = recorder.record
        assert record is not None
        q1_id = record.exchange_id_for_user_message_index(0)
        q2_id = record.exchange_id_for_user_message_index(2)
        q1_node = record.nodes[q1_id]
        q2_node = record.nodes[q2_id]
        assert q1_node.input is not None
        assert q1_node.input.content == "Q1"
        assert q2_node.input is not None
        assert q2_node.input.content == "Q2"
        assert q2_node.parent_id == q1_id
        assert record.active_leaf == q2_id
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_clear_messages_clientless_still_clears() -> None:
    session = _LiveSession()
    with session_context(cast(Any, session)):
        chat = Chat("clientless_clear")
        await reactive.flush()
        await reactive.flush()
    try:
        assert chat.history._controller is None
        await chat.set_greeting("Hi")
        await chat.append_message("hello")
        assert [entry.message.content for entry in chat._transcript.read()] == [
            "hello"
        ]

        await chat.clear_messages(greeting=True)

        assert chat._transcript.read() == ()
        assert chat._greeting_content is None
        assert [
            message["action"]
            for message in session.messages
            if message["action"]["type"] == "clear"
        ] == [{"type": "clear", "greeting": True}]
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_clear_messages_history_disabled_still_clears() -> None:
    session = _LiveSession()
    client = _MockClient()
    with session_context(cast(Any, session)):
        chat = Chat(
            "no_history_clear",
            client=cast(Any, client),
            history=False,
        )
        await reactive.flush()
        await reactive.flush()
    try:
        assert chat.history._controller is None
        client.set_turns([{"role": "user", "content": "client turn"}])
        await chat.append_message("hello")
        assert [entry.message.content for entry in chat._transcript.read()] == [
            "hello"
        ]

        await chat.clear_messages()

        assert chat._transcript.read() == ()
        assert [
            message["action"]
            for message in session.messages
            if message["action"]["type"] == "clear"
        ] == [{"type": "clear"}]
        # The screen-only clear does not touch the client's turns.
        assert client.get_turns() == [
            {"role": "user", "content": "client turn"}
        ]
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_v2_switch_replay_clears_and_repopulates_screen(
    tmp_path: Any,
) -> None:
    chat, session, _, store = await _make_initialized_live_v2_chat(
        tmp_path, "switch_replay_clear"
    )
    try:
        controller = chat.history._controller
        assert controller is not None
        recorder = controller._exchange_recorder
        assert recorder is not None
        chat_client = chat.client
        assert chat_client is not None

        await chat._record_accepted_user_input_with_capture(
            ChatMessage(content="Q1", role="user"),
            dispatch_user_submit=False,
        )
        await chat.append_message("A1")
        await reactive.flush()
        await reactive.flush()
        assert recorder.record is not None
        first_id = recorder.record.id

        with reactive.isolate():
            await chat_client.new_chat()
        assert chat._transcript.read() == ()
        assert recorder.record is None

        session.messages.clear()
        await controller.switch_to(first_id)

        # The replay clears the screen via the internal primitive, then
        # repopulates it from the saved record.
        clear_actions = [
            message["action"]
            for message in session.messages
            if message["action"]["type"] == "clear"
        ]
        assert clear_actions == [{"type": "clear"}]
        assert [entry.message.content for entry in chat._transcript.read()] == [
            "Q1",
            "A1",
        ]
        assert recorder.record is not None
        assert recorder.record.id == first_id
        assert controller._active_id_now() == first_id
        stored = await store.get(
            ConversationPartition(chat_id=chat.id, scope="test"), first_id
        )
        assert stored is not None
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_v2_delete_active_conversation_clears_screen(
    tmp_path: Any,
) -> None:
    chat, session, client, store = await _make_initialized_live_v2_chat(
        tmp_path, "delete_active_clear"
    )
    try:
        controller = chat.history._controller
        assert controller is not None
        recorder = controller._exchange_recorder
        assert recorder is not None
        partition = ConversationPartition(
            chat_id="delete_active_clear", scope="test"
        )
        client.set_turns([{"role": "user", "content": "client turn"}])
        await chat._record_accepted_user_input_with_capture(
            ChatMessage(content="Q1", role="user"),
            dispatch_user_submit=False,
        )
        await chat.append_message("A1")
        await reactive.flush()
        await reactive.flush()
        assert recorder.record is not None
        record_id = recorder.record.id

        session.messages.clear()
        await controller.delete(record_id)

        assert chat._transcript.read() == ()
        assert [
            message["action"]
            for message in session.messages
            if message["action"]["type"] == "clear"
        ] == [{"type": "clear"}]
        assert recorder.record is None
        assert controller._active_id_now() is None
        assert client.get_turns() == []
        assert await store.get(partition, record_id) is None
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_v2_failed_restore_cleanup_clears_screen(
    tmp_path: Any,
) -> None:
    chat, session, client, _ = await _make_initialized_live_v2_chat(
        tmp_path, "failed_restore_clear"
    )
    try:
        controller = chat.history._controller
        assert controller is not None
        recorder = controller._exchange_recorder
        assert recorder is not None
        client.set_turns([{"role": "user", "content": "client turn"}])
        await chat._record_accepted_user_input_with_capture(
            ChatMessage(content="Q1", role="user"),
            dispatch_user_submit=False,
        )
        await chat.append_message("A1")
        await reactive.flush()
        await reactive.flush()
        assert recorder.record is not None

        session.messages.clear()
        with (
            patch("shiny.ui.notification_show"),
            pytest.warns(UserWarning, match="Chat history restore failed"),
        ):
            await controller._clear_failed_restore(
                RuntimeError("injected restore failure")
            )

        assert chat._transcript.read() == ()
        assert [
            message["action"]
            for message in session.messages
            if message["action"]["type"] == "clear"
        ] == [{"type": "clear"}]
        assert recorder.record is None
        assert controller._active_id_now() is None
        assert client.get_turns() == []
    finally:
        chat.destroy()


@pytest.mark.anyio
@pytest.mark.parametrize("entry_point", ["normal", "slash"])
@pytest.mark.parametrize("sanitize_errors", [False, True])
@pytest.mark.parametrize("recovery", ["new_chat", "corrected_state"])
@pytest.mark.parametrize("on_error", ["sanitize", "actual", "unhandled"])
@pytest.mark.parametrize("capture_source", ["turns", "system_prompt"])
async def test_capture_failure_reports_unsent_input_and_new_chat_recovers(
    tmp_path: Any,
    request: Any,
    entry_point: str,
    sanitize_errors: bool,
    recovery: str,
    on_error: Any,
    capture_source: str,
) -> None:
    chat, session, client, store = await _make_initialized_live_v2_chat(
        tmp_path, "capture_recovery"
    )
    request.addfinalizer(chat.destroy)
    session.app = SimpleNamespace(sanitize_errors=sanitize_errors)
    chat.on_error = on_error
    controller = chat.history._controller
    assert controller is not None
    recorder = controller._exchange_recorder
    if capture_source == "system_prompt":

        def retained_prompt() -> str:
            if any(
                turn.get("content") == "unreadable prompt"
                for turn in client._turns
            ):
                raise RuntimeError("retained system prompt could not be read")
            return "healthy prompt"

        controller.adapter.get_system_prompt = retained_prompt  # type: ignore[method-assign]
        recorder._register_capture_hook(
            "shinychat:system_prompt", recorder._capture_system_prompt
        )
    # Replace the built-in provider consumer with this app's dispatch callback.
    # Keep the accepted-input effects and recorder wiring real.
    next(
        effect
        for effect in chat._effects
        if effect._fn.__name__ == "handle_user_input"
    ).destroy()
    calls: list[str] = []

    @chat.on_user_submit
    async def submitted(text: str) -> None:
        calls.append(text)

    @chat.slash_command("send", "Send")
    async def slash(text: str) -> None:
        calls.append(text)

    async def submit(text: str, seq: int) -> None:
        if entry_point == "normal":
            cast(Any, session.input[chat.user_input_id])._set(
                {
                    "text": text,
                    "attachments": [],
                    "seq": seq,
                    "client_message_id": f"client-{seq}",
                }
            )
        else:
            cast(Any, session.input[chat._slash_command_id])._set(
                {
                    "command": "send",
                    "userText": text,
                    "echo": True,
                    "seq": seq,
                    "client_message_id": f"client-{seq}",
                }
            )
        await reactive.flush()

    with session_context(cast(Any, session)), reactive.isolate():
        await submit("initial", 1)
        assert calls == ["initial"]
        assert recorder.record is not None
        transcript_before = _transcript_snapshot(chat)
        prior_open_id = chat._transcript.open_exchange_id
        assert prior_open_id is not None
        seen_messages: list[Any] = []

        @reactive.effect
        def observe_messages() -> None:
            seen_messages.append(chat.messages())

        request.addfinalizer(observe_messages.destroy)
        await reactive.flush()
        assert len(seen_messages) == 1
        before = recorder.record.model_dump(mode="json")
        partition = ConversationPartition(chat_id=chat.id, scope="test")
        saved = await store.get(partition, recorder.record.id)
        assert saved is not None
        checkpoint = saved.model_dump(mode="json")
        if capture_source == "turns":
            client._turns = [{"role": "assistant", "content": object()}]
            cause = "not JSON serializable"
        else:
            client._turns = [
                {"role": "assistant", "content": "unreadable prompt"}
            ]
            cause = "retained system prompt could not be read"
        stale_turns = deepcopy(client._turns)
        notification = MagicMock()
        with patch("shiny.ui.notification_show", notification):
            for seq in (2, 3):
                with pytest.warns(UserWarning, match=cause):
                    await submit("rejected", seq)
                actions = [m["action"] for m in session.messages]
                removal = next(
                    i
                    for i, a in enumerate(actions)
                    if a == {"type": "remove_message", "id": f"client-{seq}"}
                )
                assert (
                    actions[removal + 1]["type"] == "update_exchange_metadata"
                )
                assert calls == ["initial"]
                assert _transcript_snapshot(chat) == transcript_before
                assert chat._transcript.open_exchange_id == prior_open_id
                assert len(seen_messages) == 1
                assert "rejected" not in str(chat.messages())
                assert recorder.record.model_dump(mode="json") == before
                saved = await store.get(partition, recorder.record.id)
                assert saved is not None
                assert saved.model_dump(mode="json") == checkpoint
                assert "rejected" not in str(chat.user_input())
        assert notification.call_count == 2
        report = notification.call_args.args[0]
        assert "Message not sent" in report
        assert "saved checkpoint is unchanged" in report
        assert "New chat" in report
        assert cause not in report
        if recovery == "new_chat":
            await controller.new_chat()
            assert client._turns == []
        else:
            client._turns = [{"role": "assistant", "content": "corrected"}]
        # Recovery moves the live model state past the stale captured turn
        # that triggered the failure, without replaying the rejected input.
        assert client._turns != stale_turns
        assert calls == ["initial"]  # Recovery never resubmits automatically.
        await submit("recovered", 4)
        assert calls == ["initial", "recovered"]
        assert recorder.record is not None
        assert "rejected" not in str(recorder.record.model_dump(mode="json"))
        recovered_id = chat._transcript.open_exchange_id
        assert recovered_id is not None and recovered_id != prior_open_id
        await chat.append_message("fresh response")
        saved = await store.get(partition, recorder.record.id)
        assert isinstance(saved, ConversationRecordV2)
        assert saved.nodes[recovered_id].input is not None
        assert "recovered" in str(saved.nodes[recovered_id].input)
        assert (
            saved.nodes[recovered_id]
            .messages[-1]
            .model_dump(mode="json")["segments"][0]["content"]
            == "fresh response"
        )
        assert chat._transcript.read()[-1].exchange_id == recovered_id


@pytest.mark.anyio
async def test_slash_response_capture_failure_keeps_live_error_handling(
    tmp_path: Any, request: Any
) -> None:
    chat, session, client, _ = await _make_initialized_live_v2_chat(
        tmp_path, "slash_response_capture"
    )
    request.addfinalizer(chat.destroy)
    errors = AsyncMock()
    chat._raise_exception = errors  # type: ignore[method-assign]

    @chat.slash_command("reply", "Reply")
    async def reply() -> None:
        client._turns = [{"role": "assistant", "content": object()}]

        async def response():
            yield "already dispatched reply"

        await chat.append_message_stream(response())

    with session_context(cast(Any, session)), reactive.isolate():
        notification = MagicMock()
        with patch("shiny.ui.notification_show", notification):
            cast(Any, session.input[chat._slash_command_id])._set(
                {"command": "reply", "userText": "", "echo": True}
            )
            await reactive.flush()
        notification.assert_not_called()
        errors.assert_awaited()
        assert "not JSON serializable" in str(errors.call_args.args[0])
        assert chat.user_input() is not None
        assert any(
            entry.message.content == "already dispatched reply"
            for entry in chat._transcript.read()
        )


@pytest.mark.anyio
@pytest.mark.parametrize("entry_point", ["normal", "slash"])
@pytest.mark.parametrize(
    "failure", ["first_put", "later_put", "created_update"]
)
async def test_postcommit_input_failure_keeps_shared_owner_without_dispatch(
    tmp_path: Any, request: Any, entry_point: str, failure: str
) -> None:
    chat, session, _, store = await _make_initialized_live_v2_chat(
        tmp_path, "shared_commit_failure"
    )
    request.addfinalizer(chat.destroy)
    controller = chat.history._controller
    assert controller is not None
    recorder = controller._exchange_recorder
    next(
        effect
        for effect in chat._effects
        if effect._fn.__name__ == "handle_user_input"
    ).destroy()
    dispatches: list[str] = []
    observations: list[Any] = []

    @chat.on_user_submit
    async def submitted(text: str) -> None:
        dispatches.append(text)

    @chat.slash_command("send", "Send")
    async def slash(text: str) -> None:
        dispatches.append(text)

    @reactive.effect
    def observe_messages() -> None:
        observations.append(chat.messages())

    request.addfinalizer(observe_messages.destroy)
    error = RuntimeError(f"injected {failure} failure")
    live_error = AsyncMock()
    chat._raise_exception = live_error  # type: ignore[method-assign]
    original_put = store.put
    original_update = controller.send_history_update
    with session_context(cast(Any, session)), reactive.isolate():
        await reactive.flush()
        if failure == "later_put":
            await chat._record_accepted_user_input_with_capture(
                ChatMessage(content="prior", role="user"),
                dispatch_user_submit=False,
            )
            await reactive.flush()
        if failure == "created_update":
            controller.send_history_update = AsyncMock(side_effect=error)  # type: ignore[method-assign]
        else:
            store.put = AsyncMock(side_effect=error)  # type: ignore[method-assign]
        before_observations = len(observations)
        notification = MagicMock()
        try:
            with patch("shiny.ui.notification_show", notification):
                if entry_point == "normal":
                    cast(Any, session.input[chat.user_input_id])._set(
                        {
                            "text": "committed",
                            "attachments": [],
                            "seq": 1,
                            "client_message_id": "committed-client",
                        }
                    )
                else:
                    cast(Any, session.input[chat._slash_command_id])._set(
                        {
                            "command": "send",
                            "userText": "committed",
                            "client_message_id": "committed-client",
                            "echo": True,
                        }
                    )
                # Uses Chat's real synchronous revision listener under recorder.lock.
                await asyncio.wait_for(reactive.flush(), timeout=2)
        finally:
            store.put = original_put  # type: ignore[method-assign]
            controller.send_history_update = original_update  # type: ignore[method-assign]
        live_error.assert_awaited_once_with(error)
        notification.assert_not_called()
        assert not any(
            m["action"]["type"] == "remove_message" for m in session.messages
        )
        assert dispatches == []
        published = chat.user_input()
        assert published is None or published.text == "prior"
        assert chat._normal_user_submission() is None
        assert len(observations) == before_observations + 1
        assert recorder.record is not None
        exchange_id = chat._transcript.open_exchange_id
        assert exchange_id is not None
        assert exchange_id == recorder.record.active_leaf
        accepted = chat._transcript.read()[-1]
        assert accepted.exchange_id == exchange_id
        assert recorder.record.nodes[exchange_id].input == accepted.message
        assert (
            len(
                [
                    item
                    for item in chat._transcript.read()
                    if item.exchange_id == exchange_id
                ]
            )
            == 1
        )
        await chat.append_message("independent app output")
        assert chat._transcript.read()[-1].exchange_id == exchange_id
        saved = await store.get(
            ConversationPartition(chat_id=chat.id, scope="test"),
            recorder.record.id,
        )
        assert isinstance(saved, ConversationRecordV2)
        assert saved.nodes[exchange_id].input == accepted.message
        assert (
            saved.nodes[exchange_id]
            .messages[-1]
            .model_dump(mode="json")["segments"][0]["content"]
            == "independent app output"
        )


@pytest.mark.anyio
@pytest.mark.parametrize("entry_point", ["normal", "slash"])
async def test_first_model_capture_failure_commits_neither_input_owner(
    tmp_path: Any, request: Any, entry_point: str
) -> None:
    chat, session, client, _ = await _make_initialized_live_v2_chat(
        tmp_path, "first_capture_failure"
    )
    request.addfinalizer(chat.destroy)
    controller = chat.history._controller
    assert controller is not None
    publication = AsyncMock()
    controller.on_active_id_change = publication
    recorder = controller._exchange_recorder
    client._turns = [{"role": "assistant", "content": object()}]
    with session_context(cast(Any, session)), reactive.isolate():
        notification = MagicMock()
        with (
            patch("shiny.ui.notification_show", notification),
            pytest.warns(UserWarning, match="not JSON serializable"),
        ):
            if entry_point == "normal":
                cast(Any, session.input[chat.user_input_id])._set(
                    {"text": "rejected", "attachments": [], "seq": 1}
                )
            else:
                cast(Any, session.input[chat._slash_command_id])._set(
                    {"command": "send", "userText": "rejected", "echo": True}
                )
            await reactive.flush()
        assert "Message not sent" in notification.call_args.args[0]
        assert recorder.record is None
        assert chat._transcript.read() == ()
        assert chat._transcript.open_exchange_id is None
        assert chat.messages() == ()
        assert chat.user_input() is None
        assert chat._normal_user_submission() is None

        assert (
            controller._active_id_now() is not None
        )  # Reservation, not publication.
        publication.assert_not_awaited()
        assert not any(
            m["action"]["type"] == "remove_message" for m in session.messages
        )
        await controller.new_chat()
        assert controller._active_id_now() is None


@pytest.mark.anyio
async def test_app_output_during_failed_input_put_targets_shared_committed_exchange(
    tmp_path: Any, request: Any
) -> None:
    chat, session, _, store = await _make_initialized_live_v2_chat(
        tmp_path, "blocked_input_put"
    )
    request.addfinalizer(chat.destroy)
    controller = chat.history._controller
    assert controller is not None
    recorder = controller._exchange_recorder
    putting = asyncio.Event()
    release = asyncio.Event()
    output_committed = asyncio.Event()
    original_put = store.put
    put_count = 0

    async def fail_first_put(partition: Any, record: Any) -> None:
        nonlocal put_count
        put_count += 1
        if put_count == 1:
            putting.set()
            await release.wait()
            raise RuntimeError("input put failed")
        await original_put(partition, record)

    async def observe_output(exchange_id: str | None, entry: Any) -> None:
        output_committed.set()
        await recorder.message_committed(exchange_id, entry)

    store.put = fail_first_put  # type: ignore[method-assign]
    chat._transcript._on_message_committed = observe_output
    with session_context(cast(Any, session)), reactive.isolate():
        accepting = asyncio.create_task(
            chat._record_accepted_user_input_with_capture(
                ChatMessage(content="input", role="user")
            )
        )
        appending = None
        try:
            await asyncio.wait_for(putting.wait(), timeout=2)
            assert recorder.lock.locked()
            assert recorder.record is not None
            exchange_id = chat._transcript.open_exchange_id
            assert (
                exchange_id is not None
                and exchange_id == recorder.record.active_leaf
            )
            assert chat._transcript_revision() == 1
            appending = asyncio.create_task(
                chat.append_message("concurrent app output")
            )
            await asyncio.wait_for(output_committed.wait(), timeout=2)
            assert chat._transcript.read()[-1].exchange_id == exchange_id
            assert (
                chat._transcript.open_exchange_id == recorder.record.active_leaf
            )
            release.set()
            with pytest.raises(RuntimeError, match="input put failed"):
                await accepting
            await asyncio.wait_for(appending, timeout=2)
            assert chat.user_input() is None
            assert chat._normal_user_submission() is None
            saved = await store.get(
                ConversationPartition(chat_id=chat.id, scope="test"),
                recorder.record.id,
            )
            assert isinstance(saved, ConversationRecordV2)
            assert (
                saved.nodes[exchange_id].input
                == chat._transcript.read()[0].message
            )
            assert (
                saved.nodes[exchange_id]
                .messages[-1]
                .model_dump(mode="json")["segments"][0]["content"]
                == "concurrent app output"
            )
        finally:
            release.set()
            await asyncio.gather(
                accepting,
                *([appending] if appending is not None else []),
                return_exceptions=True,
            )
            store.put = original_put  # type: ignore[method-assign]


@pytest.mark.anyio
@pytest.mark.parametrize("entry_point", ["normal", "slash"])
@pytest.mark.parametrize("failure", ["metadata", "legacy"])
async def test_capture_rejection_cleanup_survives_metadata_failure_or_legacy_input(
    tmp_path: Any, request: Any, capsys: Any, entry_point: str, failure: str
) -> None:
    chat, session, client, store = await _make_initialized_live_v2_chat(
        tmp_path, "capture_cleanup"
    )
    request.addfinalizer(chat.destroy)
    controller = chat.history._controller
    assert controller is not None
    recorder = controller._exchange_recorder
    next(
        effect
        for effect in chat._effects
        if effect._fn.__name__ == "handle_user_input"
    ).destroy()
    dispatched: list[str] = []

    @chat.on_user_submit
    async def submitted(text: str) -> None:
        dispatched.append(text)

    @chat.slash_command("send", "Send")
    async def slash(text: str) -> None:
        dispatched.append(text)

    with session_context(cast(Any, session)), reactive.isolate():
        await chat.append_message("existing checkpoint")
        await reactive.flush()
        assert recorder.record is not None
        before = recorder.record.model_dump(mode="json")
        transcript_before = _transcript_snapshot(chat)
        partition = ConversationPartition(chat_id=chat.id, scope="test")
        saved = await store.get(partition, recorder.record.id)
        assert saved is not None
        checkpoint = saved.model_dump(mode="json")
        session.messages.clear()
        client._turns = [{"role": "assistant", "content": object()}]
        payload: dict[str, Any] = (
            {"text": "rejected", "attachments": [], "seq": 1}
            if entry_point == "normal"
            else {
                "command": "send",
                "userText": "rejected",
                "echo": True,
                "seq": 1,
            }
        )
        if failure == "metadata":
            payload["client_message_id"] = "rejected-client"
        notification = MagicMock()
        with (
            patch.object(
                controller,
                "_send_exchange_metadata",
                side_effect=RuntimeError("metadata delivery failed"),
            ) as metadata,
            patch.object(controller, "_send_sibling_metadata") as siblings,
            patch("shiny.ui.notification_show", notification),
            pytest.warns(UserWarning, match="not JSON serializable"),
        ):
            input_id = (
                chat.user_input_id
                if entry_point == "normal"
                else chat._slash_command_id
            )
            cast(Any, session.input[input_id])._set(payload)
            if failure == "metadata":
                # Normal effects propagate transport failure; slash retains its
                # existing live-error wrapper. Neither claims successful delivery.
                await reactive.flush()
                assert "metadata delivery failed" in capsys.readouterr().err
                metadata.assert_awaited_once()
            else:
                await reactive.flush()
                metadata.assert_not_called()
            siblings.assert_not_called()
        actions = [message["action"] for message in session.messages]
        assert {"type": "remove_loading"} in actions
        removals = [
            action for action in actions if action["type"] == "remove_message"
        ]
        assert removals == (
            [{"type": "remove_message", "id": "rejected-client"}]
            if failure == "metadata"
            else []
        )
        reports = [call.args[0] for call in notification.call_args_list]
        unsent = [report for report in reports if "Message not sent" in report]
        assert len(unsent) == 1
        report = unsent[0]
        assert "not JSON serializable" not in report
        assert dispatched == []
        assert _transcript_snapshot(chat) == transcript_before
        assert recorder.record.model_dump(mode="json") == before
        saved = await store.get(partition, recorder.record.id)
        assert saved is not None
        assert saved.model_dump(mode="json") == checkpoint


@pytest.mark.anyio
@pytest.mark.parametrize("client_message_id", [None, "rejected-client"])
@pytest.mark.parametrize("cleanup", ["loading", "notification"])
@pytest.mark.parametrize("cancelled", [False, True])
async def test_capture_cleanup_propagates_failure_while_capture_error_is_handled(
    tmp_path: Any,
    request: Any,
    client_message_id: str | None,
    cleanup: str,
    cancelled: bool,
) -> None:
    from shinychat._history_recorder import _ModelCaptureError

    chat, session, _, _ = await _make_initialized_live_v2_chat(
        tmp_path, "handled_capture_cleanup"
    )
    request.addfinalizer(chat.destroy)
    controller = chat.history._controller
    assert controller is not None
    cleanup_error = (
        asyncio.CancelledError("cancelled cleanup")
        if cancelled
        else RuntimeError("failed cleanup")
    )
    capture_error = _ModelCaptureError("capture failed")
    capture_error.__cause__ = ValueError("private capture cause")
    with (
        session_context(cast(Any, session)),
        patch.object(chat, "_send_action") as delivery,
        patch.object(controller, "_send_exchange_metadata") as metadata,
        patch.object(controller, "_send_sibling_metadata") as siblings,
        patch.object(
            chat,
            "_remove_loading_message",
            side_effect=cleanup_error if cleanup == "loading" else None,
        ) as loading,
        patch(
            "shiny.ui.notification_show",
            side_effect=cleanup_error if cleanup == "notification" else None,
        ) as notification,
        pytest.warns(UserWarning, match="private capture cause"),
        pytest.raises(BaseException) as raised,
    ):
        # Both reactive entry points call this while handling capture failure.
        try:
            raise capture_error
        except _ModelCaptureError as e:
            await chat._handle_input_exception(e, client_message_id)
    assert raised.value is cleanup_error
    loading.assert_awaited_once()
    notification.assert_called_once()
    assert "private capture cause" not in notification.call_args.args[0]
    if client_message_id is None:
        delivery.assert_not_called()
        metadata.assert_not_called()
        siblings.assert_not_called()
    else:
        delivery.assert_awaited_once_with(
            {"type": "remove_message", "id": client_message_id}
        )
        metadata.assert_awaited_once()
        siblings.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_capture_cleanup_preserves_primary_delivery_failure_when_transport_closed(
    tmp_path: Any, request: Any, cancelled: bool
) -> None:
    from shinychat._history_recorder import _ModelCaptureError

    chat, session, _, _ = await _make_initialized_live_v2_chat(
        tmp_path, "closed_capture_transport"
    )
    request.addfinalizer(chat.destroy)
    primary = (
        asyncio.CancelledError("cancelled removal")
        if cancelled
        else RuntimeError("closed removal")
    )
    cause = ValueError("private capture cause")
    capture_error = _ModelCaptureError("capture failed")
    capture_error.__cause__ = cause
    controller = chat.history._controller
    assert controller is not None
    with (
        session_context(cast(Any, session)),
        patch.object(chat, "_send_action", side_effect=primary),
        patch.object(
            chat,
            "_remove_loading_message",
            side_effect=RuntimeError("closed loading"),
        ) as loading,
        patch(
            "shiny.ui.notification_show",
            side_effect=RuntimeError("closed notification"),
        ) as notification,
        pytest.warns(UserWarning, match="private capture cause"),
        pytest.raises(BaseException) as raised,
    ):
        try:
            raise capture_error
        except _ModelCaptureError as e:
            await chat._handle_input_exception(e, "rejected-client")
    assert raised.value is primary
    loading.assert_awaited_once()
    notification.assert_called_once()
    assert "private capture cause" not in notification.call_args.args[0]
