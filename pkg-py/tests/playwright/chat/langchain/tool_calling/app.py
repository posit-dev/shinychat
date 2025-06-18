import os
from datetime import datetime

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from shiny.express import ui

_ = load_dotenv()


@tool
def get_current_time() -> str:
    """Get the current time in HH:MM:SS format."""
    return datetime.now().strftime("%H:%M:%S")


@tool
def get_current_date() -> str:
    """Get the current date in YYYY-MM-DD format."""
    return datetime.now().strftime("%Y-%m-%d")


@tool
def get_current_datetime() -> str:
    """Get the current date and time in a readable format."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


tools = [get_current_time, get_current_date, get_current_datetime]

tool_registry = {tool.name: tool for tool in tools}

chat_client = ChatOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    model="gpt-4o",
).bind_tools(tools)

ui.page_opts(
    title="Hello LangChain Chat Models with Tools",
    fillable=True,
    fillable_mobile=True,
)

chat = ui.Chat(
    id="chat",
    messages=[
        "Hello! How can I help you today? I can tell you the current time, date, or both!"
    ],
)
chat.ui()


@chat.on_user_submit
async def handle_user_input(user_input: str):
    messages = [HumanMessage(content=user_input)]

    async def stream_response():
        accumulated_tool_calls = []

        async for chunk in chat_client.astream(messages):
            tool_calls = getattr(chunk, "tool_calls", None)
            if tool_calls:
                accumulated_tool_calls.extend(tool_calls)

            if chunk.content:
                content = chunk.content
                if isinstance(content, str):
                    yield content
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, str):
                            yield part

        for tool_call in accumulated_tool_calls:
            tool_name = tool_call.get("name", "")
            if not tool_name:
                continue

            if tool_name in tool_registry:
                result = tool_registry[tool_name].invoke({})
                yield f"\n\n🔧 {tool_name}: {result}"
            else:
                yield f"\n\n❌ Unknown tool: {tool_name}"

    await chat.append_message_stream(stream_response())
