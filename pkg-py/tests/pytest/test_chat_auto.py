from __future__ import annotations

import asyncio
import threading
from typing import Any, cast

import pytest
from htmltools import tags
from shiny import Inputs, Session
from shiny.module import ResolvedId
from shiny.session import session_context
from shinychat import Chat, chat_ui
from shinychat._chat_client import ChatClient, messages_to_turns
from shinychat._chat_types import ChatMessageDict

# ---------------------------------------------------------------------------
# Test session / mock client helpers
# ---------------------------------------------------------------------------


class _MockSession:
    ns: ResolvedId = ResolvedId("")
    app: object = None
    id: str = "mock-session"
    input: Inputs

    def __init__(self) -> None:
        self.input = Inputs({}, ns=ResolvedId)

    def on_ended(self, callback: object) -> None:
        pass

    def on_destroy(self, callback: object) -> None:
        pass

    def _increment_busy_count(self) -> None:
        pass

    def is_stub_session(self) -> bool:
        return True


test_session = cast(Session, _MockSession())


def _run_async(coro_fn: Any) -> None:
    """Run an async function in a separate thread to avoid event loop conflicts."""
    exc: list[BaseException] = []

    def _target() -> None:
        try:
            asyncio.run(coro_fn())
        except BaseException as err:
            exc.append(err)

    thread = threading.Thread(target=_target)
    thread.start()
    thread.join()
    if exc:
        raise exc[0]


class MockClient:
    """Minimal chatlas-like client for unit testing."""

    def __init__(
        self,
        *,
        turns: list[Any] | None = None,
        system_prompt: str | None = None,
        tools: list[Any] | None = None,
    ) -> None:
        self._turns: list[Any] = turns if turns is not None else []
        self.system_prompt: str | None = system_prompt
        self._tools: list[Any] = tools if tools is not None else []

    def get_turns(self) -> list[Any]:
        return list(self._turns)

    def set_turns(self, turns: list[Any]) -> None:
        self._turns = list(turns)

    def get_tools(self) -> list[Any]:
        return list(self._tools)

    def set_tools(self, tools: list[Any]) -> None:
        self._tools = list(tools)


class _MockStreamTask:
    def __init__(self, status: str = "initial") -> None:
        self._status = status

    def status(self) -> str:
        return self._status


class _StubChat:
    def __init__(self, *, stream_status: str = "initial") -> None:
        self.latest_message_stream = _MockStreamTask(stream_status)
        self.clear_calls: list[bool] = []
        self.appended_messages: list[ChatMessageDict] = []

    async def clear_messages(self, *, greeting: bool = False) -> None:
        self.clear_calls.append(greeting)

    async def append_message(self, message: ChatMessageDict) -> None:
        self.appended_messages.append(message)


def make_chat() -> tuple[Chat, MockClient]:
    """Return (Chat, MockClient) where Chat is wired up with client=."""
    mock = MockClient()
    with session_context(test_session):
        chat = Chat("test", client=cast(Any, mock))  # type: ignore[arg-type]
    return chat, mock


# ---------------------------------------------------------------------------
# ChatClient construction via Chat(client=)
# ---------------------------------------------------------------------------


def test_client_is_none_without_client():
    with session_context(test_session):
        chat = Chat("test_no_client")
    assert chat.client is None


def test_client_is_chat_client_with_client():
    chat, _ = make_chat()
    assert isinstance(chat.client, ChatClient)


def test_client_value_returns_raw_client():
    chat, mock = make_chat()
    assert chat.client is not None
    assert chat.client.value is mock


# ---------------------------------------------------------------------------
# ChatClient._swap_client — sync / no-sync
# ---------------------------------------------------------------------------


def test_set_sync_copies_state():
    mock_old = MockClient(
        turns=["turn1"],
        system_prompt="be helpful",
        tools=["tool_a"],
    )
    mock_new = MockClient()

    with session_context(test_session):
        chat = Chat("test_sync", client=cast(Any, mock_old))  # type: ignore[arg-type]

    assert chat.client is not None
    chat.client._swap_client(cast(Any, mock_new), sync=True)

    assert mock_new.get_turns() == ["turn1"]
    assert mock_new.system_prompt == "be helpful"
    assert mock_new.get_tools() == ["tool_a"]


def test_set_no_sync_skips_copy():
    mock_old = MockClient(
        turns=["turn1"],
        system_prompt="be helpful",
        tools=["tool_a"],
    )
    mock_new = MockClient()

    with session_context(test_session):
        chat = Chat("test_nosync", client=cast(Any, mock_old))  # type: ignore[arg-type]

    assert chat.client is not None
    chat.client._swap_client(cast(Any, mock_new), sync=False)

    assert mock_new.get_turns() == []
    assert mock_new.system_prompt is None
    assert mock_new.get_tools() == []


