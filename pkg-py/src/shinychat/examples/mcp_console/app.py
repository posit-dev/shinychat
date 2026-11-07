"""Smoke-test app for MCP Console `send` results rendered as tool cards.

Prerequisites:

1. The mcp-console server binary, built from a revision that attaches
   `send` call metadata to results (posit-dev/mcp-console#215, not yet
   merged -- check out that PR branch, `cargo build --release`, then either
   put the binary on your PATH or point `MCP_CONSOLE_BIN` at it).
2. `ANTHROPIC_API_KEY` set for chatlas.
3. A chatlas version whose MCP client forwards result `_meta` verbatim
   (posit-dev/chatlas#489, merged after v0.23.0 -- install from source with
   `pip install git+https://github.com/posit-dev/chatlas` until the next
   release).

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

import asyncio
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
    system_prompt=(
        "You have a `send` tool that executes R code in a persistent session. "
        "Always supply a short one-line `note` naming what the call produces."
    ),
)

app_ui = ui.page_fillable(chat_ui("chat"), title="MCP Console send cards")

# Holder for the one-per-process registration task (mutated, not rebound, so
# no `global`). Every browser session runs `server()`, but one mcp-console
# process serves them all.
_registration: "list[asyncio.Task[None]]" = []


def server(input, output, session):
    Chat("chat", client=chat_client)

    # MCP stdio sessions are bound to the event loop that opened them, and
    # Shiny serves each session on the app's loop -- so register here, at
    # session start, rather than at module level (where the session would
    # die with its loop before the first tool call). The task completes
    # long before a user can type and submit a first message.
    if not _registration:
        _registration.append(
            asyncio.get_running_loop().create_task(
                chat_client.register_mcp_tools_stdio_async(
                    command=BINARY, args=["serve"]
                )
            )
        )


app = App(app_ui, server)
