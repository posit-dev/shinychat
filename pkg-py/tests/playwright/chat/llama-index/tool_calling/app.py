from datetime import datetime

import pytz
from dotenv import load_dotenv
from llama_index.core.agent import ReActAgent
from llama_index.core.llms import ChatMessage
from llama_index.core.tools import FunctionTool
from llama_index.llms.openai import OpenAI
from shiny.express import ui

_ = load_dotenv()


def get_current_time(timezone: str = "UTC") -> str:
    """Get the current time in the specified timezone.

    Args:
        timezone: The timezone to get the time for (e.g., 'UTC', 'US/Eastern', 'US/Pacific')

    Returns:
        Current time as a formatted string
    """
    tz = pytz.timezone(timezone)
    current_time = datetime.now(tz)
    return current_time.strftime("%I:%M:%S %p %Z")


def get_current_date(timezone: str = "UTC") -> str:
    """Get the current date in the specified timezone.

    Args:
        timezone: The timezone to get the date for (e.g., 'UTC', 'US/Eastern', 'US/Pacific')

    Returns:
        Current date as a formatted string
    """
    tz = pytz.timezone(timezone)
    current_date = datetime.now(tz)
    return current_date.strftime("%A, %B %d, %Y")


time_tool = FunctionTool.from_defaults(fn=get_current_time)
date_tool = FunctionTool.from_defaults(fn=get_current_date)

llm = OpenAI(
    model="gpt-4.1-nano-2025-04-14",
)

agent = ReActAgent.from_tools([time_tool, date_tool], llm=llm, verbose=True)

ui.page_opts(
    title="Shiny Chat with LlamaIndex Tool Calling",
    fillable=True,
    fillable_mobile=True,
)


chat = ui.Chat(
    id="chat",
    messages=[
        {
            "role": "system",
            "content": "You are a pirate with a colorful personality. You can help users get the current time and date using your tools when they ask.",
        },
        {"role": "user", "content": "What is your name, pirate?"},
        {
            "role": "assistant",
            "content": "Arrr, they call me Captain Cog, the chattiest pirate on the seven seas! I can also tell ye the time and date if ye need to know when to set sail!",
        },
    ],
)
chat.ui()


@chat.on_user_submit
async def handle_user_input():
    messages = [
        ChatMessage(role=msg["role"], content=msg["content"]) for msg in chat.messages()
    ]

    last_message = messages[-1]
    chat_history = messages[:-1]

    async def stream_generator():
        response_stream = await agent.astream_chat(
            message=last_message.content, chat_history=chat_history
        )
        async for token in response_stream.async_response_gen():
            yield token

    await chat.append_message_stream(stream_generator())
