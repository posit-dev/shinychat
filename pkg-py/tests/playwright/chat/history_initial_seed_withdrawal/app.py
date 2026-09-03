from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import chatlas
import shinychat._history as history_module
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_ui
from shinychat.types import HistoryOptions

history_module._EXCHANGE_TREE_HISTORY_V2 = False


app_ui = ui.page_fillable(
    ui.output_text("v1_history_update"),
    ui.output_text("v1_action_order"),
    ui.output_text("v1_submissions"),
    chat_ui("v1"),
    ui.output_text("disabled_history_update"),
    ui.output_text("disabled_action_order"),
    ui.output_text("disabled_submissions"),
    chat_ui("disabled"),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    provider = MagicMock()
    provider.name = "test"
    provider.model = "test"
    v1_update = reactive.Value("")
    disabled_update = reactive.Value("")
    v1_actions = reactive.Value([])
    disabled_actions = reactive.Value([])
    v1_submission_count = reactive.Value(0)
    disabled_submission_count = reactive.Value(0)

    v1 = Chat(
        "v1",
        client=chatlas.Chat(provider),
        messages=["v1 constructor message"],
        history=HistoryOptions(
            store="memory",
            scope="test-user",
            restore_mode="browser",
        ),
    )
    disabled = Chat(
        "disabled",
        client=chatlas.Chat(provider),
        messages=["disabled constructor message"],
        history=False,
    )

    v1_send_action = v1._send_action

    async def track_v1_history_update(action: Any, *args: Any) -> None:
        await v1_send_action(action, *args)
        with reactive.isolate():
            v1_actions.set([*v1_actions(), str(action["type"])])
        if action.get("type") == "history_update":
            v1_update.set(
                f"{action['enabled']}:{action.get('transition_protocol', '')}"
            )

    v1._send_action = track_v1_history_update  # type: ignore[method-assign]

    disabled_send_action = disabled._send_action

    async def track_disabled_history_update(action: Any, *args: Any) -> None:
        await disabled_send_action(action, *args)
        with reactive.isolate():
            disabled_actions.set([*disabled_actions(), str(action["type"])])
        if action.get("type") == "history_update":
            disabled_update.set(str(action["enabled"]))

    disabled._send_action = track_disabled_history_update  # type: ignore[method-assign]

    @v1.on_user_submit
    async def _record_v1_submission(_input: str) -> None:
        v1_submission_count.set(v1_submission_count() + 1)

    @disabled.on_user_submit
    async def _record_disabled_submission(_input: str) -> None:
        disabled_submission_count.set(disabled_submission_count() + 1)

    @render.text
    def v1_history_update() -> str:
        return v1_update()

    @render.text
    def v1_action_order() -> str:
        return ",".join(v1_actions())

    @render.text
    def disabled_history_update() -> str:
        return disabled_update()

    @render.text
    def disabled_action_order() -> str:
        return ",".join(disabled_actions())

    @render.text
    def v1_submissions() -> str:
        return str(v1_submission_count())

    @render.text
    def disabled_submissions() -> str:
        return str(disabled_submission_count())


app = App(app_ui, server)
