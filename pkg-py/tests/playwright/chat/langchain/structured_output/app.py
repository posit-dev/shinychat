import os
from typing import Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from shiny.express import ui

_ = load_dotenv()


class Joke(BaseModel):
    """Joke to tell user."""

    setup: str = Field(description="The setup of the joke")
    punchline: str = Field(description="The punchline to the joke")
    rating: Optional[int] = Field(description="How funny the joke is, from 1 to 10")


_ = Joke.model_rebuild()

chat_client = ChatOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    model="gpt-4o",
)

ui.page_opts(
    title="Hello LangChain Chat Model using structured output",
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
    joke = chat_client.with_structured_output(Joke).invoke(user_input)
    joke_text = f"{joke.setup}\n\n{joke.punchline}\n\nRating: {joke.rating if joke.rating is not None else 'N/A'}"
    await chat.append_message_stream(joke_text)
