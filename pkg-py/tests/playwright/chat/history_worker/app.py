from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import chatlas
import shinychat._history as history_module
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_ui
from shinychat.types import FileConversationStore, HistoryOptions

history_module._EXCHANGE_TREE_HISTORY_V2 = True
STORE_DIR = Path(tempfile.mkdtemp(prefix="shinychat-worker-"))


class EchoClient(chatlas.Chat):
    def __init__(self):
        provider = MagicMock()
        provider.name = "echo"
        provider.model = "echo"
        super().__init__(provider, system_prompt="Initial instructions")

    async def stream_async(
        self, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[str, None]:  # type: ignore[override]
        prompt = str(args[0])
        self.set_turns(
            [
                *self.get_turns(),
                chatlas.Turn(role="user", contents=prompt),
                chatlas.Turn(role="assistant", contents=f"echo: {prompt}"),
            ]
        )

        async def output():
            yield f"echo: {prompt}"

        return output()


app_ui = ui.page_fillable(
    ui.input_action_button("handoff", "Save for worker"),
    ui.output_text_verbatim("saved"),
    ui.output_text_verbatim("run_id"),
    ui.input_action_button("inspect", "Inspect model context"),
    ui.output_text_verbatim("turns"),
    chat_ui("chat"),
)


def server(input: Inputs, output: Outputs, session: Session):
    client = EchoClient()
    saved_value = reactive.Value("")
    run_value = reactive.Value("")
    turns_value = reactive.Value("")
    chat = Chat(
        "chat",
        client=client,
        history=HistoryOptions(
            store=FileConversationStore(STORE_DIR), scope="alice", title=None
        ),
    )

    @chat.history.on_restore
    def restore(values):
        run_value.set(values.get("deputy", {}).get("run_id", ""))

    @chat.history.on_save
    def save(values):
        values["deputy"] = {"version": 1, "run_id": run_value.get()}

    @reactive.effect
    @reactive.event(input.handoff)
    async def handoff():
        await chat.history.save()
        saved_value.set(
            json.dumps(
                {
                    "directory": str(STORE_DIR),
                    "id": chat.history.conversation_id(),
                }
            )
        )
        session.on_ended((STORE_DIR / "disconnected").touch)

    @reactive.effect
    @reactive.event(input.inspect)
    def inspect():
        turns_value.set(
            json.dumps(
                [
                    turn.model_dump(mode="json", exclude_none=True)
                    for turn in client.get_turns(include_system_prompt=True)
                ]
            )
        )

    @render.text
    def saved():
        return saved_value()

    @render.text
    def run_id():
        return run_value()

    @render.text
    def turns():
        return turns_value()


app = App(app_ui, server)
