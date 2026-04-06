"""
Test app: HTMLDependency objects must be re-sent during bookmark restore.

When a chat message includes HTML with an HTMLDependency (e.g., tool result
styling), the CSS/JS is loaded on the client via renderDependenciesAsync().
On bookmark restore, the message HTML is restored but the dependency must also
be re-sent so the styling takes effect.
"""

from pathlib import Path
from typing import Any

from htmltools import HTMLDependency, TagList, tags
from shiny.express import app_opts
from shiny.types import Jsonifiable
from shinychat.express import Chat

app_opts(bookmark_store="server")

# Create a CSS file for the HTMLDependency
CSS_DIR = Path(__file__).parent / "_test_assets"
CSS_DIR.mkdir(exist_ok=True)
(CSS_DIR / "custom.css").write_text(
    ".custom-styled-card { border: 3px solid red; padding: 12px; background: #fff0f0; }"
)

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


@chat.on_user_submit
async def handle_user_input(user_input: str):
    client.turns.append({"role": "user", "content": user_input})
    styled_message = TagList(
        custom_dep,
        tags.div(
            {"class": "custom-styled-card"},
            f"Styled response to: {user_input}",
        ),
    )
    client.turns.append(
        {"role": "assistant", "content": f"Styled response to: {user_input}"}
    )
    await chat.append_message(styled_message)
