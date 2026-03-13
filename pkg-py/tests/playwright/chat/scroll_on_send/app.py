import asyncio

from shiny.express import ui
from shinychat.express import Chat

ui.page_opts(title="Scroll on Send Test")

chat = Chat(id="chat")

# Fill chat with enough messages to make it scrollable
initial_messages = [f"Message {i}: padding to fill the chat area." for i in range(20)]

chat.ui(messages=initial_messages, height="400px")


@chat.on_user_submit
async def handle_user_input(user_input: str):
    await asyncio.sleep(0.5)
    await chat.append_message(f"You said: {user_input}")
