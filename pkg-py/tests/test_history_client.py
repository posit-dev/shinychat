from __future__ import annotations

import pytest
from shinychat._history_client import (
    TurnsAdapter,
    as_turns_adapter,
    turn_fallback_markdown,
)


class DictClient:
    def __init__(self):
        self._turns: list[dict[str, object]] = []

    def get_turns(self) -> list[dict[str, object]]:
        return list(self._turns)

    def set_turns(self, turns: list[dict[str, object]]) -> None:
        self._turns = list(turns)


def test_dict_client_round_trip():
    adapter = as_turns_adapter(DictClient())
    assert isinstance(adapter, TurnsAdapter)
    adapter.set_turns_json([{"role": "user", "content": "hi"}])
    assert adapter.get_turns_json() == [{"role": "user", "content": "hi"}]


def test_chatlas_adapter_round_trip():
    chatlas = pytest.importorskip("chatlas")
    client = chatlas.ChatOpenAI(api_key="fake")
    client.set_turns(
        [
            chatlas.Turn(role="user", contents="hi"),
            chatlas.Turn(role="assistant", contents="hello"),
        ]
    )
    adapter = as_turns_adapter(client)
    dumped = adapter.get_turns_json()
    assert [d["role"] for d in dumped] == ["user", "assistant"]
    adapter.set_turns_json([])
    assert client.get_turns() == []
    adapter.set_turns_json(dumped)
    assert [t.role for t in client.get_turns()] == ["user", "assistant"]


def test_client_info_for_chatlas():
    chatlas = pytest.importorskip("chatlas")
    client = chatlas.ChatOpenAI(api_key="fake")
    info = as_turns_adapter(client).client_info()
    assert info.get("provider") and info.get("model")


def test_client_info_for_plain_client_is_empty():
    assert as_turns_adapter(DictClient()).client_info() == {}


def test_rejects_clients_without_turns():
    class Opaque: ...

    with pytest.raises(ValueError, match="get_turns"):
        as_turns_adapter(Opaque())


def test_turn_fallback_markdown_chatlas_shape():
    # chatlas serializes text contents as {"content_type": "text", "text": "..."}
    turn = {
        "role": "assistant",
        "contents": [
            {"content_type": "text", "text": "Hello "},
            {
                "content_type": "tool_request",
                "id": "x",
                "name": "f",
                "arguments": {},
            },
            {"content_type": "text", "text": "world"},
        ],
    }
    assert turn_fallback_markdown(turn) == "Hello world"


def test_turn_fallback_markdown_plain_shape():
    assert turn_fallback_markdown({"role": "user", "content": "hi"}) == "hi"
