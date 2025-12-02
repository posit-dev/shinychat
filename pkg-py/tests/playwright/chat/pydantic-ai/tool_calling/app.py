import os

from dotenv import load_dotenv
from pydantic_ai import Agent
from shiny.express import ui

_ = load_dotenv()
chat_client = Agent(
    "openai:o4-mini",
    system_prompt="You are a helpful assistant.",
)


@chat_client.tool_plain
def get_weather(location: str) -> str:
    """Get the current weather for a given location."""
    return f"The current weather in {location} is sunny with a temperature of 25°C."


@chat_client.tool_plain
def get_time() -> str:
    """Get the current time."""
    from datetime import datetime

    return f"The current time is {datetime.now().strftime('%H:%M:%S')}."


@chat_client.tool_plain
def get_joke() -> str:
    """Tell a joke."""
    return "Why don't scientists trust atoms? Because they make up everything!"


# Set some Shiny page options
ui.page_opts(
    title="Use tool calling with Pydantic AI",
    fillable=True,
    fillable_mobile=True,
)


# Create and display a Shiny chat component
chat = ui.Chat(
    id="chat",
)
chat.ui(
    messages=[
        {
            "content": "Hello! I'm a chatbot that can help you with weather, time, and jokes. How can I assist you today?",
            "role": "assistant",
        }
    ],
)


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
