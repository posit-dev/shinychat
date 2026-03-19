from typing import Any

from shiny.express import render
from shinychat.express import Chat
from shiny.types import Jsonifiable


class MockClient:
    """A mock client implementing the ClientWithState protocol."""

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


client = MockClient()

chat = Chat(id="chat")
chat.ui()
chat.enable_bookmarking(client, bookmark_store="server")


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
