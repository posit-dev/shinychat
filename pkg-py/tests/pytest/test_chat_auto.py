from __future__ import annotations

import pytest
from typing import cast

from htmltools import Tag, tags
from shiny import Session
from shiny.module import ResolvedId
from shiny.session import session_context
from shinychat import Chat, ChatAutoServer, chat_auto_ui
from shinychat._chat_auto import messages_to_turns


class _MockSession:
    ns: ResolvedId = ResolvedId("")
    app: object = None
    id: str = "mock-session"

    def on_ended(self, callback: object) -> None:
        pass

    def on_destroy(self, callback: object) -> None:
        pass

    def _increment_busy_count(self) -> None:
        pass

    def is_stub_session(self) -> bool:
        return True


test_session = cast(Session, _MockSession())


class MockClient:
    def __init__(self) -> None:
        self._turns: list[object] = []
        self.system_prompt: str | None = None
        self._tools: list[object] = []

    def get_turns(self) -> list[object]:
        return list(self._turns)

    def set_turns(self, turns: list[object]) -> None:
        self._turns = list(turns)

    def get_tools(self) -> list[object]:
        return list(self._tools)

    def set_tools(self, tools: list[object]) -> None:
        self._tools = list(tools)


def make_auto(
    client: MockClient | None = None,
) -> tuple[ChatAutoServer, MockClient]:
    client = client or MockClient()
    with session_context(test_session):
        chat = Chat("test")
    auto = ChatAutoServer(chat=chat, client=client)
    return auto, client


# ---------------------------------------------------------------------------
# chat_auto_ui()
# ---------------------------------------------------------------------------


def test_chat_auto_ui_sets_id_and_enables_cancel():
    with session_context(test_session):
        result = chat_auto_ui("myid")
    assert isinstance(result, Tag)
    html = result.get_html_string()
    assert 'id="myid"' in html
    assert "enable-cancel" in html


def test_chat_auto_ui_forwards_kwargs():
    with session_context(test_session):
        result = chat_auto_ui(
            "myid",
            placeholder="Ask me anything...",
            height="400px",
            greeting="Hello there!",
            footer=tags.div("my footer"),
            icon_assistant=tags.span("bot"),
        )
    html = result.get_html_string()
    assert "Ask me anything..." in html
    assert "400px" in html
    assert "Hello there!" in html
    assert "my footer" in html
    assert "bot" in html


# ---------------------------------------------------------------------------
# ChatAutoServer properties
# ---------------------------------------------------------------------------


def test_chat_and_client_properties():
    client = MockClient()
    auto, _ = make_auto(client)
    assert auto.chat is auto._chat
    assert auto.client is client


# ---------------------------------------------------------------------------
# _swap_client
# ---------------------------------------------------------------------------


def test_swap_client_sync_copies_state():
    auto, old = make_auto()
    old._turns = ["t1", "t2"]
    old.system_prompt = "Be helpful"
    old._tools = ["tool_a"]

    new = MockClient()
    with session_context(test_session):
        auto._swap_client(new, sync=True)

    assert auto.client is new
    assert new._turns == ["t1", "t2"]
    assert new.system_prompt == "Be helpful"
    assert new._tools == ["tool_a"]


def test_swap_client_no_sync_skips_copy():
    auto, old = make_auto()
    old._turns = ["t1"]
    old.system_prompt = "Be helpful"
    old._tools = ["tool_a"]

    new = MockClient()
    with session_context(test_session):
        auto._swap_client(new, sync=False)

    assert auto.client is new
    assert new._turns == []
    assert new.system_prompt is None
    assert new._tools == []


def test_swap_client_skips_none_system_prompt():
    auto, old = make_auto()
    old.system_prompt = None

    new = MockClient()
    new.system_prompt = "Keep me"
    with session_context(test_session):
        auto._swap_client(new, sync=True)

    assert new.system_prompt == "Keep me"


# ---------------------------------------------------------------------------
# clear() — validation
# ---------------------------------------------------------------------------


def test_clear_rejects_set_without_messages():
    import asyncio

    auto, _ = make_auto()
    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(ValueError, match="client_history='set'"):
            loop.run_until_complete(auto.clear(client_history="set"))
    finally:
        loop.close()


def test_clear_rejects_append_without_messages():
    import asyncio

    auto, _ = make_auto()
    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(ValueError, match="client_history='append'"):
            loop.run_until_complete(auto.clear(client_history="append"))
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# messages_to_turns
# ---------------------------------------------------------------------------


def test_messages_to_turns_basic():
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
        {"role": "user", "content": "bye"},
    ]
    turns = messages_to_turns(msgs)

    assert len(turns) == 3
    assert turns[0].role == "user"
    assert turns[0].text == "hello"
    assert turns[1].role == "assistant"
    assert turns[1].text == "hi there"
    assert turns[2].role == "user"
    assert turns[2].text == "bye"


def test_messages_to_turns_empty():
    assert messages_to_turns([]) == []


def test_messages_to_turns_defaults_to_assistant():
    turns = messages_to_turns([{"content": "no role"}])
    assert turns[0].role == "assistant"
    assert turns[0].text == "no role"


# ---------------------------------------------------------------------------
# tagify
# ---------------------------------------------------------------------------


def test_tagify_raises_without_tag():
    auto, _ = make_auto()
    with pytest.raises(RuntimeError, match="tagify"):
        auto.tagify()


def test_tagify_delegates_to_tag():
    auto, _ = make_auto()
    with session_context(test_session):
        tag = chat_auto_ui("test")
    auto._tag = tag
    result = auto.tagify()
    assert result is not None


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


def test_public_exports():
    from shinychat import ChatAutoServer, chat_auto_server, chat_auto_ui
    from shinychat.types import ChatAutoServer as TypesChatAutoServer

    assert callable(chat_auto_ui)
    assert callable(chat_auto_server)
    assert ChatAutoServer is TypesChatAutoServer
