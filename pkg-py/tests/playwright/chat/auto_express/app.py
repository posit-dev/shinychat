from shiny.express import render
from shinychat.express import Chat


class MockChatClient:
    """A mock chatlas-like client for testing."""

    def __init__(self) -> None:
        self._turns: list[object] = []
        self.system_prompt: str | None = None
        self._tools: list[object] = []

    def get_turns(self) -> list[object]:
        return list(self._turns)

    def set_turns(self, turns: list[object]) -> None:
        self._turns = list(turns)

    def get_tools(self) -> list[object]:
        return list(self._tools)

    def set_tools(self, tools: list[object]) -> None:
        self._tools = list(tools)

    async def stream_async(
        self,
        *args: object,
        content: str = "text",
        controller: object | None = None,
    ):
        del controller
        user_input = str(args[0]) if args else ""
        self._turns.append({"role": "user", "content": user_input})
        reply = f"You said: {user_input}"
        self._turns.append({"role": "assistant", "content": reply})

        async def _gen():
            for word in reply.split(" "):
                yield word + " "

        return _gen()

    async def get_state(self):
        return {"version": 1, "turns": self._turns}

    async def set_state(self, state: object) -> None:
        assert isinstance(state, dict)
        self._turns = state.get("turns", [])


client = MockChatClient()

chat = Chat(id="chat", client=client, greeting="Welcome to the test!")  # type: ignore[arg-type]
chat.ui()


"chat.messages():"


@render.code
def message_state():
    return str(chat.messages())
