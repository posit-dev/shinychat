from __future__ import annotations

import tempfile

from shiny import App, Inputs, Outputs, Session, render, ui
from shinychat import Chat, FileConversationStore, chat_ui


class MockChatClient:
    """Minimal client satisfying ClientWithTurns for enable_history."""

    def __init__(self) -> None:
        self._turns: list[dict[str, object]] = []

    def get_turns(self) -> list[dict[str, object]]:
        return list(self._turns)

    def set_turns(self, turns: list[dict[str, object]]) -> None:
        self._turns = list(turns)

    async def stream_async(self, *args: object, **kwargs: object):
        user_input = str(args[0]) if args else ""
        self._turns.append({"role": "user", "content": user_input})
        reply = f"echo: {user_input}"
        self._turns.append({"role": "assistant", "content": reply})

        async def _gen():
            yield reply

        return _gen()


store_dir = tempfile.mkdtemp(prefix="shinychat-history-url-")


def app_ui(request: object) -> ui.Tag:
    return ui.page_fillable(
        ui.input_text("filter_text", "Filter", value="none"),
        ui.output_text("filter_state"),
        chat_ui("chat"),
    )


def server(input: Inputs, output: Outputs, session: Session) -> None:
    client = MockChatClient()
    chat = Chat(id="chat")

    @render.text
    def filter_state():
        return f"filter: {input.filter_text()}"

    @chat.on_user_submit
    async def _(user_input: str) -> None:
        stream = await client.stream_async(user_input)
        await chat.append_message_stream(stream)

    chat.enable_history(
        client,
        store=FileConversationStore(dir=store_dir),
        user_id="test-user",
        title=False,
        restore_mode="url",
    )


app = App(app_ui, server, bookmark_store="server")
