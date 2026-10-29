"""Baseline instrument for the node-first failed-edit contract (shinychat#zcv8).

Seeds one conversation A, B (B carries a text attachment), C, then edits B.
A selectable ``on_restore`` fault mode lets a test either:

* ``restore_throw`` -- hold a bounded synchronous window (current production
  invokes ``on_restore`` callbacks synchronously), mutate the live app state
  and the live model, and then throw from the edit-time restore callback; or
* ``capture_poison`` -- return normally after poisoning the live model so the
  capture of the edited exchange itself fails.

The capture fault makes the model's turn getter fail until a saved parent is
applied. This keeps the instrument independent of new production symbols and
uses the same attachment-capable Chatlas client shape as history_edit.

Counters are kept independent of each other:

* ``#provider_calls`` -- incremented inside the echo client's
  ``stream_async`` (one per actual provider dispatch).
* ``#submit_count`` -- incremented in a ``@chat.on_user_submit`` callback
  (one per accepted input).
* ``#user_input_count`` -- incremented by an effect observing the shipped
  ``chat.user_input()`` accessor (an independent accepted-input channel).
* ``#save_count`` -- incremented inside the ``@chat.history.on_save``
  callback (one per automatic capture invocation, including the single
  pre-admission capture on a preparation failure; ordinary saves count too,
  so tests read deltas rather than absolutes).

The two fault modes make the app-values outcome of a preparation failure
explicit and opposite:

* ``restore_throw`` breaks the automatic ``on_save`` capture *after* a
  serializable diagnostic fragment was added, so the full snapshot is
  correctly incomplete and the retained failed node must record
  ``app_values: "unavailable"`` -- never a partial fragment tree. The
  shipped warn-and-continue policy applies; healthy edits are unaffected.
* ``capture_poison`` first mutates the live filter to a distinctive
  captured-at-failure value, then poisons the model and returns normally;
  the required capture fails but ``on_save`` succeeds, so the failed node
  must record a *complete* snapshot containing exactly that value. Reloading
  it must restore the node's own saved values, not inherited parent values.

Every ``on_restore`` invocation appends JSON events to
``<store dir>/restore_trace.jsonl``: the wall-clock (ms) entry observation of
``chat.messages()`` and the live client turns (model context), plus
``fault_window_start``/``fault_window_end`` markers around the bounded sync
delay. Tests compare these server timestamps against the browser-side
``Date.now()`` sample timestamps to verify what was visible *inside* the
fault window. The file store directory is rendered as ``#store_dir``, and
``#chat_messages`` renders a live JSON snapshot of ``chat.messages()`` so
tests can prove the settled transcript view after a preparation failure --
the same outgoing view that a fresh load and the browse callback observe.

The capture fault keeps the model's turn getter poisoned until a saved
parent is applied through ``set_turns``; changing the fault selector alone
does not clear it. ``#model_poisoned`` mirrors that state for test
assertions; the mirror is only written alongside the plain backing flag, so
the capture path never takes reactive dependencies. The bounded fault window
must comfortably exceed websocket delivery plus a browser render plus the
test sampler's 50 ms heartbeat, so samples land inside it.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, AsyncGenerator, Literal
from unittest.mock import MagicMock

import chatlas
from chatlas import Turn
from chatlas._turn import AssistantTurn
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_ui
from shinychat.types import FileConversationStore, HistoryOptions

# The conftest passes a per-test directory via the environment; fall back to
# a fresh temp directory when the app is started some other way.
STORE_DIR = os.environ.get("SHINYCHAT_TEST_STORE_DIR") or tempfile.mkdtemp(
    prefix="shinychat-history-node-first-"
)
STORE = FileConversationStore(dir=STORE_DIR)
TRACE_FILE = Path(STORE_DIR) / "restore_trace.jsonl"

FAULT_MODES = {
    "none": "none (healthy edit)",
    "restore_throw": "mutate app+model, then throw",
    "capture_poison": "mutate filter, poison model, then return",
}

# The distinctive app value the capture_poison fault stages before the
# required capture fails, so a complete failed-position snapshot is
# distinguishable from any inherited parent value ("all").
FILTER_CAPTURED_AT_FAILURE = "captured-at-failure"

# The bounded synchronous fault window. The server blocks for this long in
# the edit-time restore callback; the browser must already show the pending
# edited message by then (the server pushes the projection before the
# fallible restore), so the test sampler's 50 ms heartbeat lands samples
# inside it.
FAULT_WINDOW_SECONDS = 0.8


class EchoClient(chatlas.Chat):
    """Echo client whose live model getter stays poisoned until a saved
    parent is applied via ``set_turns``.

    ``capture_poisoned`` reads use a plain flag (no reactive dependencies on
    the capture path); writes mirror into a reactive value so browser tests
    can observe ``#model_poisoned``.
    """

    def __init__(
        self,
        dispatches: reactive.Value[int],
        poison_mirror: reactive.Value[bool],
    ) -> None:
        provider = MagicMock()
        provider.name = "node-first-echo"
        provider.model = "node-first-echo"
        super().__init__(provider)
        self.dispatches = dispatches
        self.poison_mirror = poison_mirror
        self._capture_poisoned = False

    @property
    def capture_poisoned(self) -> bool:
        return self._capture_poisoned

    @capture_poisoned.setter
    def capture_poisoned(self, value: bool) -> None:
        self._capture_poisoned = value
        self.poison_mirror.set(value)

    def get_turns(
        self,
        *,
        include_system_prompt: bool = False,
        tool_result_role: Literal["assistant", "user"] = "user",
    ) -> list[Turn]:
        if self.capture_poisoned:
            raise RuntimeError("Injected live model capture failure")
        return super().get_turns(
            include_system_prompt=include_system_prompt,
            tool_result_role=tool_result_role,
        )

    def set_turns(self, turns: Sequence[Turn]) -> None:
        super().set_turns(turns)
        # Applying saved turns is the only thing that clears the capture
        # fault: a parent apply rewinds the live model.
        self.capture_poisoned = False

    async def stream_async(
        self, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[str, None]:  # type: ignore[override]
        text = str(args[0]) if args else ""
        self.dispatches.set(self.dispatches() + 1)
        self._turns.extend(
            [
                Turn(role="user", contents=text),
                AssistantTurn(contents=f"Echo: {text}"),
            ]
        )

        async def response() -> AsyncGenerator[str, None]:
            yield f"Echo: {text}"

        return response()


app_ui = ui.page_fillable(
    ui.input_select(
        "fault_mode", "on_restore fault mode", FAULT_MODES, selected="none"
    ),
    ui.input_text("region_filter", "Region filter", value="all"),
    ui.output_text("store_dir"),
    ui.output_text("provider_calls"),
    ui.output_text("submit_count"),
    ui.output_text("user_input_count"),
    ui.output_text("save_count"),
    ui.output_text("user_input_text"),
    ui.output_text("chat_messages"),
    ui.output_text("restore_count"),
    ui.output_text("model_poisoned"),
    ui.output_text("current_filter"),
    chat_ui("chat", allow_attachments=True),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    dispatches = reactive.Value(0)
    accepted_submissions = reactive.Value(0)
    user_input_seen = reactive.Value(0)
    restore_attempts = reactive.Value(0)
    save_attempts = reactive.Value(0)
    selected_filter = reactive.Value("all")
    poison_mirror = reactive.Value(False)
    client = EchoClient(dispatches, poison_mirror)

    chat = Chat(
        id="chat",
        client=client,
        history=HistoryOptions(
            store=STORE,
            scope="test-user",
            restore_mode="browser",
            title=None,
        ),
    )

    def trace(event: dict[str, Any]) -> None:
        with open(TRACE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def messages_snapshot() -> list[dict[str, Any]]:
        # The contract's approved callback observation: what chat.messages()
        # shows inside edit-time on_restore.
        return [
            {"role": str(m.get("role")), "content": str(m.get("content"))}
            for m in chat.messages()
        ]

    def turns_snapshot() -> list[dict[str, Any]] | None:
        # Diagnostic reads must not introduce an extra restore failure when
        # the fault deliberately makes model capture unavailable. The capture
        # poison guards get_turns (the production capture seam); the trace
        # still needs to observe what the live model actually holds while
        # poisoned, because read-only navigation deliberately never invokes
        # the builtin model rewind hooks: the browse callback's model must
        # be provably the untouched edit-time parent context, not a guess.
        turns = (
            list(client._turns)  # diagnostic raw read, bypasses the fault
            if client.capture_poisoned
            else client.get_turns()
        )
        return [
            {"role": turn.role, "content": turn.text} for turn in turns
        ]

    def apply_filter(region: str) -> None:
        selected_filter.set(region)
        ui.update_text("region_filter", value=region)

    @reactive.effect
    @reactive.event(input.region_filter)
    def accept_filter_input() -> None:
        selected_filter.set(input.region_filter())

    @chat.history.on_save
    def save_values(values: dict[str, Any]) -> None:
        # isolate(): this capture callback must neither take dependencies on
        # nor invalidate whatever capture/settlement context invokes it --
        # no repeat of the old self-invalidating-counter instrument bug.
        # Every read below (counter, filter, fault mode) is a plain snapshot
        # read with no reactive dependency.
        with reactive.isolate():
            # One per automatic capture invocation, successful or not;
            # tests read deltas to prove the pre-admission capture ran
            # exactly once.
            save_attempts.set(save_attempts.get() + 1)
            values["filter"] = selected_filter.get()
            if (
                client.capture_poisoned
                and input.fault_mode() == "restore_throw"
            ):
                # The restore_throw preparation failure deliberately breaks
                # the automatic capture AFTER a serializable fragment was
                # added, so the full snapshot is correctly incomplete: the
                # retained failed node must record app_values "unavailable",
                # never a partial fragment tree. The shipped warn-and-continue
                # policy applies.
                values["diagnostic"] = "captured-at-restore-failure"
                raise RuntimeError("Injected edit-time on_save failure")

    @chat.history.on_restore
    def restore_values(values: dict[str, Any]) -> None:
        restore_attempts.set(restore_attempts.get() + 1)
        mode = input.fault_mode()
        trace(
            {
                "event": "restore_enter",
                "mode": mode,
                "t_ms": time.time() * 1000,
                "values": dict(values),
                "chat_messages": messages_snapshot(),
                "client_turns": turns_snapshot(),
            }
        )
        if mode == "restore_throw":
            # Bounded synchronous window while the edit outcome is being
            # decided. Current production invokes on_restore synchronously,
            # so a short time.sleep is the honest observable window.
            trace({"event": "fault_window_start", "t_ms": time.time() * 1000})
            time.sleep(FAULT_WINDOW_SECONDS)
            trace({"event": "fault_window_end", "t_ms": time.time() * 1000})
            # Mutate the live app state ...
            selected_filter.set("mutated-by-restore")
            client.capture_poisoned = True
            raise RuntimeError("Injected edit-time on_restore failure")
        if mode == "capture_poison":
            # Mutate the live app state to a distinctive captured-at-failure
            # value first, then poison the model and return normally: the
            # required capture of the edited exchange fails, but the
            # automatic on_save capture succeeds, so the retained failed
            # node must record a complete snapshot with exactly this value.
            selected_filter.set(FILTER_CAPTURED_AT_FAILURE)
            client.capture_poisoned = True
            trace(
                {
                    "event": "restore_exit",
                    "mode": mode,
                    "t_ms": time.time() * 1000,
                }
            )
            return
        apply_filter(str(values.get("filter", "all")))
        trace(
            {
                "event": "restore_exit",
                "mode": mode,
                "t_ms": time.time() * 1000,
            }
        )

    @chat.on_user_submit
    async def count_submission(_content: str, _attachments: list[Any]) -> None:
        accepted_submissions.set(accepted_submissions.get() + 1)

    @reactive.effect
    @reactive.event(chat.user_input)
    def count_accepted_user_input() -> None:
        user_input_seen.set(user_input_seen.get() + 1)

    @render.text
    def store_dir() -> str:
        return STORE_DIR

    @render.text
    def provider_calls() -> str:
        return str(dispatches.get())

    @render.text
    def submit_count() -> str:
        return str(accepted_submissions.get())

    @render.text
    def user_input_count() -> str:
        return str(user_input_seen.get())

    @render.text
    def save_count() -> str:
        return str(save_attempts.get())

    @render.text
    def user_input_text() -> str:
        result = chat.user_input()
        return result.text if result is not None else ""

    @render.text
    def chat_messages() -> str:
        # Live chat.messages() view: lets tests prove the settled server
        # transcript after a preparation failure -- the same outgoing view
        # that a fresh load and the browse callback observe -- independent
        # of the trace snapshots.
        return json.dumps(messages_snapshot())

    @render.text
    def restore_count() -> str:
        return str(restore_attempts.get())

    @render.text
    def model_poisoned() -> str:
        return str(poison_mirror.get()).lower()

    @render.text
    def current_filter() -> str:
        return selected_filter.get()


app = App(app_ui, server)
