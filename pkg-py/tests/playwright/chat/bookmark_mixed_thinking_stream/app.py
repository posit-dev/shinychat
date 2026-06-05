from pathlib import Path
from typing import Any

from htmltools import HTMLDependency, TagList, tags
from shiny.express import app_opts
from shiny.types import Jsonifiable
from shinychat._chat_types import ChatMessage
from shinychat.express import Chat

app_opts(bookmark_store="server")
CSS_DIR = Path(__file__).parent / "_test_assets"
custom_dep = HTMLDependency(
    name="custom-styled-card", version="1.0.0",
    source={"subdir": str(CSS_DIR)}, stylesheet=[{"href": "custom.css"}],
)


class MockClient:
    def __init__(self) -> None:
        self.turns: list[Any] = []

    async def get_state(self) -> Jsonifiable:
        return {"version": 1, "turns": self.turns}

    async def set_state(self, state: Jsonifiable) -> None:
        assert isinstance(state, dict)
        self.turns = list(state["turns"])  # type: ignore[index]


client = MockClient()
chat = Chat(id="chat")
chat.ui()
chat.enable_bookmarking(client, bookmark_on="response")


async def mixed_stream(user_input: str):
    yield ChatMessage(content="reasoning about it", role="assistant", content_type="thinking")
    yield f"Markdown reply to **{user_input}**.\n\n"
    yield TagList(custom_dep, tags.div({"class": "custom-styled-card"}, "Styled HTML"))


@chat.on_user_submit
async def handle(user_input: str):
    client.turns.append({"role": "user", "content": user_input})
    client.turns.append({"role": "assistant", "content": f"reply to {user_input}"})
    await chat.append_message_stream(mixed_stream(user_input))
