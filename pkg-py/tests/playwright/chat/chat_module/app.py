from __future__ import annotations

from typing import Any, Optional

from shiny import App, Inputs, Outputs, Session, render, ui
from shinychat import chat_mod_server, chat_mod_ui


class MockChat:
    def __init__(self):
        self._turns: list[Any] = []
        self._system_prompt: str = ""
        self._tools: list[Any] = []

    def stream_async(self, user_input: str, content: str = "all"):
        async def _stream():
            for word in f"Echo: {user_input}".split():
                yield word + " "

        return _stream()

    def get_turns(self) -> list[Any]:
        return self._turns

    def set_turns(self, turns: list[Any]) -> None:
        self._turns = turns

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    @system_prompt.setter
    def system_prompt(self, val: str) -> None:
        self._system_prompt = val

    def get_tools(self) -> list[Any]:
        return self._tools

    def set_tools(self, tools: list[Any]) -> None:
        self._tools = tools

    def get_last_turn(self) -> Optional[Any]:
        return None


app_ui = ui.page_fillable(
    ui.panel_title("Chat Module Test"),
    chat_mod_ui("chatmod"),
    ui.output_text("status_out"),
    fillable_mobile=True,
)


def server(input: Inputs, output: Outputs, session: Session):
    client = MockChat()
    state = chat_mod_server("chatmod", client=client)

    @output
    @render.text
    def status_out():
        return state.status()


app = App(app_ui, server)
