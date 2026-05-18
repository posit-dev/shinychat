from typing import List

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from shiny import reactive
from shiny.express import ui

_ = load_dotenv()
chat_client = Agent(
    "openai:gpt-4.1-nano-2025-04-14",
    system_prompt="You are a helpful assistant.",
)

conversation_history = reactive.value(list[ModelMessage]([]))

ui.page_opts(
    title="Hello OpenAI Chat",
    fillable=True,
    fillable_mobile=True,
)

chat = ui.Chat(
    id="chat",
)
chat.ui(
    messages=[
        {
            "content": "Hello! I’m your AI assistant. You can ask me questions, get explanations, or help with tasks like brainstorming, summarizing, or coding. How can I assist you today?",
            "role": "user",
        }
    ]
)


@chat.on_user_submit
async def handle_user_input(user_input: str):
    current_history = conversation_history.get()
    stream = pydantic_stream_generator(user_input, current_history)
    await chat.append_message_stream(stream)


async def pydantic_stream_generator(
    user_input: str, current_history: List[ModelMessage]
):
    message_history = current_history if current_history else None
    async with chat_client.run_stream(
        user_input, message_history=message_history
    ) as result:
        async for chunk in result.stream_text(delta=True):
            yield chunk
        conversation_history.set(result.all_messages())
