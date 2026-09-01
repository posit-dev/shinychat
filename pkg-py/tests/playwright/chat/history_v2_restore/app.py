from __future__ import annotations

import json
import os
import tempfile
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import chatlas
import shinychat._history as history_module
from chatlas import Turn
from chatlas._turn import AssistantTurn
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_ui
from shinychat.types import FileConversationStore, HistoryOptions

history_module._EXCHANGE_TREE_HISTORY_V2 = True


class EchoChatClient(chatlas.Chat):
    def __init__(self) -> None:
        provider = MagicMock()
        provider.name = "echo"
        provider.model = "echo"
        super().__init__(provider)
        self.provider_context: reactive.Value[str] | None = None

    async def stream_async(
        self, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[str, None]:  # type: ignore[override]
        user_input = str(args[0]) if args else ""
        context = [str(turn.contents) for turn in self._turns] + [user_input]
        if self.provider_context is not None:
            self.provider_context.set(" | ".join(context))
        self._turns.extend(
            [
                Turn(role="user", contents=user_input),
                AssistantTurn(contents=f"echo: {user_input}"),
            ]
        )

        async def _gen() -> AsyncGenerator[str, None]:
            yield f"echo: {user_input}"

        return _gen()


_store_dirs: dict[int, str] = {}


def _store_dir() -> str:
    pid = os.getpid()
    if pid not in _store_dirs:
        _store_dirs[pid] = tempfile.mkdtemp(prefix="shinychat-history-v2-")
    return _store_dirs[pid]


app_ui = ui.page_fillable(
    ui.input_action_button("inspect_turns", "Inspect turns"),
    ui.output_text_verbatim("turns"),
    ui.output_text_verbatim("recorder"),
    ui.output_text_verbatim("provider_context"),
    ui.output_text_verbatim("history_updates"),
    chat_ui("chat"),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    client = EchoChatClient()
    provider_context_value: reactive.Value[str] = reactive.Value("")
    turns_value: reactive.Value[str] = reactive.Value("")
    recorder_value: reactive.Value[str] = reactive.Value("")
    history_updates_value: reactive.Value[int] = reactive.Value(0)
    history_update_count = 0
    client.provider_context = provider_context_value

    chat = Chat(
        id="chat",
        client=client,
        history=HistoryOptions(
            store=FileConversationStore(dir=_store_dir()),
            scope="test-user",
            title=None,
        ),
    )
    send_action = chat._send_action

    async def track_history_updates(action: Any, *args: Any) -> None:
        nonlocal history_update_count
        if action.get("type") == "history_update":
            history_update_count += 1
            history_updates_value.set(history_update_count)
        await send_action(action, *args)

    chat._send_action = track_history_updates  # type: ignore[method-assign]

    @reactive.effect
    @reactive.event(input.inspect_turns)
    def _inspect_turns() -> None:
        restored_turns = [
            turn.model_dump(mode="json")
            for turn in client.get_turns(include_system_prompt=True)
        ]
        turns_value.set(
            json.dumps(
                {
                    "turn_count": len(restored_turns),
                    "turns": restored_turns,
                }
            )
        )
        controller = chat.history._controller
        assert controller is not None
        recorder = controller._exchange_recorder
        assert recorder is not None
        record = recorder.record
        assert record is not None
        assert record.active_leaf is not None
        active = record.nodes[record.active_leaf]
        recorder_value.set(
            json.dumps(
                {
                    "conversation_id": record.id,
                    "node_count": len(record.nodes),
                    "active_state": active.state["shinychat:turns"].model_dump(
                        mode="json"
                    ),
                }
            )
        )

    @render.text
    def provider_context() -> str:
        return provider_context_value()

    @render.text
    def turns() -> str:
        return turns_value()

    @render.text
    def recorder() -> str:
        return recorder_value()

    @render.text
    def history_updates() -> str:
        return str(history_updates_value())


app = App(app_ui, server)
