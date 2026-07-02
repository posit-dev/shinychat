from __future__ import annotations

import os
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import chatlas
from chatlas import Turn
from chatlas._turn import AssistantTurn
from shiny import App, Inputs, Outputs, Session, ui
from shinychat import Chat, chat_ui
from shinychat.types import HistoryOptions


class EchoChatClient(chatlas.Chat):
    def __init__(self) -> None:
        provider = MagicMock()
        provider.name = "echo"
        provider.model = "echo"
        super().__init__(provider)

    async def stream_async(
        self, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[str, None]:  # type: ignore[override]
        # chatlas accepts provider-specific stream signatures; tests only need
        # the simple positional prompt path.
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


def app_ui(request: object) -> ui.Tag:
    return ui.page_fillable(chat_ui("chat"))


def server(input: Inputs, output: Outputs, session: Session) -> None:
    if os.getenv("SHINY_DEV_MODE") != "1":
        raise RuntimeError(
            "history_auto_memory_reload must run with SHINY_DEV_MODE=1"
        )
    Chat(
        id="chat",
        client=EchoChatClient(),
        history=HistoryOptions(store="auto", title=None),
    )


app = App(app_ui, server)
