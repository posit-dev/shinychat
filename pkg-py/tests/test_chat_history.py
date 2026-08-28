from __future__ import annotations

from typing import Any, Awaitable, Callable, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from shiny.module import ResolvedId
from shiny.session import session_context
from shinychat import Chat
from shinychat._history import ChatHistory
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

    def is_stub_session(self) -> bool:
        return True


class _HistoryBookmark:
    def __init__(self) -> None:
        self.exclude: list[ResolvedId] = []
        self.store: str | None = None
        self._restore_context = None

    def on_bookmark(self, fn: object) -> Callable[[], None]:
        return lambda: None


class _HistoryBookmarkSession(_MockSession):
    def __init__(self) -> None:
        super().__init__()
        self.bookmark = _HistoryBookmark()

    def is_stub_session(self) -> bool:
        return False

    def root_scope(self) -> "_HistoryBookmarkSession":
        return self


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


def test_history_excludes_legacy_messages_input_from_bookmarks():
    session = cast(Any, _HistoryBookmarkSession())
    with session_context(session):
        chat = Chat("history_bookmark_exclude", client=MagicMock(), history=False)

    with (
        session_context(session),
        patch("shiny.reactive.effect", lambda fn: fn),
        patch("shinychat._history.as_turns_adapter"),
        patch("shinychat._history.resolve_store"),
    ):
        chat.history._start()

    assert chat.messages_input_id in session.bookmark.exclude


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
        self._restore_context = None


class _LiveSession(_MockSession):
    """Non-stub session mock with just enough surface to run ChatHistory._start()."""

    def __init__(self) -> None:
        super().__init__()
        self.bookmark = _MockBookmark()
        self.ended_callbacks: list[Callable[[], None]] = []

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
        pass


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
