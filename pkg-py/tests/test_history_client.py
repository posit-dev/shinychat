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


# --- get_turns_grouped --------------------------------------------------------


def test_grouped_no_tools_dict_client():
    """Non-chatlas client: every turn is its own group."""
    client = DictClient()
    client.set_turns(
        [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
        ]
    )
    adapter = as_turns_adapter(client)
    groups = adapter.get_turns_grouped()
    assert groups == [
        [{"role": "user", "content": "q"}],
        [{"role": "assistant", "content": "a"}],
    ]


def test_grouped_no_tools_chatlas():
    """Chatlas client without tool calls: every turn is its own group."""
    chatlas = pytest.importorskip("chatlas")
    client = chatlas.ChatOpenAI(api_key="fake")
    client.set_turns(
        [
            chatlas.Turn(role="user", contents="q"),
            chatlas.Turn(role="assistant", contents="a"),
        ]
    )
    adapter = as_turns_adapter(client)
    groups = adapter.get_turns_grouped()
    assert len(groups) == 2
    assert groups[0][0]["role"] == "user"
    assert groups[1][0]["role"] == "assistant"
    # Each group is a single turn
    assert len(groups[0]) == 1
    assert len(groups[1]) == 1


def test_grouped_single_tool_call_chatlas():
    """Tool exchange collapses into one assistant group."""
    chatlas = pytest.importorskip("chatlas")
    from chatlas._content import (
        ContentText,
        ContentToolRequest,
        ContentToolResult,
    )
    from chatlas._turn import AssistantTurn

    client = chatlas.ChatOpenAI(api_key="fake")
    client.set_turns(
        [
            chatlas.Turn(role="user", contents="weather?"),
            AssistantTurn(
                contents=[
                    ContentToolRequest(
                        id="t1", name="get_weather", arguments={"city": "NYC"}
                    )
                ]
            ),
            chatlas.Turn(
                role="user",
                contents=[ContentToolResult(id="t1", value="Sunny, 75F")],
            ),
            AssistantTurn(contents=[ContentText(text="It's sunny and 75F!")]),
        ]
    )
    adapter = as_turns_adapter(client)
    groups = adapter.get_turns_grouped()

    assert len(groups) == 2, "4 turns should produce 2 groups"
    # First group: the real user turn
    assert len(groups[0]) == 1
    assert groups[0][0]["role"] == "user"
    # Second group: the 3 tool-exchange turns
    assert len(groups[1]) == 3
    assert groups[1][0]["role"] == "assistant"  # tool request
    assert groups[1][1]["role"] == "user"  # tool result
    assert groups[1][2]["role"] == "assistant"  # final text

    # Flattened groups must equal the original turns (for API restoration)
    flat = [t for g in groups for t in g]
    assert flat == adapter.get_turns_json()


def test_grouped_multi_tool_call_chatlas():
    """Multiple sequential tool calls collapse into one group."""
    chatlas = pytest.importorskip("chatlas")
    from chatlas._content import (
        ContentText,
        ContentToolRequest,
        ContentToolResult,
    )
    from chatlas._turn import AssistantTurn

    client = chatlas.ChatOpenAI(api_key="fake")
    client.set_turns(
        [
            chatlas.Turn(role="user", contents="plan a trip"),
            AssistantTurn(
                contents=[
                    ContentToolRequest(id="a", name="weather", arguments={})
                ]
            ),
            chatlas.Turn(
                role="user",
                contents=[ContentToolResult(id="a", value="sunny")],
            ),
            AssistantTurn(
                contents=[
                    ContentToolRequest(id="b", name="hotels", arguments={})
                ]
            ),
            chatlas.Turn(
                role="user",
                contents=[ContentToolResult(id="b", value="Hilton")],
            ),
            AssistantTurn(
                contents=[ContentText(text="Here's your trip plan.")],
            ),
        ]
    )
    adapter = as_turns_adapter(client)
    groups = adapter.get_turns_grouped()

    assert len(groups) == 2, "6 turns should produce 2 groups"
    assert len(groups[0]) == 1  # user turn
    assert len(groups[1]) == 5  # entire tool exchange

    flat = [t for g in groups for t in g]
    assert flat == adapter.get_turns_json()
