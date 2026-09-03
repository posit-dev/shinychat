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


@reactive.effect
async def _():
    await chat._append_message_stream(stream("FIRST ", "FIRST ", "FIRST"))
    await chat.append_message("SECOND SECOND SECOND")
    await chat._append_message_stream(stream("THIRD ", "THIRD ", "THIRD"))
    await chat.append_message("FOURTH FOURTH FOURTH")
    await chat._append_message_stream(stream("FIFTH ", "FIFTH ", "FIFTH"))


"Message state:"


@render.code
def message_state():
    return str(chat.messages())
