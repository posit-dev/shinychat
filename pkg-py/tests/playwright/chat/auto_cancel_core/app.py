import asyncio

import chatlas
from shiny import App, Inputs, Outputs, Session, module, reactive, render, ui
from shinychat import Chat, chat_ui


class ObservableStreamController(chatlas.StreamController):
    cancel_requested: reactive.Value[bool] | None = None

    def cancel(self, reason: str = "cancelled") -> None:
        super().cancel(reason=reason)
        if self.cancel_requested is not None:
            self.cancel_requested.set(True)


chatlas.StreamController = ObservableStreamController


class SlowChatClient:
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
        del content
        user_input = str(args[0]) if args else ""
        self._turns.append({"role": "user", "content": user_input})

        async def _gen():
            for chunk in ("alpha ", "beta ", "gamma ", "delta "):
                if controller is not None and controller.cancelled:
                    break
                await asyncio.sleep(0.2)
                yield chunk

        return _gen()

    async def get_state(self):
        return {"version": 1, "turns": self._turns}

    async def set_state(self, state: object) -> None:
        assert isinstance(state, dict)
        self._turns = state.get("turns", [])


@module.ui
def chat_mod_ui():
    return chat_ui(id="chat")


@module.server
def chat_mod_server(input: Inputs, output: Outputs, session: Session) -> None:
    del input, output, session
    Chat("chat", client=SlowChatClient())  # type: ignore[arg-type]


# Note: `enable_cancel=True` is intentionally omitted here. Passing a
# `client=` to `Chat` should auto-enable the stop button via a server message.
# The chat lives inside a module ("mod") to exercise ResolvedId handling in
# _setup_client — the bug this test guards against only manifests in modules.
app_ui = ui.page_fillable(
    chat_mod_ui("mod"),
    ui.output_code("cancel_requested"),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    del input, output, session
    cancel_requested_value = reactive.Value(False)
    ObservableStreamController.cancel_requested = cancel_requested_value

    chat_mod_server("mod")

    @render.code
    def cancel_requested() -> str:
        return str(cancel_requested_value())


app = App(app_ui, server)
