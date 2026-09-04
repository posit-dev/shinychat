import asyncio

from htmltools import TagList
from shiny import reactive
from shiny.express import ui
from shinychat.express import MarkdownStream

stream = MarkdownStream("stream")
stream.ui()


async def content():
    yield "Forged: <shiny-chat-"
    await asyncio.sleep(0.01)
    yield (
        'raw-html><img src="x" data-forged '
        'onerror="window.__forgedFired = true"></shiny-chat-raw-html>'
    )
    yield TagList(
        "## This is markdown",
        ui.input_action_button("trusted_btn", "Trusted HTML"),
    )


@reactive.effect
async def _():
    await stream.stream(content())
