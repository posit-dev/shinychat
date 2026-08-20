from datetime import datetime

import pytz
from dotenv import load_dotenv
from llama_index.core.agent.workflow import AgentStream, FunctionAgent
from llama_index.core.tools import FunctionTool
from llama_index.core.workflow import Context
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

ui.page_opts(
    title="Shiny Chat with LlamaIndex Tool Calling",
    fillable=True,
    fillable_mobile=True,
)

agent = FunctionAgent(
    tools=[time_tool, date_tool],
    llm=llm,
    system_prompt="You are a pirate with a colorful personality. You can tell people the time and date when they need to know when to set sail!",
)

ctx = Context(agent)

chat = ui.Chat(
    id="chat",
)
chat.ui(
    messages=[
        {
            "role": "assistant",
            "content": "Arrr, they call me Captain Cog, the chattiest pirate on the seven seas! I can also tell ye the time and date if ye need to know when to set sail!",
        },
    ],
)


async def stream_response_from_agent(user_message: str, context: Context):
    """Stream response from agent using the context-based approach."""
    handler = agent.run(user_msg=user_message, ctx=context)

    async for event in handler.stream_events():
        if isinstance(event, AgentStream):
            if event.delta:
                yield event.delta

    await handler


@chat.on_user_submit
async def handle_user_input(user_input: str):
    """Handle user input and stream response using context."""

    async def stream_generator():
        async for chunk in stream_response_from_agent(user_input, ctx):
            yield chunk

    await chat.append_message_stream(stream_generator())
