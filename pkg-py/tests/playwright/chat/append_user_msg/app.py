from shiny import reactive
from shiny.express import render
from shinychat.express import Chat

chat = Chat(id="chat")
chat.ui()


@reactive.effect
async def _():
    await chat.append_message({"content": "A user message", "role": "user"})


"chat.messages():"


@render.code
def message_state():
    return str(chat.messages())
