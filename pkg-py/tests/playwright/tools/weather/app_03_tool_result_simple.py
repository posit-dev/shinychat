import faicons
from chatlas import ChatOpenAI, ContentToolResult
from shiny.express import app_opts, ui

from shinychat.express import Chat

from . import tools


def get_weather_forecast(
    lat: float, lon: float, location_name: str
) -> ContentToolResult:
    """Get the weather forecast for a location."""
    forecast_data = tools.get_weather_forecast(lat, lon)

    # Determine icon based on temperature
    if forecast_data["temperature_2m"] > 21:
        icon = "sun"
    elif forecast_data["temperature_2m"] < 7:
        icon = "snowflake"
    else:
        icon = "cloud-sun"

    # Return ContentToolResult with extra display metadata
    return ContentToolResult(
        value=forecast_data,
        extra={
            "display": {
                "title": f"Weather Forecast for {location_name}",
                "icon": faicons.icon_svg(icon),
            }
        },
    )


# Create chat client and register tool
chat_client = ChatOpenAI(model="gpt-4.1-nano")
chat_client.register_tool(
    get_weather_forecast,
    annotations={"title": "Weather Forecast"},
)


# The Shiny app
ui.page_opts(title="Weather Tool - Tool Result Simple")
app_opts(bookmark_store="url")


chat = Chat(id="chat")
chat.ui()

chat.enable_bookmarking(chat_client)


@chat.on_user_submit
async def handle_user_input(user_input: str):
    response = await chat_client.stream_async(user_input, content="all")
    await chat.append_message_stream(response)
