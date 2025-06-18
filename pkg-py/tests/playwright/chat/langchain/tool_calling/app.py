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

    async def stream_wrapper():
        # while True:
        response = await chat_client.astream(messages)

        # if response.tool_calls:
        #     if response.content:
        #         yield response.content + "\n\n"

        #     for tool_call in response.tool_calls:
        #         tool_to_call = None
        #         for tool in tools:
        #             if tool.name == tool_call["name"]:
        #                 tool_to_call = tool
        #                 break

        #         if tool_to_call:
        #             tool_result = tool_to_call.invoke(tool_call["args"])

        #             messages.append(response)
        #             messages.append(
        #                 ToolMessage(
        #                     content=str(tool_result), tool_call_id=tool_call["id"]
        #                 )
        #             )

        #     continue
        # else:
        #     yield response.content
        #     break

        async def stream_wrapper():
            async for item in response:
                yield item.content

        await chat.append_message_stream(stream_wrapper())
