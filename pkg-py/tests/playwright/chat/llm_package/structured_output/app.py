import llm
from dotenv import load_dotenv
from pydantic import BaseModel
from shiny.express import ui

# Load environment variables from .env file
_ = load_dotenv()


class Dog(BaseModel):
    name: str
    age: int


model = llm.get_model("gpt-4o-mini")


model.system_prompt = "You are a helpful assistant."

ui.page_opts(
    title="Hello LLM Chat",
    fillable=True,
    fillable_mobile=True,
)


chat = ui.Chat(
    id="chat",
)
chat.ui(
    messages=[
        {
            "content": """
            Here are some examples of what you can ask me:

- <span class="suggestion"> Tell me about a dog named Bella who is 3 years old. </span>
- <span class="suggestion"> I have a dog named Rocky, age 7. </span>
- <span class="suggestion"> Give me info about a puppy called Luna, 1 year old. </span>
            """,
            "role": "assistant",
        }
    ]
)


@chat.on_user_submit
async def handle_user_input(user_input: str):
    response = model.prompt(user_input, stream=True, schema=Dog)

    async def stream_generator():
        for chunk in response:
            yield chunk

    await chat.append_message_stream(stream_generator())
