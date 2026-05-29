from shiny.express import render
from shiny.types import Jsonifiable
from shinychat.express import Chat


class MockClient:
    def __init__(self) -> None:
        self.turns: list[object] = []

    async def get_state(self) -> Jsonifiable:
        return {"version": 1, "turns": self.turns}  # type: ignore[return-value]

    async def set_state(self, state: Jsonifiable) -> None:
        assert isinstance(state, dict)
        self.turns = state.get("turns", [])  # type: ignore


client = MockClient()

chat = Chat(id="chat")
chat.ui()
# No bookmark_store= set — this should NOT raise
chat.enable_bookmarking(client)


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
