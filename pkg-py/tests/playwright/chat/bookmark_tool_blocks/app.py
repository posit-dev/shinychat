"""Bookmark restore with structured tool and web-search blocks."""

from typing import Any

from chatlas import Turn
from chatlas._turn import AssistantTurn
from chatlas.types import (
    ContentText,
    ContentToolRequest,
    ContentToolRequestSearch,
    ContentToolResponseSearch,
    ContentToolResult,
    WebSource,
)
from shiny import reactive
from shiny.express import input, render, ui
from shiny.types import Jsonifiable
from shinychat.express import Chat
from shinychat.types import ToolResultDisplay


def _dump(turn: Turn) -> dict[str, Any]:
    return turn.model_dump(mode="json")  # type: ignore[return-value]


class MockClient:
    """A mock client implementing ClientWithState + ClientWithTurns."""

    def __init__(self) -> None:
        self.turns: list[Any] = []

    async def get_state(self) -> Jsonifiable:
        state: Jsonifiable = {"version": 1, "turns": self.turns}
        return state

    async def set_state(self, state: Jsonifiable) -> None:
        assert isinstance(state, dict)
        turns = state["turns"]
        assert isinstance(turns, list)
        self.turns = turns

    def get_turns(self) -> list[dict[str, Any]]:
        return self.turns

    def set_turns(self, turns: list[Any]) -> None:
        self.turns = [
            t.model_dump(mode="json") if hasattr(t, "model_dump") else t
            for t in turns
        ]


client = MockClient()

chat = Chat(id="chat")
chat.ui()
chat.enable_bookmarking(client, bookmark_store="server")

ui.input_action_button("add_blocks", "Add tool + web blocks")


async def inject_tool_and_web() -> None:
    request = ContentToolRequest(
        id="bookmark-tool-1",
        name="data_tool",
        arguments={},
    )
    result = ContentToolResult(
        value="Restored tool result body",
        request=request,
        extra={
            "display": ToolResultDisplay(
                title="Looked up data",
                open=True,
            )
        },
    )
    search_request = ContentToolRequestSearch(query="best e-bike motors")
    search_response = ContentToolResponseSearch(
        sources=[
            WebSource(
                url="https://ebicycles.example/motors",
                title="Best E-Bike Motors for Commuting",
            ),
        ]
    )
    text = ContentText(text="Hub motors are ideal for flat terrain.")
    await chat.append_message_stream(
        [request, result, search_request, search_response, text]
    )
    client.turns.append(_dump(AssistantTurn(contents=[request])))
    client.turns.append(_dump(Turn(role="user", contents=[result])))
    client.turns.append(
        _dump(AssistantTurn(contents=[search_request, search_response, text]))
    )


@reactive.effect
@reactive.event(input.add_blocks)
async def _():
    await inject_tool_and_web()


@chat.on_user_submit
async def handle_user_input(user_input: str):
    client.turns.append({"role": "user", "content": user_input})
    reply = f"You said: {user_input}"
    client.turns.append({"role": "assistant", "content": reply})
    await chat.append_message(reply)


"chat.messages():"


@render.code
def message_state():
    return str(chat.messages())
