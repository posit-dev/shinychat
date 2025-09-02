import os

import pandas as pd
from chatlas import ChatOpenAI, ContentToolResult
from shiny.express import ui
from shinychat.express import Chat

# Set environment variable for tool display
os.environ["SHINYCHAT_TOOL_DISPLAY"] = "rich"


def get_weather_forecast(
    lat: float, lon: float, location_name: str
) -> ContentToolResult:
    """Get the weather forecast for a location."""
    # Mock detailed forecast data as a pandas DataFrame (similar to R's data.frame)
    forecast_data = pd.DataFrame(
        {
            "time": ["06:00", "12:00", "18:00", "24:00"],
            "temperature": [65, 72, 68, 62],
            "humidity": [70, 65, 72, 80],
            "conditions": ["Clear", "Partly cloudy", "Cloudy", "Clear"],
            "wind_speed": [5, 8, 6, 4],
        }
    )

    # Convert DataFrame to HTML table
    forecast_table = forecast_data.to_html(
        index=False, classes="table table-striped"
    )

    # Return ContentToolResult with extra display metadata
    return ContentToolResult(
        value=forecast_table,
        extra={
            "display": {
                "html": ui.HTML(forecast_table),
                "title": f"Weather Forecast for {location_name}",
            }
        },
    )


client = ChatOpenAI(model="gpt-4.1-nano")
client.register_tool(
    get_weather_forecast,
    annotations={"title": "Weather Forecast"},
)

ui.page_opts(title="Weather Tool - Tool Result Table")

chat = Chat(id="chat")
chat.ui()


@chat.on_user_submit
async def handle_user_input(user_input: str):
    response = await client.stream_async(user_input, content="all")
    await chat.append_message_stream(response)
