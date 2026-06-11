from typing import Any

from shiny.express import render, ui
from shiny.types import Jsonifiable
from shinychat.express import Chat


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


ui.markdown(
    """
    ### Bookmarking slash commands

    **How to fire a slash command** (the palette grabs `Enter` to *select*, so a
    single `Enter` does **not** submit):

    1. Type the whole thing — e.g. `/greet world` — then press **Enter once**. The
       space after `greet` closes the palette, so this submits directly.
    2. Or: type `/greet`, **Enter** (selects → input shows `/greet`), type ` world`,
       **Enter** again (submits).

    Try `/greet world` (echoed → bookmarked), `/note` (side effect only → not
    bookmarked), or any plain message. Each assistant reply updates the
    `?_state_id_=` in the URL — copy it into a new tab to verify restore.
    """
)

client = MockClient()

chat = Chat(id="chat")
chat.ui(placeholder="Type /greet world and press Enter...")
chat.enable_bookmarking(client, bookmark_store="server")


def _record(role: str, content: str) -> None:
    # Mirror what a real LLM client tracks so bookmarked client state stays in
    # sync with the visible transcript.
    client.turns.append({"role": role, "content": content})


# Echoed command: the `/greet user_input` user message is stored *and* the
# handler appends an assistant reply, so the whole exchange is bookmarked and
# restored.
@chat.slash_command("greet", "Send a greeting")
async def _(user_input: str):
    _record("user", f"/greet {user_input}".rstrip())
    reply = f"Hello! You said: {user_input}"
    _record("assistant", reply)
    await chat.append_message(reply)


# Side-effect-only command (echo=False): nothing is stored, so it never appears
# in a bookmark and its side effect (the notification) is not restored.
@chat.slash_command("note", "Side-effect only", echo=False)
async def _():
    ui.notification_show("noted")


@chat.on_user_submit
async def _():
    user_input, _ = chat.user_input()
    _record("user", user_input)
    reply = f"Echo: {user_input}"
    _record("assistant", reply)
    await chat.append_message(reply)


ui.hr()
"Stored messages (what gets bookmarked) — `chat.messages()`:"


@render.code
def message_state():
    return str(chat.messages())
