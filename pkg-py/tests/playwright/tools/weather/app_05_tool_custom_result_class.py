import pandas as pd
from chatlas import ChatOpenAI, ContentToolResult
from shiny.express import ui
from shinychat.express import Chat
from shinychat.types import ToolResultDisplay


class WeatherToolResult(ContentToolResult):
    """
    Custom tool result class for weather forecasts.

    This example shows how to use a custom tool result class. In the R version,
    this extends the contents_shinychat() generic to compute the HTML table on
    the fly when rendering the result. In Python, we'll include the extra
    rendering logic directly in the constructor.
    """

    def __init__(self, forecast_data, location_name: str, **kwargs):
        # Create HTML table from the data
        if isinstance(forecast_data, pd.DataFrame):
            html_table = forecast_data.to_html(
                index=False, classes="table table-striped"
            )
        else:
            html_table = str(forecast_data)  # Fallback

        extra = {
            "display": ToolResultDisplay(
                html=ui.HTML(html_table),
                title=f"Weather Forecast for {location_name}",
            )
        }

        super().__init__(value=forecast_data, extra=extra, **kwargs)


def get_weather_forecast(
    lat: float, lon: float, location_name: str
) -> WeatherToolResult:
    """Get the weather forecast for a location."""
    # Mock detailed forecast data as a pandas DataFrame
    forecast_data = pd.DataFrame(
        {
            "time": ["06:00", "12:00", "18:00", "24:00"],
            "temperature": [65, 72, 68, 62],
            "humidity": [70, 65, 72, 80],
            "conditions": ["Clear", "Partly cloudy", "Cloudy", "Clear"],
            "wind_speed": [5, 8, 6, 4],
        }
    )
    return WeatherToolResult(forecast_data, location_name)


client = ChatOpenAI(model="gpt-4.1-nano")
client.register_tool(
    get_weather_forecast,
    annotations={"title": "Weather Forecast"},
)

ui.page_opts(title="Weather Tool - Custom Result Class")

chat = Chat(id="chat")
chat.ui()


@chat.on_user_submit
async def handle_user_input(user_input: str):
    response = await client.stream_async(user_input, content="all")
    await chat.append_message_stream(response)
