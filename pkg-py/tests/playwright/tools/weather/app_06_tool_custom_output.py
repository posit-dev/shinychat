import faicons
import pandas as pd
from chatlas import ChatOpenAI, ContentToolResult
from shiny.express import ui
from shiny.ui import value_box
from shinychat import message_content_chunk
from shinychat.express import Chat
from shinychat.types import ChatMessage


class WeatherToolResult(ContentToolResult):
    """
    Custom tool result class for weather forecasts with custom value box output.
    This example shows how to use a custom tool result class that renders
    the weather data as a custom UI component (value box in R, custom HTML in Python).
    """

    location_name: str


@message_content_chunk.register
def _(message: WeatherToolResult):
    val = message.value
    high_temp = str(val["temperature"].max())
    low_temp = str(val["temperature"].min())
    current = val.iloc[0]

    content = value_box(
        message.location_name,
        str(current["temperature"]),
        f"{current['temperature']}°F (High: {high_temp}°F, Low: {low_temp}°F)",
        showcase=faicons.icon_svg("sun"),
        full_screen=True,
    )
    return ChatMessage(content=content)


def get_weather_forecast(
    lat: float, lon: float, location_name: str
) -> WeatherToolResult:
    """Get the weather forecast for a location."""
    # Mock detailed forecast data as a pandas DataFrame
    forecast_data = pd.DataFrame(
        {
            "time": ["Current", "06:00", "12:00", "18:00"],
            "temperature": [68, 65, 72, 66],
            "humidity": [75, 70, 65, 72],
            "conditions": ["Partly cloudy", "Clear", "Sunny", "Cloudy"],
            "wind_speed": [7, 5, 8, 6],
        }
    )
    return WeatherToolResult(value=forecast_data, location_name=location_name)


client = ChatOpenAI(model="gpt-4.1-nano")
client.register_tool(
    get_weather_forecast,
    annotations={"title": "Weather Forecast"},
)

ui.page_opts(title="Weather Tool - Custom Output")

chat = Chat(id="chat")
chat.ui()


@chat.on_user_submit
async def handle_user_input(user_input: str):
    response = await client.stream_async(user_input, content="all")
    await chat.append_message_stream(response)
