from dotenv import load_dotenv
from llama_index.core.llms import ChatMessage
from llama_index.llms.openai import OpenAI
from shiny.express import ui

# Load environment variables from .env file
_ = load_dotenv()

llm = OpenAI(
    model="gpt-4o-mini",
)

ui.page_opts(
    title="Shiny Chat with LlamaIndex",
    fillable=True,
    fillable_mobile=True,
)


chat = ui.Chat(
    id="chat",
    messages=[
        {"role": "system", "content": "You are a pirate with a colorful personality."},
        {"role": "user", "content": "What is your name, pirate?"},
        {
            "role": "assistant",
            "content": "Arrr, they call me Captain Cog, the chattiest pirate on the seven seas!",
        },
    ],
)
chat.ui()


async def get_response_tokens(conversation: list[ChatMessage]):
    response_stream = await llm.astream_chat(conversation)
    async for r in response_stream:
        yield r.delta


@chat.on_user_submit
async def handle_user_input():
    conversation = [
        ChatMessage(role=msg["role"], content=msg["content"]) for msg in chat.messages()
    ]

    await chat.append_message_stream(get_response_tokens(conversation))
