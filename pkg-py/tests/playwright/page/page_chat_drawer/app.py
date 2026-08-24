from __future__ import annotations

import tempfile
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import chatlas
from chatlas import Turn
from chatlas._turn import AssistantTurn
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_drawer, chat_nav_panel, page_chat
from shinychat.types import FileConversationStore, HistoryOptions
from starlette.requests import Request


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
        response = f"echo: {user_input}"
        self._turns.extend(
            [
                Turn(role="user", contents=user_input),
                AssistantTurn(contents=response),
            ]
        )

        async def _gen() -> AsyncGenerator[str, None]:
            yield response

        return _gen()


store_dir = tempfile.mkdtemp(prefix="shinychat-page-drawer-history-")


def app_ui(request: Request) -> ui.Tag:
    query_params = request.query_params
    requested_width = query_params.get("drawer_width") or ""
    requested_chat_width = query_params.get("chat_width") or ""
    drawer_width = {
        "default": "400px",
        "90pct": "90%",
        "relative": "32rem",
    }.get(requested_width, "70%")
    chat_width = {
        "full": "100%",
        "wide": "900px",
        "intrinsic": "fit-content",
    }.get(requested_chat_width, "min(680px, 100%)")
    return page_chat(
        "Drawer Assistant",
        id="chat",
        width=chat_width,
        pages_navbar=[
            chat_nav_panel(
                "Details",
                ui.div("Secondary page content", id="details_page"),
                value="details",
                sidebar=True,
            ),
        ],
        toolbar=ui.div(
            ui.input_action_button("show_drawer", "Show drawer"),
            ui.input_action_button("update_drawer", "Update drawer"),
            class_="d-flex gap-2",
        ),
        sidebar=True,
        drawer=chat_drawer(width=drawer_width, open=False),
    )


def drawer_content(version: str) -> ui.Tag:
    return ui.div(
        ui.p(f"{version} drawer content", class_="drawer-content-label"),
        ui.input_text(
            "drawer_text",
            "Drawer value",
            value=version,
        ),
        ui.output_text("drawer_value"),
    )


def server(input: Inputs, output: Outputs, session: Session) -> None:
    chat = Chat(
        id="chat",
        client=EchoChatClient(),
        history=HistoryOptions(
            store=FileConversationStore(dir=store_dir),
            scope=f"page-drawer-test-{session.id}",
            title=None,
        ),
    )

    @render.text
    def drawer_value() -> str:
        return f"Drawer value: {input.drawer_text()}"

    @reactive.effect
    @reactive.event(input.show_drawer)
    async def _show_drawer() -> None:
        await chat.drawer.show(
            drawer_content("Initial"),
            title="Initial drawer",
        )

    @reactive.effect
    @reactive.event(input.update_drawer)
    async def _update_drawer() -> None:
        await chat.drawer.update(
            drawer_content("Updated"),
            title="Updated drawer",
        )


app = App(app_ui, server)
