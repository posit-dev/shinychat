from shiny.express import render, ui
from shinychat.express import Chat

# Set some Shiny page options
ui.page_opts(title="Hello Chat")


chat = Chat(id="chat")
chat.ui()


@chat.on_user_submit
async def _():
    raise Exception("boom!")


"Message state:"


@render.code
def message_state():
    return str(chat.messages())
