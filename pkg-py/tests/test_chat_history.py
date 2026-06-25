from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

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

    def on_ended(self, callback: object) -> None:
        pass

    def on_destroy(self, callback: object) -> None:
        pass

    def _increment_busy_count(self) -> None:
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
