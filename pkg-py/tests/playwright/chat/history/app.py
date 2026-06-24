from __future__ import annotations

import tempfile
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import chatlas
from chatlas import Turn
from chatlas._turn import AssistantTurn
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
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


store_dir = tempfile.mkdtemp(prefix="shinychat-history-")


def app_ui(request: object) -> ui.Tag:
    return ui.page_fillable(
        ui.output_text("filter_state"),
        ui.input_action_button("set_filter", "Set filter"),
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
        ),
    )
    filter_value: reactive.Value[str] = reactive.Value("none")

    @render.text
    def filter_state():
        return f"filter: {filter_value()}"

    @reactive.effect
    @reactive.event(input.set_filter)
    def _():
        filter_value.set("penguins")

    @chat.history.on_save
    def _(values: dict[str, object]) -> None:
        values["app_filter"] = filter_value()

    @chat.history.on_restore
    def _(values: dict[str, object]) -> None:
        filter_value.set(str(values.get("app_filter", "none")))



app = App(app_ui, server, bookmark_store="server")
