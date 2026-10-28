from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import chatlas
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_ui

app_ui = ui.page_fillable(
    ui.output_text("disabled_history_update"),
    ui.output_text("disabled_action_order"),
    ui.output_text("disabled_submissions"),
    chat_ui("disabled"),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    provider = MagicMock()
    provider.name = "test"
    provider.model = "test"
    disabled_update = reactive.Value("")
    disabled_actions = reactive.Value([])
    disabled_submission_count = reactive.Value(0)

    disabled = Chat(
        "disabled",
        client=chatlas.Chat(provider),
        messages=["disabled constructor message"],
        history=False,
    )

    disabled_send_action = disabled._send_action

    async def track_disabled_history_update(action: Any, *args: Any) -> None:
        await disabled_send_action(action, *args)
        with reactive.isolate():
            disabled_actions.set([*disabled_actions(), str(action["type"])])
        if action.get("type") == "history_update":
            disabled_update.set(str(action["enabled"]))

    disabled._send_action = track_disabled_history_update  # type: ignore[method-assign]

    @disabled.on_user_submit
    async def _record_disabled_submission(_input: str) -> None:
        disabled_submission_count.set(disabled_submission_count() + 1)

    @render.text
    def disabled_history_update() -> str:
        return disabled_update()

    @render.text
    def disabled_action_order() -> str:
        return ",".join(disabled_actions())

    @render.text
    def disabled_submissions() -> str:
        return str(disabled_submission_count())


app = App(app_ui, server)
