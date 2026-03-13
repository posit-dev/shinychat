"""
Manual test app for verifying the streaming dot appears during streaming.

Run with:
  cd /Users/cpsievert/github/shinychat
  make js-build && make py-update-dist
  uv run shiny run test_streaming_dot.py

The assistant response streams slowly (one word every 200ms) so you can
visually confirm the pulsing dot appears at the end of the streamed content
and disappears when streaming finishes.
"""

import asyncio

from shiny import App, ui
from shiny.ui import Chat, chat_ui

SLOW_RESPONSE = (
    "Here is a **streaming response** with enough content to verify "
    "the streaming dot. It includes:\n\n"
    "- A bullet list\n"
    "- With multiple items\n"
    "- To test dot placement inside lists\n\n"
    "And a code block:\n\n"
    "```python\ndef hello():\n    print('world')\n```\n\n"
    "And finally a closing paragraph so you can watch the dot "
    "move between block elements as content arrives."
)

app_ui = ui.page_fillable(
    ui.h3("Streaming Dot Test"),
    ui.p("Send any message. The response streams one word every 200ms."),
    chat_ui("chat", height="500px"),
)


def server(input, output, session):
    chat = Chat("chat")

    @chat.on_user_submit
    async def on_submit():
        async def slow_stream():
            for word in SLOW_RESPONSE.split(" "):
                yield word + " "
                await asyncio.sleep(0.2)

        await chat.append_message_stream(slow_stream())


app = App(app_ui, server)
