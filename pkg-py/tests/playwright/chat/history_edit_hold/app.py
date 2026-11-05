"""Fixture for edit admission, refusal, and draft retention.

A one-shot on_save failure makes the first-input root invalid while later
checkpoints remain valid. The probe verifies that setup before tests edit.
The edit gate uses out-of-cycle websocket handlers because a reactive
release effect cannot run while the gated edit effect is awaiting it.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, cast

from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_ui
from shinychat.types import HistoryOptions


class EchoClient:
    """Duck-typed echo client that counts provider dispatches."""

    def __init__(self, dispatches: reactive.Value[int]) -> None:
        self.turns: list[Any] = []
        self.dispatches = dispatches

    def get_turns(self) -> list[Any]:
        return list(self.turns)

    def set_turns(self, turns: list[Any]) -> None:
        self.turns = list(turns)

    async def stream_async(
        self, text: str, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[str, None]:
        self.dispatches.set(self.dispatches.get() + 1)
        self.turns.extend(
            [
                {"role": "user", "content": text},
                {"role": "assistant", "content": f"echo: {text}"},
            ]
        )

        async def response() -> AsyncGenerator[str, None]:
            yield f"echo: {text}"

        return response()


app_ui = ui.page_fillable(
    ui.input_action_button("break_onsave", "Break first-input on_save"),
    ui.output_text("onsave_status"),
    ui.output_text("dispatch_count"),
    chat_ui("chat", allow_attachments=True),
    ui.tags.script(
        """
        window.__shinychatEditGate = { state: "idle" };
        if (window.Shiny && Shiny.addCustomMessageHandler) {
          Shiny.addCustomMessageHandler("shinyChatEditGate", function (msg) {
            window.__shinychatEditGate = { state: msg.state };
          });
        }
        """
    ),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    dispatches = reactive.value(0)
    onsave_state = reactive.value("idle")
    client = EchoClient(dispatches)
    chat = Chat(
        "chat",
        client=cast(Any, client),
        history=HistoryOptions(
            store="memory", scope="test", restore_mode="none", title=None
        ),
    )
    controller = chat.history._controller
    assert controller is not None

    # One-shot failing app on_save: consumed by the first-input root_close
    # capture, so every later capture (settlements, admissions, edits)
    # succeeds and later checkpoints stay valid.
    break_onsave = {"armed": False, "consumed": False}

    @chat.history.on_save
    def fail_first_capture(values: dict[str, Any]) -> None:
        if break_onsave["armed"] and not break_onsave["consumed"]:
            break_onsave["consumed"] = True
            onsave_state.set("first-input on_save failed")
            raise RuntimeError("first-input on_save failed")
        values["app"] = "ok"

    @reactive.effect
    @reactive.event(input.break_onsave)
    def _arm_break_onsave() -> None:
        break_onsave["armed"] = True
        onsave_state.set("armed")

    # Plain, non-reactive gate state: the gate is driven only by the
    # websocket message handler below, never by reactive effects (see the
    # module docstring). `holding` is one-shot, so the armed hold parks
    # exactly one edit request and an ungated retry passes through.
    gate: dict[str, Any] = {"holding": False, "parked": 0}
    release = asyncio.Event()

    original_handle_edit = controller.handle_edit

    async def gated_handle_edit(
        message_index: int,
        content: str,
        attachments: Any = None,
        *,
        request_id: str | None = None,
    ) -> None:
        if gate["holding"]:
            gate["holding"] = False
            gate["parked"] += 1
            # Custom messages are sent directly over the websocket, not
            # batched into the output flush, so this reaches the browser
            # while the edit effect keeps its cycle busy.
            await session.send_custom_message(
                "shinyChatEditGate", {"state": "parked"}
            )
            await release.wait()
            gate["parked"] -= 1
            await session.send_custom_message(
                "shinyChatEditGate", {"state": "released"}
            )
        await original_handle_edit(
            message_index, content, attachments, request_id=request_id
        )

    controller.handle_edit = gated_handle_edit  # type: ignore[method-assign]

    async def edit_gate_control(action: str) -> dict[str, Any]:
        if action == "hold":
            # Clear before arming so a stale set from an earlier round
            # cannot leak through.
            release.clear()
            gate["holding"] = True
        elif action == "release":
            release.set()
        elif action != "status":
            raise ValueError(f"Unknown edit gate action: {action!r}")
        return {"holding": gate["holding"], "parked": gate["parked"]}

    async def fixture_probe() -> dict[str, Any]:
        recorder = controller._exchange_recorder
        record = recorder.record
        if record is None:
            return {"record": None}
        root = record.root_id
        user_inputs = [
            str(node.input.content)
            for node in record.nodes.values()
            if node.input is not None
        ]
        return {
            "root_status": record.nodes[root].status,
            "root_checkpoint": record.nodes[root].checkpoint,
            "user_inputs": user_inputs,
        }

    session.set_message_handler("shinyChatEditGateControl", edit_gate_control)
    session.set_message_handler("shinyChatFixtureProbe", fixture_probe)

    @render.text
    def onsave_status() -> str:
        return onsave_state.get()

    @render.text
    def dispatch_count() -> str:
        return f"Provider dispatches: {dispatches.get()}"


app = App(app_ui, server)
app.sanitize_errors = True
