from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from shinychat._chat_client import ChatClient, messages_to_turns
from shinychat._chat_types import ChatMessageDict
from shinychat._history import HistoryController
from shinychat._history_client import TurnsAdapter
from shinychat._history_store import (
    ConversationPartition,
    InMemoryConversationStore,
)


class _Stream:
    def status(self) -> str:
        return "initial"


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
        self.history = SimpleNamespace(_controller=None)
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
async def test_history_aware_clear_saves_and_separates_conversations():
    client, chat, raw_client, store = await _make_history_chat()
    controller = chat.history._controller
    assert controller is not None

    _set_exchange(raw_client, chat, "first question", "first answer")
    await controller.on_response()
    first = controller.record
    assert first is not None
    first_id = first.id
    first_snapshot = first.model_dump(mode="json")

    await client.clear(greeting=True)

    assert chat.clear_calls == [True]
    assert raw_client.get_turns() == []
    assert chat.messages == []
    assert controller.record is None
    assert controller._active_id_now() is None
    assert any(
        action.get("type") == "history_update"
        and action.get("active_id") is None
        for action in chat.actions
    )

    _set_exchange(raw_client, chat, "second question", "second answer")
    await controller.on_response()
    second = controller.record
    assert second is not None
    assert second.id != first_id
    assert first.model_dump(mode="json") == first_snapshot

    saved_first = await store.get(controller.partition, first_id)
    assert saved_first is not None
    assert saved_first.model_dump(mode="json") == first_snapshot


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"messages": [{"role": "user", "content": "seed"}]},
            "messages.*conversation history",
        ),
        (
            {
                "messages": [{"role": "user", "content": "seed"}],
                "client_history": "set",
            },
            "messages.*conversation history",
        ),
        (
            {"client_history": "set"},
            "client_history.*clear",
        ),
        (
            {"client_history": "append"},
            "client_history.*clear",
        ),
        (
            {"client_history": "keep"},
            "client_history.*clear",
        ),
    ],
)
async def test_history_aware_clear_rejects_advanced_modes(
    kwargs: dict[str, Any], message: str
):
    client, chat, raw_client, _store = await _make_history_chat()
    _set_exchange(raw_client, chat, "question", "answer")
    before_turns = raw_client.get_turns()

    with pytest.raises(ValueError, match=message):
        await client.clear(**kwargs)  # type: ignore[arg-type]

    assert raw_client.get_turns() == before_turns
    assert chat.clear_calls == []


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
