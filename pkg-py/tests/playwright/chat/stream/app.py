from shiny import reactive
from shiny.express import render, ui
from shinychat.express import Chat

ui.page_opts(title="Hello Chat")

# Create and display the chat
chat = Chat(id="chat")
chat.ui()


async def stream(*chunks: str):
    for chunk in chunks:
        yield chunk


async def _stream_message(*chunks: str, stream_id: str) -> None:
    # `Chat._append_message_stream()` only sends content and end chunks; the
    # start chunk must be sent first, as `append_message_stream()` does.
    await chat._start_message_stream(stream_id)
    await chat._append_message_stream(stream(*chunks), stream_id)


@reactive.effect
async def _():
    await _stream_message("FIRST ", "FIRST ", "FIRST", stream_id="s1")
    await chat.append_message("SECOND SECOND SECOND")
    await _stream_message("THIRD ", "THIRD ", "THIRD", stream_id="s2")
    await chat.append_message("FOURTH FOURTH FOURTH")
    await _stream_message("FIFTH ", "FIFTH ", "FIFTH", stream_id="s3")


"Message state:"


@render.code
def message_state():
    return str(chat.messages())
