from shiny.express import ui

from shinychat.express import Chat

# Regression test app for posit-dev/shinychat#121: moving a chat component to
# another DOM container must not wipe its rendered conversation.

ui.page_opts(title="Move Chat")

# Plain client-side button: moves the chat container element from #left to
# #right, triggering the custom element's disconnectedCallback/connectedCallback.
ui.tags.button(
    "Move chat",
    id="move",
    type="button",
    class_="btn btn-primary",
    onclick=(
        "document.getElementById('right')"
        ".appendChild(document.getElementById('chat'))"
    ),
)

with ui.div(id="left"):
    chat = Chat(id="chat")
    chat.ui(messages=["Hello! How can I help you today?"])

ui.div(id="right")


@chat.on_user_submit
async def handle_user_input(user_input: str):
    await chat.append_message(f"You said: {user_input}")
