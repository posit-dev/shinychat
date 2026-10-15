from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, cast

import pytest
from shiny.types import NotifyException
from shinychat._chat_client import ChatClient, messages_to_turns
from shinychat._chat_types import ChatMessageDict
from shinychat._history import ChatHistory, HistoryController
from shinychat._history_client import TurnsAdapter
from shinychat._history_store import (
    ConversationPartition,
    InMemoryConversationStore,
)


class _Stream:
    def __init__(self, state: str = "initial") -> None:
        self.state = state

    def status(self) -> str:
        return self.state


class _TurnClient:
    def __init__(self) -> None:
        self._turns: list[Any] = []

    def get_turns(self) -> list[Any]:
        return list(self._turns)

    def set_turns(self, turns: list[Any]) -> None:
        self._turns = list(turns)


class _Chat:
    def __init__(self) -> None:
        self.latest_message_stream = _Stream()
        # The real ChatHistory namespace so the v2 admission predicate
        # (`_history_action_admitted`) exercised by ChatClient.new_chat()
        # runs the production logic against this fake chat.
        self.history = ChatHistory(cast(Any, self))
        self.messages: list[dict[str, Any]] = []
        self.clear_calls: list[bool] = []
        self.actions: list[dict[str, Any]] = []
        self._session = None

    def _messages_for_bookmark(self) -> list[dict[str, Any]]:
        return self.messages

    async def clear_messages(self, *, greeting: bool = False) -> None:
        self.clear_calls.append(greeting)
        self.messages.clear()

    async def append_message(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    async def _send_action(self, action: dict[str, Any]) -> None:
        self.actions.append(action)

    @asynccontextmanager
    async def _destructive_history_mutation(self, *, block_input: bool = False):
        del block_input
        yield


def _ui_message(role: str, content: str) -> dict[str, Any]:
    return {
        "role": role,
        "segments": [{"content": content, "content_type": "markdown"}],
    }


async def _make_history_chat() -> tuple[
    ChatClient, _Chat, _TurnClient, InMemoryConversationStore
]:
    raw_client = _TurnClient()
    chat = _Chat()
    store = InMemoryConversationStore()
    controller = HistoryController(
        chat=chat,  # type: ignore[arg-type]
        adapter=TurnsAdapter(raw_client),
        store=store,
        title_fn=None,
        title_enabled=False,
        client=raw_client,
    )
    controller.partition = ConversationPartition(
        chat_id="chat", scope="test-scope"
    )
    chat.history._controller = controller
    # The v2 admission predicate treats a chat as unresolved until the
    # initial history decision completes; model a post-init chat.
    chat.history._initial_history_initialized = True
    return (
        ChatClient(chat=cast(Any, chat), client=cast(Any, raw_client)),
        chat,
        raw_client,
        store,
    )


def _set_exchange(
    raw_client: _TurnClient, chat: _Chat, question: str, answer: str
) -> None:
    raw_client.set_turns(
        [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
    )
    chat.messages = [
        _ui_message("user", question),
        _ui_message("assistant", answer),
    ]


@pytest.mark.anyio
async def test_history_disabled_clear_keeps_legacy_modes():
    raw_client = _TurnClient()
    chat = _Chat()
    client = ChatClient(chat=cast(Any, chat), client=cast(Any, raw_client))
    messages: list[ChatMessageDict] = [{"role": "user", "content": "seed"}]
    old_messages: list[ChatMessageDict] = [{"role": "user", "content": "old"}]
    raw_client.set_turns(messages_to_turns(old_messages))
    chat.messages = [_ui_message("assistant", "old")]

    await client.clear(messages=messages, greeting=True, client_history="set")

    assert chat.clear_calls == [True]
    assert chat.messages == [messages[0]]
    assert raw_client.get_turns() == messages_to_turns(messages)


@pytest.mark.anyio
async def test_new_chat_requires_conversation_history():
    raw_client = _TurnClient()
    chat = _Chat()
    client = ChatClient(chat=cast(Any, chat), client=cast(Any, raw_client))

    with pytest.raises(ValueError, match="conversation history"):
        await client.new_chat()


@pytest.mark.anyio
async def test_v2_new_chat_rejects_an_in_flight_response():
    client, chat, raw_client, _store = await _make_history_chat()
    chat.latest_message_stream.state = "running"
    turns = [{"role": "user", "content": "question"}]
    raw_client.set_turns(turns)

    with pytest.raises(NotifyException, match="Can't start a new chat while"):
        await client.new_chat()

    assert raw_client.get_turns() == turns
    assert chat.clear_calls == []


@pytest.mark.anyio
async def test_v2_new_chat_rejected_while_initial_history_unresolved():
    client, chat, raw_client, _store = await _make_history_chat()
    chat.history._initial_history_initialized = False
    _set_exchange(raw_client, chat, "question", "answer")
    before_turns = raw_client.get_turns()

    with pytest.raises(RuntimeError, match="still initializing"):
        await client.new_chat()

    # Rejected before any mutation: turns, rendered messages, and the client
    # turns are untouched, and no history_update was published.
    assert raw_client.get_turns() == before_turns
    assert chat.clear_calls == []
    assert chat.messages
    assert not any(
        action.get("type") == "history_update" for action in chat.actions
    )


@pytest.mark.anyio
async def test_v2_new_chat_clears_state_after_initial_history_resolves():
    client, chat, raw_client, _store = await _make_history_chat()
    controller = chat.history._controller
    assert controller is not None
    _set_exchange(raw_client, chat, "question", "answer")

    await client.new_chat(greeting=True)

    assert chat.clear_calls == [True]
    assert raw_client.get_turns() == []
    assert chat.messages == []
    assert controller._active_id_now() is None
    assert any(
        action.get("type") == "history_update"
        and action.get("active_id") is None
        and action.get("transition_protocol") == "completion-v2"
        for action in chat.actions
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"messages": [{"role": "user", "content": "seed"}]},
        {
            "messages": [{"role": "user", "content": "seed"}],
            "client_history": "set",
        },
        {"client_history": "set"},
        {"client_history": "append"},
        {"client_history": "keep"},
    ],
)
async def test_v2_clear_rejects_history_managed_chats(kwargs: dict[str, Any]):
    client, chat, raw_client, _store = await _make_history_chat()
    _set_exchange(raw_client, chat, "question", "answer")
    before_turns = raw_client.get_turns()

    with pytest.raises(ValueError, match="new_chat"):
        await client.clear(**kwargs)  # type: ignore[arg-type]

    assert raw_client.get_turns() == before_turns
    assert chat.clear_calls == []
