from __future__ import annotations

import tempfile
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import chatlas
from chatlas import Turn
from chatlas._turn import AssistantTurn
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_artifact, chat_nav_panel, page_chat
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


store_dir = tempfile.mkdtemp(prefix="shinychat-page-artifact-history-")


def app_ui(request: Request) -> ui.Tag:
    query_params = request.query_params
    requested_width = query_params.get("artifact_width") or ""
    requested_chat_width = query_params.get("chat_width") or ""
    artifact_width = {
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
        "Artifact Assistant",
        id="chat",
        width=chat_width,
        pages=[
            chat_nav_panel(
                "Details",
                ui.div("Secondary page content", id="details_page"),
                value="details",
                sidebar=True,
            ),
        ],
        toolbar=ui.div(
            ui.input_action_button("show_artifact", "Show artifact"),
            ui.input_action_button("update_artifact", "Update artifact"),
            class_="d-flex gap-2",
        ),
        sidebar=True,
        artifact=chat_artifact(width=artifact_width, open=False),
    )


def artifact_content(version: str) -> ui.Tag:
    return ui.div(
        ui.p(f"{version} artifact content", class_="artifact-content-label"),
        ui.input_text(
            "artifact_text",
            "Artifact value",
            value=version,
        ),
        ui.output_text("artifact_value"),
    )


def server(input: Inputs, output: Outputs, session: Session) -> None:
    chat = Chat(
        id="chat",
        client=EchoChatClient(),
        history=HistoryOptions(
            store=FileConversationStore(dir=store_dir),
            scope="page-artifact-test",
            title=None,
        ),
    )

    @render.text
    def artifact_value() -> str:
        return f"Artifact value: {input.artifact_text()}"

    @reactive.effect
    @reactive.event(input.show_artifact)
    async def _show_artifact() -> None:
        await chat.artifact.show(
            artifact_content("Initial"),
            title="Initial artifact",
        )

    @reactive.effect
    @reactive.event(input.update_artifact)
    async def _update_artifact() -> None:
        await chat.artifact.update(
            artifact_content("Updated"),
            title="Updated artifact",
        )


app = App(app_ui, server)