def test_set_skips_none_system_prompt():
    """A None system_prompt on the old client should not overwrite non-None on the new one."""
    mock_old = MockClient(system_prompt=None)
    mock_new = MockClient(system_prompt="keep me")

    with session_context(test_session):
        chat = Chat("test_sp", client=cast(Any, mock_old))  # type: ignore[arg-type]

    assert chat.client is not None
    chat.client._swap_client(cast(Any, mock_new), sync=True)

    # system_prompt should be untouched because old had None
    assert mock_new.system_prompt == "keep me"


# ---------------------------------------------------------------------------
# ChatClient.clear — validation
# ---------------------------------------------------------------------------


def test_clear_rejects_set_without_messages():
    chat, _ = make_chat()
    assert chat.client is not None

    with pytest.raises(ValueError, match="messages.*must be provided"):

        async def _run() -> None:
            assert chat.client is not None
            await chat.client.clear(client_history="set")

        _run_async(_run)


def test_clear_rejects_append_without_messages():
    chat, _ = make_chat()
    assert chat.client is not None

    with pytest.raises(ValueError, match="messages.*must be provided"):

        async def _run() -> None:
            assert chat.client is not None
            await chat.client.clear(client_history="append")

        _run_async(_run)


def test_clear_rejects_messages_with_clear():
    chat, _ = make_chat()
    assert chat.client is not None

    msgs: list[ChatMessageDict] = [{"content": "hi", "role": "user"}]
    with pytest.raises(ValueError, match='only valid with `client_history="set"'):

        async def _run() -> None:
            assert chat.client is not None
            await chat.client.clear(messages=msgs, client_history="clear")

        _run_async(_run)


def test_clear_rejects_messages_with_keep():
    chat, _ = make_chat()
    assert chat.client is not None

    msgs: list[ChatMessageDict] = [{"content": "hi", "role": "user"}]
    with pytest.raises(ValueError, match='only valid with `client_history="set"'):

        async def _run() -> None:
            assert chat.client is not None
            await chat.client.clear(messages=msgs, client_history="keep")

        _run_async(_run)


def test_clear_rejects_invalid_client_history():
    chat, _ = make_chat()
    assert chat.client is not None

    with pytest.raises(ValueError, match="not valid"):

        async def _run() -> None:
            assert chat.client is not None
            await chat.client.clear(client_history="bogus")  # type: ignore[arg-type]

        _run_async(_run)


def test_clear_rejects_when_stream_is_running():
    chat = _StubChat(stream_status="running")
    client = ChatClient(chat=cast(Any, chat), client=cast(Any, MockClient()))

    with pytest.raises(RuntimeError, match="response stream is running"):

        async def _run() -> None:
            await client.clear()

        _run_async(_run)

    assert chat.clear_calls == []
    assert chat.appended_messages == []


# ---------------------------------------------------------------------------
# messages_to_turns helper
# ---------------------------------------------------------------------------


def test_messages_to_turns_basic():
    msgs: list[ChatMessageDict] = [
        {"content": "hi", "role": "user"},
        {"content": "hello", "role": "assistant"},
    ]
    turns = messages_to_turns(msgs)
    assert len(turns) == 2
    assert turns[0].role == "user"
    assert turns[1].role == "assistant"


def test_messages_to_turns_empty():
    assert messages_to_turns([]) == []


def test_messages_to_turns_defaults_to_assistant():
    msgs: list[ChatMessageDict] = [{"content": "x", "role": "assistant"}]
    turns = messages_to_turns(msgs)
    assert turns[0].role == "assistant"


# ---------------------------------------------------------------------------
# chat_ui helpers
# ---------------------------------------------------------------------------


def test_chat_ui_with_enable_cancel():
    tag = chat_ui("myid", enable_cancel=True)
    html = tag.get_html_string()
    assert 'enable-cancel="true"' in html


def test_chat_ui_enable_cancel_false_is_explicit():
    # Explicit False must be distinguishable from "unset" in the DOM so the
    # client can veto a `client=` auto-enable.
    tag = chat_ui("myid", enable_cancel=False)
    html = tag.get_html_string()
    assert 'enable-cancel="false"' in html


def test_chat_ui_enable_cancel_unset_omits_attribute():
    # Unset (the default) renders no attribute, signalling "no preference".
    tag = chat_ui("myid")
    html = tag.get_html_string()
    assert "enable-cancel" not in html


def test_chat_ui_forwards_kwargs():
    icon = tags.span("🤖")
    tag = chat_ui(
        "myid",
        placeholder="Ask me anything",
        height="400px",
        greeting="Hello!",
        footer=tags.p("footer text"),
        icon_assistant=icon,
    )
    html = tag.get_html_string()
    assert "Ask me anything" in html
    assert "400px" in html
    assert "Hello!" in html
    assert "footer text" in html


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------


def test_public_exports() -> None:
    from shinychat.types import ChatClient as CC

    assert CC is ChatClient
