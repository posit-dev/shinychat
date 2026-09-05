import os

from dotenv import load_dotenv
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import ChatOpenAI
from shiny.express import ui

_ = load_dotenv()

model = ChatOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    model="gpt-4.1-nano-2025-04-14",
)

prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a helpful assistant. You answer in a friendly and concise manner.",
        ),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
    ]
)

store = {}


def get_session_history(session_id: str):
    if session_id not in store:
        store[session_id] = InMemoryChatMessageHistory()
    return store[session_id]


chain_with_history = RunnableWithMessageHistory(
    prompt | model,
    get_session_history,
    input_messages_key="input",
    history_messages_key="history",
)

ui.page_opts(
    title="Shiny Chat with LangChain History",
    fillable=True,
    fillable_mobile=True,
)

chat = ui.Chat(
    id="chat",
)
chat.ui(
    messages=[
        {
            "content": "Hello! I'm a chatbot that can remember our conversation. How can I help you today?",
            "role": "assistant",
        }
    ],
)


@chat.on_user_submit
async def handle_user_input(user_input: str):
    config = {"configurable": {"session_id": "shiny_session_1"}}
    response_stream = chain_with_history.astream(
        {"input": user_input},
        config=config,
    )

    async def stream_wrapper():
        async for chunk in response_stream:
            yield chunk.content

    await chat.append_message_stream(stream_wrapper())
