import asyncio

import chatlas
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_ui


class LocalStreamingClient:
    def __init__(self) -> None:
        self._turns: list[object] = []
        self.system_prompt: str | None = None
        self._tools: list[object] = []

    def get_turns(self) -> list[object]:
        return list(self._turns)

    def set_turns(self, turns: list[object]) -> None:
        self._turns = list(turns)

    def get_tools(self) -> list[object]:
        return list(self._tools)

    def set_tools(self, tools: list[object]) -> None:
        self._tools = list(tools)

    async def stream_async(
        self,
        *args: object,
        content: str = "text",
        controller: chatlas.StreamController | None = None,
    ):
        del args, content

        async def chunks():
            yield "Streaming"
            for _ in range(300):
                if controller is not None and controller.cancelled:
                    break
                await asyncio.sleep(0.1)
                yield "."

        return chunks()


app_ui = ui.page_fillable(
    ui.input_action_button("open_chat", "Open chat"),
    ui.output_text("cancel_received"),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    del output, session
    chat = Chat("chat", client=LocalStreamingClient())  # type: ignore[arg-type]
    cancelled = reactive.Value(False)

    @reactive.effect
    @reactive.event(input.open_chat)
    def _():
        ui.modal_show(
            ui.modal(
                chat_ui("chat", enable_cancel=True),
                title="Chat modal",
                easy_close=True,
            )
        )
        chat.slash_command("ping", "Local command", fn=None)

    @reactive.effect
    @reactive.event(input.chat_cancel)
    def _():
        cancelled.set(True)

    @render.text
    def cancel_received() -> str:
        return str(cancelled())


app = App(app_ui, server)
