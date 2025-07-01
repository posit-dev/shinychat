import llm
from dotenv import load_dotenv
from shiny.express import ui

# Load environment variables from .env file
_ = load_dotenv()


def get_current_time() -> str:
    """Returns the current date and time as a string."""
    from datetime import datetime

    return str(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


model = llm.get_model("gpt-4o-mini")
model.system_prompt = "You are a helpful assistant."


ui.page_opts(
    title="Hello LLM Chat",
    fillable=True,
    fillable_mobile=True,
)

chat = ui.Chat(
    id="chat",
    messages=["Hello! I am a bot using `llm` package with OpenAI that showcases tool calling. How can I help? Ask me for the current time or date."],
)
chat.ui()


@chat.on_user_submit
async def handle_user_input(user_input: str):

    response = model.chain(user_input, tools=[get_current_time])

    # Stream the response to the chat window
    await chat.append_message_stream(response)
