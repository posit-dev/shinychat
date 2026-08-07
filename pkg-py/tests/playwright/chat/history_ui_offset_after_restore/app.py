"""Regression app for server-owned history replay after a conversation switch."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import chatlas
from chatlas import Turn
from chatlas._turn import AssistantTurn
from htmltools import HTMLDependency, TagList, tags
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_ui
from shinychat.types import FileConversationStore, HistoryOptions

CSS_DIR = Path(__file__).parent / "_test_assets"

marker_dep = HTMLDependency(
    name="ui-offset-marker-card",
    version="1.0.0",
    source={"subdir": str(CSS_DIR)},
    stylesheet=[{"href": "custom.css"}],
)


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

        # Rich-UI reply: a styled card carrying an HTMLDependency, distinct
        # per turn via `user_input`. This is what must survive a *second*
        # restore intact -- if `ui_offset` goes stale, this card is dropped
        # from `node.ui` and the restore falls back to plain echoed text.
        assert self.shinychat_chat is not None
        await self.shinychat_chat.append_message(
            TagList(
                marker_dep,
                tags.div(
                    {"class": "ui-offset-marker-card"},
                    f"rich reply for: {user_input}",
                ),
            )
        )

        async def _gen() -> AsyncGenerator[str, None]:
            yield f"echo: {user_input}"

        return _gen()


store_dir = tempfile.mkdtemp(prefix="shinychat-history-ui-offset-")

app_ui = ui.page_fluid(
    chat_ui("chat"),
    ui.output_text_verbatim("save_count"),
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
    def _(values: dict[str, object]) -> None:
        saves.set(saves() + 1)

    @chat.history.on_restore
    def on_history_restore(_: dict[str, object]) -> None:
        restores.set(restores() + 1)

    @render.text
    def save_count():
        return str(saves())

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
