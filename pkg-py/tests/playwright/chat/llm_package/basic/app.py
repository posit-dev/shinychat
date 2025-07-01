import llm
from dotenv import load_dotenv
from shiny.express import ui

# Load environment variables from .env file
_ = load_dotenv()

model = llm.get_model("gpt-4o-mini")
model.system_prompt = "You are a helpful assistant."

conversation = model.conversation()

ui.page_opts(
    title="Hello LLM Chat",
    fillable=True,
    fillable_mobile=True,
)

chat = ui.Chat(
    id="chat",
    messages=[
        "Hello! I am a bot using `llm` package with OpenAI. How can I help?"
    ],
)
chat.ui()


def register_handlers(conversation):
    @chat.on_user_submit
    async def handle_user_input(user_input: str):
        response = conversation.prompt(user_input, stream=True)

        async def stream_generator():
            for chunk in response:
                yield chunk

        await chat.append_message_stream(stream_generator())


register_handlers(conversation)
