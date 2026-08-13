from __future__ import annotations

import json
import tempfile
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import chatlas
from chatlas import Turn
from chatlas._turn import AssistantTurn
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shiny.ui import HTML
from shinychat import Chat, chat_ui
from shinychat.types import FileConversationStore, HistoryOptions

# `Chat(client=...)` auto-registers its own `on_user_submit` handler (see
# `_setup_client` in `_chat.py`) that awaits `stream_async()` and appends the
# result via `append_message_stream()`. Adding a second, app-defined
# `on_user_submit` would fire independently and double-echo the reply, so the
# out-of-band message is appended as a side effect from inside
# `stream_async()` itself, which runs in the same on_user_submit invocation,
# before the streamed reply is appended.

OUT_OF_BAND_MARKER = "oob-marker-content"


class EchoChatClient(chatlas.Chat):
    def __init__(self) -> None:
        provider = MagicMock()
        provider.name = "echo"
        provider.model = "echo"
        super().__init__(provider)
        self.shinychat_chat: Chat | None = (
            None  # set once the Chat is constructed
        )

    async def stream_async(
        self, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[str, None]:  # type: ignore[override]
        user_input = str(args[0]) if args else ""
        self._turns.extend(
            [
                Turn(role="user", contents=user_input),
                AssistantTurn(contents=f"echo: {user_input}"),
            ]
        )

        assert self.shinychat_chat is not None
        await self.shinychat_chat.append_message(
            HTML(f'<div id="{OUT_OF_BAND_MARKER}">out-of-band notice</div>')
        )

        async def _gen() -> AsyncGenerator[str, None]:
            yield f"echo: {user_input}"

        return _gen()


store_dir = tempfile.mkdtemp(prefix="shinychat-history-oob-")

app_ui = ui.page_fluid(
    chat_ui("chat"),
    ui.output_text_verbatim("messages"),
    ui.output_text_verbatim("record"),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    client = EchoChatClient()
    chat = Chat(
        id="chat",
        client=client,
        history=HistoryOptions(
            store=FileConversationStore(dir=store_dir),
            scope="test-user",
            title=None,
        ),
    )
    client.shinychat_chat = chat
    saves = reactive.value(0)
    restores = reactive.value(0)

    @chat.history.on_save
    def on_history_save(_: dict[str, object]) -> None:
        saves.set(saves() + 1)

    @chat.history.on_restore
    def on_history_restore(_: dict[str, object]) -> None:
        restores.set(restores() + 1)

    @render.text
    def messages() -> str:
        chat.messages()
        return json.dumps(chat._messages_for_bookmark())

    @render.text
    def record() -> str:
        saves()
        restores()
        controller = chat.history._controller
        if controller is None or controller.record is None:
            return "null"
        return json.dumps(controller.record.model_dump(mode="json"))


app = App(app_ui, server)
