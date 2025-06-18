import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from shiny.express import ui

_ = load_dotenv()
chat_client = ChatOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    model="gpt-4o",
)

ui.page_opts(
    title="Hello LangChain Chat Models",
    fillable=True,
    fillable_mobile=True,
)

chat = ui.Chat(
    id="chat",
    messages=["Hello! How can I help you today?"],
)
chat.ui()


@chat.on_user_submit
async def handle_user_input(user_input: str):
    response = chat_client.astream(user_input)

    async def stream_wrapper():
        async for item in response:
            yield item.content

    await chat.append_message_stream(stream_wrapper())
