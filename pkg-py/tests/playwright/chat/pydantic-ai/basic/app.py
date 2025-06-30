import os

from dotenv import load_dotenv
from pydantic_ai import Agent
from shiny.express import ui

_ = load_dotenv()
chat_client = Agent(
    "openai:o4-mini",
    system_prompt="You are a helpful assistant.",
)


# Set some Shiny page options
ui.page_opts(
    title="Hello OpenAI Chat",
    fillable=True,
    fillable_mobile=True,
)


# Create and display a Shiny chat component
chat = ui.Chat(
    id="chat",
    messages=["Hello! How can I help you today?"],
)
chat.ui()


# Generate a response when the user submits a message
@chat.on_user_submit
async def handle_user_input(user_input: str):
    stream = pydantic_stream_generator(user_input)
    await chat.append_message_stream(stream)


# An async generator function to stream the response from the Pydantic AI agent
async def pydantic_stream_generator(user_input: str):
    async with chat_client.run_stream(user_input) as result:
        async for chunk in result.stream_text(delta=True):
            yield chunk
