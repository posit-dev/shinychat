from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import chatlas
import shinychat._history as history_module
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_ui
from shinychat.types import HistoryOptions

history_module._EXCHANGE_TREE_HISTORY_V2 = True


app_ui = ui.page_fillable(
    ui.output_text("accepted_submissions"),
    ui.output_text("history_updates_sent"),
    chat_ui(
        "chat",
        allow_attachments=True,
        messages=[
            ui.HTML(
                '<span id="held-submit-suggestion" class="suggestion submit">'
                "submit suggestion</span>"
            )
        ],
    ),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    accepted_submission_count = reactive.Value(0)
    accepted_attachment_count = reactive.Value(0)
    history_updates_sent_value = reactive.Value(0)
    provider = MagicMock()
    provider.name = "test"
    provider.model = "test"
    chat = Chat(
        "chat",
        client=chatlas.Chat(provider),
        history=HistoryOptions(
            store="memory",
            scope="test-user",
            restore_mode="none",
        ),
    )
    send_action = chat._send_action

    async def track_history_update(action: Any, *args: Any) -> None:
        await send_action(action, *args)
        if action.get("type") == "history_update":
            history_updates_sent_value.set(history_updates_sent_value() + 1)

    chat._send_action = track_history_update  # type: ignore[method-assign]

    @chat.on_user_submit
    async def _record_submission(
        _input: str, attachments: list[Any]
    ) -> None:
        accepted_submission_count.set(accepted_submission_count() + 1)
        accepted_attachment_count.set(len(attachments))

    @render.text
    def accepted_submissions() -> str:
        return (
            f"{accepted_submission_count()}:{accepted_attachment_count()}"
        )

    @render.text
    def history_updates_sent() -> str:
        return str(history_updates_sent_value())


app = App(app_ui, server)
