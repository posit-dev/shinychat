"""
Test app: HTMLDependency objects must survive bookmark restore for streamed messages.

Same scenario as bookmark_html_deps, but the response is delivered via
append_message_stream() instead of append_message(). This tests whether
HTML dependencies are properly accumulated during streaming and then
included in the stored message for bookmark serialization.
"""

from pathlib import Path
from typing import Any

from htmltools import HTMLDependency, TagList, tags
from shiny.express import app_opts
from shiny.types import Jsonifiable
from shinychat.express import Chat

app_opts(bookmark_store="server")

CSS_DIR = Path(__file__).parent / "_test_assets"

custom_dep = HTMLDependency(
    name="custom-styled-card",
    version="1.0.0",
    source={"subdir": str(CSS_DIR)},
    stylesheet=[{"href": "custom.css"}],
)


class MockClient:
    """A mock client implementing the ClientWithState protocol."""

    def __init__(self) -> None:
        self.turns: list[Any] = []

    async def get_state(self) -> Jsonifiable:
        return {"version": 1, "turns": self.turns}

    async def set_state(self, state: Jsonifiable) -> None:
        assert isinstance(state, dict)
        turns = state["turns"]
        assert isinstance(turns, list)
        self.turns = turns


client = MockClient()

chat = Chat(id="chat")
chat.ui()
chat.enable_bookmarking(client, bookmark_on="response")


async def styled_response_stream(user_input: str):
    """An async generator that yields a styled HTML chunk (with HTMLDependency)."""
    yield TagList(
        custom_dep,
        tags.div(
            {"class": "custom-styled-card"},
            f"Streamed styled response to: {user_input}",
        ),
    )


@chat.on_user_submit
async def handle_user_input(user_input: str):
    client.turns.append({"role": "user", "content": user_input})
    client.turns.append(
        {"role": "assistant", "content": f"Streamed styled response to: {user_input}"}
    )
    await chat.append_message_stream(styled_response_stream(user_input))
