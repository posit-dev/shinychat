from __future__ import annotations

import asyncio
from contextlib import nullcontext
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
    InMemoryConversationStore,
)
from shinychat._history_types import new_conversation_record_v2
from shinychat.types import HistoryOptions

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

    def on_bookmarked(self, callback: Callable[[str], Any]) -> Callable[[], None]:
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
async def test_v2_stale_server_bookmark_pointer_notifies_and_keeps_draft() -> None:
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
    assert chat.messages() == ()
    notification.assert_called_once()


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
    controller.partition = ConversationPartition(chat_id="bookmark_settlement", scope="test")
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
    assert [
        message["action"]["url"] for message in session.messages
    ] == ["?_state_id_=state-first", "?_state_id_=state-second"]


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
