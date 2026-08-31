"""Bookmark restore with structured tool and web-search blocks.

This app combines:
  * Bookmarking enabled (MockClient + bookmark_store="server"), mirroring
    chat/bookmark/app.py — but the MockClient also implements the
    ClientWithTurns protocol (get_turns/set_turns), like a real chatlas
    client, so restore exercises the turns-based path: the UI is re-derived
    from the client's turns server-side, reconstructing structured blocks.
  * A button that injects a tool request+result pair (framed_result pattern)
    and a web search burst (web_citations pattern: ContentToolRequestSearch +
    ContentToolResponseSearch with sources), recording the equivalent
    chatlas-shaped turns in the client the way a real tool loop would.

On bookmark restore, the tool group/card and the web activity must re-render
in the restored transcript, re-derived from the turns.
"""

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
    """Inject a tool request+result pair and a web search burst."""
    # Tool request + result (framed_result pattern)
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
    # Web search burst (web_citations pattern)
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
    # One stream for the whole injection: each completed assistant stream
    # triggers an auto-bookmark (bookmark_on="response"), so two streams
    # would race the test's bookmark-URL capture (roborev 1072).
    await chat.append_message_stream(
        [request, result, search_request, search_response, text]
    )
    # Record the exchange as turns the way a real chatlas tool loop would
    # (assistant request turn, then a user-role tool-result turn, then the
    # assistant web/text turn).
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
    # Track turns in mock client (mimicking what a real LLM client does)
    client.turns.append({"role": "user", "content": user_input})
    reply = f"You said: {user_input}"
    client.turns.append({"role": "assistant", "content": reply})
    await chat.append_message(reply)


"chat.messages():"


@render.code
def message_state():
    return str(chat.messages())
