from __future__ import annotations

from typing import Any, AsyncGenerator, cast

from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_ui
from shinychat.types import HistoryOptions


class EchoClient:
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
        self.dispatches.set(self.dispatches() + 1)
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
    ui.input_action_button("poison", "Retain unsupported model turn"),
    ui.input_action_button("correct", "Correct model state"),
    ui.output_text("dispatch_count"),
    ui.output_text("poison_status"),
    chat_ui("chat"),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    dispatches = reactive.Value(0)
    poisoned = reactive.Value(False)
    client = EchoClient(dispatches)
    Chat(
        "chat",
        client=cast(Any, client),
        history=HistoryOptions(
            store="memory", scope="test", restore_mode="none", title=None
        ),
    )

    @reactive.effect
    @reactive.event(input.poison)
    def poison() -> None:
        client.turns.append({"role": "assistant", "content": object()})
        poisoned.set(True)

    @reactive.effect
    @reactive.event(input.correct)
    def correct() -> None:
        client.turns = [
            t for t in client.turns if isinstance(t.get("content"), str)
        ]
        poisoned.set(False)

    @render.text
    def dispatch_count() -> str:
        return f"Provider dispatches: {dispatches()}"

    @render.text
    def poison_status() -> str:
        return "Unsupported turn retained" if poisoned() else "Healthy"


app = App(app_ui, server)
app.sanitize_errors = True
