from __future__ import annotations

import json
import os
import re
import tempfile
from typing import Any, AsyncGenerator, Literal
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
        self.provider_calls: reactive.Value[int] | None = None
        self.provider_attachment_counts: reactive.Value[str] | None = None
        self.provider_attachment_names: reactive.Value[str] | None = None

    async def stream_async(
        self, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[str, None]:  # type: ignore[override]
        user_input = str(args[0]) if args else ""
        if self.provider_calls is not None:
            self.provider_calls.set(self.provider_calls.get() + 1)
        if self.provider_attachment_counts is not None:
            existing = self.provider_attachment_counts.get()
            count = str(len(args) - 1)
            self.provider_attachment_counts.set(
                ",".join([existing, count]) if existing else count
            )
        if self.provider_attachment_names is not None:
            names = []
            for content in args[1:]:
                filename = getattr(content, "filename", None)
                if filename:
                    names.append(str(filename))
                    continue
                text = str(getattr(content, "text", ""))
                match = re.search(r'<file-attachment name="([^"]+)"', text)
                if match:
                    names.append(match.group(1))
            if names:
                existing = self.provider_attachment_names.get()
                value = ",".join(names)
                self.provider_attachment_names.set(
                    ",".join([existing, value]) if existing else value
                )
        context = [str(turn.contents) for turn in self._turns] + [user_input]
        if self.provider_context is not None:
            self.provider_context.set(" | ".join(context))
        if (
            user_input in ("retry me", "held retry")
            and user_input not in _failed_inputs
        ):
            _failed_inputs.add(user_input)
            raise RuntimeError("intentional retry fixture failure")
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
_restore_mode: Literal["browser", "url", "none", "bookmark"] = "browser"
_failed_inputs: set[str] = set()


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
    ui.output_text_verbatim("provider_calls"),
    ui.output_text_verbatim("provider_attachment_counts"),
    ui.output_text_verbatim("provider_attachment_names"),
    ui.output_text_verbatim("accepted_submissions"),
    ui.output_text_verbatim("accepted_attachment_counts"),
    ui.output_text_verbatim("accepted_attachment_names"),
    ui.output_text_verbatim("history_updates"),
    chat_ui("chat"),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    client = EchoChatClient()
    provider_context_value: reactive.Value[str] = reactive.Value("")
    provider_calls_value: reactive.Value[int] = reactive.Value(0)
    provider_attachment_counts_value: reactive.Value[str] = reactive.Value("")
    provider_attachment_names_value: reactive.Value[str] = reactive.Value("")
    accepted_submissions_value: reactive.Value[int] = reactive.Value(0)
    accepted_attachment_counts_value: reactive.Value[str] = reactive.Value("")
    accepted_attachment_names_value: reactive.Value[str] = reactive.Value("")
    turns_value: reactive.Value[str] = reactive.Value("")
    recorder_value: reactive.Value[str] = reactive.Value("")
    history_updates_value: reactive.Value[int] = reactive.Value(0)
    history_update_count = 0
    client.provider_context = provider_context_value
    client.provider_calls = provider_calls_value
    client.provider_attachment_counts = provider_attachment_counts_value
    client.provider_attachment_names = provider_attachment_names_value

    chat = Chat(
        id="chat",
        client=client,
        history=HistoryOptions(
            store=FileConversationStore(dir=_store_dir()),
            scope="test-user",
            title=None,
            restore_mode=_restore_mode,
        ),
    )
    send_action = chat._send_action

    @chat.on_user_submit
    async def _record_accepted_submission(
        user_input: str, attachments: list[Any]
    ) -> None:
        accepted_submissions_value.set(accepted_submissions_value.get() + 1)
        existing = accepted_attachment_counts_value.get()
        count = str(len(attachments))
        accepted_attachment_counts_value.set(
            ",".join([existing, count]) if existing else count
        )
        names = [attachment.name for attachment in attachments]
        if names:
            existing = accepted_attachment_names_value.get()
            value = ",".join(names)
            accepted_attachment_names_value.set(
                ",".join([existing, value]) if existing else value
            )

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
    def provider_calls() -> str:
        return str(provider_calls_value())

    @render.text
    def provider_attachment_counts() -> str:
        return provider_attachment_counts_value()

    @render.text
    def provider_attachment_names() -> str:
        return provider_attachment_names_value()

    @render.text
    def accepted_submissions() -> str:
        return str(accepted_submissions_value())

    @render.text
    def accepted_attachment_counts() -> str:
        return accepted_attachment_counts_value()

    @render.text
    def accepted_attachment_names() -> str:
        return accepted_attachment_names_value()

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
