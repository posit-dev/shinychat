"""Smoke-test app for MCP Console `send` results rendered as tool cards.

Prerequisites:

1. The mcp-console server binary. Build it from
   https://github.com/posit-dev/mcp-console (`cargo build --release`) and
   either put it on your PATH or point `MCP_CONSOLE_BIN` at it.
2. `ANTHROPIC_API_KEY` set for chatlas.
3. A chatlas version whose MCP client forwards result `_meta` verbatim.

Run with:

    shiny run pkg-py/src/shinychat/examples/mcp_console/app.py

Things to try:

* "Plot a histogram of 1000 normal draws" -- the card should arrive open
  with the plot front and center (request code collapsed behind details).
* "Show me the first few rows of mtcars" -- a text/code result card.
* Hover a card to reveal the fullscreen toggle (bottom-right corner);
  scroll a long result and confirm the toggle stays anchored.
* Use the copy button on the request/result code blocks.
"""

from __future__ import annotations

import os
import shutil

from chatlas import ChatAnthropic
from shiny import App, ui

from shinychat import Chat, chat_ui


def _find_binary() -> str:
    binary = os.environ.get("MCP_CONSOLE_BIN") or shutil.which("mcp-console")
    if binary is None:
        raise RuntimeError(
            "mcp-console binary not found. Build it from "
            "https://github.com/posit-dev/mcp-console (`cargo build --release`) "
            "and either put it on your PATH or set the MCP_CONSOLE_BIN "
            "environment variable to its location."
        )
    return binary


BINARY = _find_binary()

chat_client = ChatAnthropic(
    model="claude-haiku-4-5",
    system_prompt=(
        "You have a `send` tool that executes R code in a persistent session. "
        "Always supply a short one-line `note` naming what the call produces."
    ),
)

app_ui = ui.page_fillable(chat_ui("chat"), title="MCP Console send cards")


def server(input, output, session):
    chat = Chat("chat")
    mcp_registered = False

    @chat.on_user_submit
    async def _(user_input: str):
        nonlocal mcp_registered
        if not mcp_registered:
            await chat_client.register_mcp_tools_stdio_async(
                command=BINARY, args=["serve"]
            )
            mcp_registered = True
        stream = await chat_client.stream_async(user_input, content="all")
        await chat.append_message_stream(stream)


app = App(app_ui, server)
