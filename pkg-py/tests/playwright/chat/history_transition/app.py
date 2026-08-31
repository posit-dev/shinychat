from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, cast
from unittest.mock import MagicMock

import chatlas
from chatlas import Turn
from chatlas._turn import AssistantTurn
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_ui
from shinychat._chat_types import ChatAction
from shinychat.types import HistoryOptions


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
        self._turns.extend(
            [
                Turn(role="user", contents=user_input),
                AssistantTurn(contents=f"echo: {user_input}"),
            ]
        )

        async def _gen() -> AsyncGenerator[str, None]:
            yield f"echo: {user_input}"

        return _gen()


app_ui = ui.page_fillable(
    ui.output_text("submissions"),
    ui.output_text("protocol_state"),
    ui.output_text("transition_events"),
    ui.input_action_button("protocol_absent", "Use absent protocol"),
    ui.input_action_button("protocol_unknown", "Use unknown protocol"),
    ui.input_action_button("protocol_withdrawn", "Use withdrawn protocol"),
    chat_ui("chat", allow_attachments=True),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    submission_count = reactive.value(0)
    protocol_state_value = reactive.value("completion-v1")
    transition_events_value = reactive.value([])
    chat = Chat(
        id="chat",
        client=EchoChatClient(),
        history=HistoryOptions(store="memory", scope="test-user", title=None),
    )
    controller = chat.history._controller
    assert controller is not None
    original_new = controller.new_chat
    original_delete = controller.delete
    first_request_id: str | None = None

    def record_transition_event(event: str) -> None:
        transition_events_value.set([*transition_events_value.get(), event])

    async def wait_then_new() -> None:
        nonlocal first_request_id
        payload = session.input["chat_history_new"]()
        second_transition = first_request_id is not None
        request_id = (
            payload.get("requestId") if isinstance(payload, dict) else None
        )
        if isinstance(request_id, str):
            if first_request_id is None:
                first_request_id = request_id
                record_transition_event("new-started")
            else:
                record_transition_event("new-started")
                await asyncio.sleep(0.5)
                await chat._send_action(
                    {
                        "type": "history_transition_complete",
                        "requestId": first_request_id,
                    }
                )
                await chat._send_action(
                    {
                        "type": "update_input",
                        "value": "stale-completion-ack",
                    }
                )
                record_transition_event("stale-completion-sent")
        else:
            record_transition_event("new-started")
        await asyncio.sleep(2.0 if second_transition else 0.5)
        await original_new()
        record_transition_event("new-finished")

    async def wait_then_delete(conversation_id: str) -> None:
        await asyncio.sleep(0.5)
        await original_delete(conversation_id)

    controller.new_chat = wait_then_new  # type: ignore[method-assign]
    controller.delete = wait_then_delete  # type: ignore[method-assign]

    @chat.on_user_submit
    async def _(user_input: str) -> None:
        submission_count.set(submission_count.get() + 1)
        await chat.append_message(f"echo: {user_input}")

    @render.text
    def submissions() -> str:
        return str(submission_count.get())

    @render.text
    def protocol_state() -> str:
        return protocol_state_value.get()

    @render.text
    def transition_events() -> str:
        return ",".join(transition_events_value.get())

    missing = object()

    async def send_history_update_for_test(protocol: object) -> None:
        assert controller.partition is not None
        metas = await controller.store.list(controller.partition)
        action: dict[str, Any] = {
            "type": "history_update",
            "enabled": True,
            "conversations": [meta.model_dump(mode="json") for meta in metas],
            "active_id": (
                controller.record.id if controller.record is not None else None
            ),
        }
        if protocol is not missing:
            action["transition_protocol"] = protocol
        await chat._send_action(cast(ChatAction, action))

    async def set_protocol(protocol: object, label: str) -> None:
        await send_history_update_for_test(protocol)
        protocol_state_value.set(label)

    @reactive.effect
    @reactive.event(input.protocol_absent)
    async def _set_protocol_absent() -> None:
        await set_protocol(missing, "absent")

    @reactive.effect
    @reactive.event(input.protocol_unknown)
    async def _set_protocol_unknown() -> None:
        await set_protocol("completion-v2", "unknown")

    @reactive.effect
    @reactive.event(input.protocol_withdrawn)
    async def _set_protocol_withdrawn() -> None:
        await set_protocol("withdrawn", "withdrawn")


app = App(app_ui, server)
