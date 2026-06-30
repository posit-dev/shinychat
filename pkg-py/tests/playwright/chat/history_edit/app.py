from __future__ import annotations

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
        user_input = str(args[0]) if args else ""
        self._turns.extend(
            [
                Turn(role="user", contents=user_input),
                AssistantTurn(contents=f"Echo: {user_input}"),
            ]
        )

        async def _gen() -> AsyncGenerator[str, None]:
            yield f"Echo: {user_input}"

        return _gen()


def app_ui(request: object) -> ui.Tag:
    return ui.page_fillable(chat_ui("chat"))


def server(input: Inputs, output: Outputs, session: Session) -> None:
    Chat(
        id="chat",
        client=EchoChatClient(),
        history=HistoryOptions(
            store="memory",
            restore_mode="none",
            scope="test-user",
            title=None,
        ),
    )


app = App(app_ui, server)
