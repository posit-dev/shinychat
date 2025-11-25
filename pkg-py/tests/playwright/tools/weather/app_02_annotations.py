from chatlas import ChatOpenAI
from shiny.express import app_opts, ui
from shinychat.express import Chat

from .tools import get_weather_forecast

client = ChatOpenAI(model="gpt-4.1-nano")
client.register_tool(
    get_weather_forecast,
    annotations={"title": "Weather Forecast"},
)

ui.page_opts(title="Weather Tool - Annotations")
app_opts(bookmark_store="url")

chat = Chat(id="chat")
chat.ui()

chat.enable_bookmarking(client)


@chat.on_user_submit
async def handle_user_input(user_input: str):
    response = await client.stream_async(user_input, content="all")
    await chat.append_message_stream(response)
