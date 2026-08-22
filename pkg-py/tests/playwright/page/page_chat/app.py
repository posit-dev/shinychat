from __future__ import annotations

import asyncio
import tempfile
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import chatlas
from chatlas import Turn
from chatlas._turn import AssistantTurn
from shiny import App, Inputs, Outputs, Session, reactive, ui
from shinychat import (
    Chat,
    chat_nav_panel,
    chat_sidebar,
    chat_ui_history,
    page_chat,
)
from shinychat.types import FileConversationStore, HistoryOptions
from starlette.requests import Request


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


def app_ui(request: Request) -> ui.Tag:
    if request.query_params.get("standard_theme") == "true":
        return page_chat(
            "Standard theme",
            id="chat",
            sidebar=False,
            artifact_panel=False,
            theme=ui.Theme(preset="shiny"),
        )

    if request.query_params.get("single") == "true":
        return page_chat(
            "A single-page title that should remain fully visible",
            id="chat",
            toolbar=ui.input_action_button("single_toolbar", "Action"),
            sidebar=False,
            artifact_panel=False,
        )

    if request.query_params.get("sidebarless") == "true":
        return page_chat(
            "Sidebarless Assistant",
            id="chat",
            pages_navbar=[
                chat_nav_panel(
                    "About",
                    ui.div("About page", id="sidebarless_about_page"),
                    sidebar=False,
                ),
            ],
            toolbar=ui.input_action_button("sidebarless_toolbar", "Refresh"),
            sidebar=False,
            artifact_panel=False,
        )

    title = "Research Assistant"
    if request.query_params.get("long_title") == "true":
        title = (
            "Research Assistant for long-running analyses and "
            "multi-step investigations"
        )

    return page_chat(
        title,
        id="chat",
        pages_navbar=[
            chat_nav_panel(
                "History",
                chat_ui_history("chat"),
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
                toolbar=ui.input_text(
                    "settings_toolbar_value",
                    "Settings toolbar value",
                    value="settings toolbar initial",
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
            chat_nav_panel(
                "Pinned",
                ui.div("Pinned page content", id="pinned_page"),
                value="pinned",
                sidebar=chat_sidebar(
                    ui.div("Pinned sidebar content", id="pinned_sidebar"),
                    width=900,
                    open="always",
                    resizable=False,
                ),
            ),
        ],
        toolbar=ui.input_text(
            "toolbar_value",
            "Toolbar value",
            value="toolbar initial",
        ),
        toolbar_global=ui.TagList(
            ui.input_text(
                "toolbar_global_value",
                "Global toolbar value",
                value="global toolbar initial",
            ),
            ui.input_action_button("show_toast", "Show toast"),
        ),
        sidebar=True,
        artifact_panel=False,
        greeting="Start a conversation.",
        footer=ui.div("Page chat footer", class_="page-chat-footer"),
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

    @reactive.effect
    @reactive.event(input.show_toast)
    def _show_toast() -> None:
        ui.show_toast(ui.toast("Toast content", header="Toast", type="info"))


app = App(app_ui, server)
