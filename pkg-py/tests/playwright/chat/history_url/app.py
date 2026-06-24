from __future__ import annotations

import tempfile
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import chatlas
from chatlas import Turn
from chatlas._turn import AssistantTurn
from shiny import App, Inputs, Outputs, Session, render, ui
from shinychat import Chat, chat_ui
from shinychat.types import FileConversationStore
from shinychat.types import HistoryOptions


class EchoChatClient(chatlas.Chat):
    def __init__(self) -> None:
        provider = MagicMock()
        provider.name = "echo"
        provider.model = "echo"
        super().__init__(provider)

    async def stream_async(self, *args: Any, **kwargs: Any) -> AsyncGenerator[str, None]:  # type: ignore[override]
        user_input = str(args[0]) if args else ""
        self._turns.extend([
            Turn(role="user", contents=user_input),
            AssistantTurn(contents=f"echo: {user_input}"),
        ])

        async def _gen() -> AsyncGenerator[str, None]:
            yield f"echo: {user_input}"

        return _gen()


store_dir = tempfile.mkdtemp(prefix="shinychat-history-url-")


def app_ui(request: object) -> ui.Tag:
    return ui.page_fillable(
        ui.input_text("filter_text", "Filter", value="none"),
        ui.output_text("filter_state"),
        chat_ui("chat"),
    )


def server(input: Inputs, output: Outputs, session: Session) -> None:
    chat = Chat(
        id="chat",
        client=EchoChatClient(),
        history=HistoryOptions(
            store=FileConversationStore(dir=store_dir),
            scope="test-user",
            title="fallback",
            restore_mode="url",
        ),
    )

    @render.text
    def filter_state():
        return f"filter: {input.filter_text()}"


app = App(app_ui, server, bookmark_store="server")
