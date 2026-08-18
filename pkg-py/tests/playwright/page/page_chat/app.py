from __future__ import annotations

import asyncio
import tempfile
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import chatlas
from chatlas import Turn
from chatlas._turn import AssistantTurn
from shiny import App, Inputs, Outputs, Session, ui
from shinychat import Chat, chat_nav_panel, chat_sidebar, page_chat
from shinychat.types import FileConversationStore, HistoryOptions


class SlowEchoChatClient(chatlas.Chat):
    def __init__(self) -> None:
        provider = MagicMock()
        provider.name = "slow-echo"
        provider.model = "slow-echo"
        super().__init__(provider)

    async def stream_async(
        self, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[str, None]:  # type: ignore[override]
        user_input = str(args[0]) if args else ""
        response = f"echo: {user_input}"
        self._turns.extend(
            [
                Turn(role="user", contents=user_input),
                AssistantTurn(contents=response),
            ]
        )

        async def _gen() -> AsyncGenerator[str, None]:
            for chunk in response.split():
                await asyncio.sleep(0.12)
                yield f"{chunk} "

        return _gen()


store_dir = tempfile.mkdtemp(prefix="shinychat-page-history-")


def app_ui(request: object) -> ui.Tag:
    return page_chat(
        "Research Assistant",
        id="chat",
        pages=[
            chat_nav_panel(
                "History",
                ui.div(
                    ui.input_text(
                        "history_page_input",
                        "History page value",
                        value="history page",
                    ),
                    id="history_page",
                ),
                value="history",
                sidebar=True,
            ),
            chat_nav_panel(
                "Settings",
                ui.div(
                    ui.input_text(
                        "settings_page_input",
                        "Settings page value",
                        value="settings page",
                    ),
                    id="settings_page",
                ),
                value="settings",
                sidebar=chat_sidebar(
                    ui.input_text(
                        "custom_sidebar_input",
                        "Custom sidebar value",
                        value="custom sidebar",
                    ),
                    width=320,
                    open="closed",
                    resizable=True,
                ),
            ),
            chat_nav_panel(
                "About",
                ui.div(
                    ui.input_text(
                        "about_page_input",
                        "About page value",
                        value="about page",
                    ),
                    id="about_page",
                ),
                value="about",
                sidebar=False,
            ),
        ],
        toolbar=ui.input_text(
            "toolbar_value",
            "Toolbar value",
            value="toolbar initial",
        ),
        sidebar=True,
        artifact=False,
        greeting="Start a conversation.",
    )


def server(input: Inputs, output: Outputs, session: Session) -> None:
    Chat(
        id="chat",
        client=SlowEchoChatClient(),
        history=HistoryOptions(
            store=FileConversationStore(dir=store_dir),
            title=None,
        ),
    )


app = App(app_ui, server)
