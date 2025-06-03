import os

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic import BaseModel

from shiny.express import ui


class CityLocation(BaseModel):
    city: str
    county: str
    state: str


_ = load_dotenv()
chat_client = Agent(
    "openai:o4-mini",
    api_key=os.environ.get("OPENAI_API_KEY"),
    system_prompt="You are a helpful assistant.",
    output_type=CityLocation,
)


# Set some Shiny page options
ui.page_opts(
    title="Hello OpenAI Chat",
    fillable=True,
    fillable_mobile=True,
)


# Create and display a Shiny chat component
chat = ui.Chat(
    id="chat",
    messages=["Hello! Ask me where the superbowl was held in any year?"],
)
chat.ui()


@chat.on_user_submit
async def handle_user_input(user_input: str):
    result = await chat_client.run(user_input)
    city_info = result.output
    message = f"City: {city_info.city}, County: {city_info.county}, State: {city_info.state}"
    await chat.append_message(message)
