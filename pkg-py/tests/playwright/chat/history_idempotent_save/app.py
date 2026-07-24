from __future__ import annotations

import tempfile
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import chatlas
from chatlas import Turn
from chatlas._turn import AssistantTurn
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_ui
from shinychat.types import FileConversationStore, HistoryOptions

# Regression app for content-idempotent history save: after a restore,
# replay_ui re-renders the stored conversation and the client re-reports its
# snapshot, firing the save trigger again. That re-report must be a no-op —
# save_count (driven by chat.history.on_save, which only fires on an actual
# store.put) must not increase, and the stored conversation must stay intact.


class EchoChatClient(chatlas.Chat):
    def __init__(self) -> None:
        provider = MagicMock()
        provider.name = "echo"
        provider.model = "echo"
        super().__init__(provider)

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

        async def _gen() -> AsyncGenerator[str, None]:
            yield f"echo: {user_input}"

        return _gen()


store_dir = tempfile.mkdtemp(prefix="shinychat-history-idempotent-")

app_ui = ui.page_fluid(chat_ui("chat"), ui.output_text_verbatim("save_count"))


def server(input: Inputs, output: Outputs, session: Session) -> None:
    chat = Chat(
        id="chat",
        client=EchoChatClient(),
        history=HistoryOptions(
            store=FileConversationStore(dir=store_dir),
            scope="test-user",
            title=None,
        ),
    )
    saves = reactive.value(0)

    @chat.history.on_save
    def _(values: dict[str, object]) -> None:
        saves.set(saves() + 1)

    @render.text
    def save_count():
        return str(saves())


app = App(app_ui, server)
