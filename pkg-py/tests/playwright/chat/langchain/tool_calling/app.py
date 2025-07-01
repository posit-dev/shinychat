import os
from datetime import datetime

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from shiny.express import ui

_ = load_dotenv()


@tool
def get_current_time() -> str:
    """Get the current time in HH:MM:SS format."""
    return datetime.now().strftime("%H:%M:%S")


@tool
def get_current_date() -> str:
    """Get the current date in YYYY-MM-DD format."""
    return datetime.now().strftime("%Y-%m-%d")


@tool
def get_current_weather(city: str) -> str:
    """Get the current weather for a given city."""
    return f"The current weather in {city} is sunny with a temperature of 25°C."


@tool
def calculator(expression: str) -> str:
    """Evaluate mathematical expressions"""
    return str(eval(expression))


tools = [get_current_time, get_current_date, calculator, get_current_weather]

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You are a helpful assistant"),
        MessagesPlaceholder("chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ]
)

llm = ChatOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    model="gpt-4.1-nano-2025-04-14",
)

agent = create_openai_tools_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools)

store = {}


def get_session_history(session_id: str):
    """
    Retrieves the chat history for a given session ID.
    If no history exists, a new one is created.
    """
    if session_id not in store:
        store[session_id] = InMemoryChatMessageHistory()
    return store[session_id]


agent_with_chat_history = RunnableWithMessageHistory(
    agent_executor,
    get_session_history,
    input_messages_key="input",
    history_messages_key="chat_history",
)

ui.page_opts(
    title="Shiny Chat with LangChain Agent",
    fillable=True,
    fillable_mobile=True,
)

chat = ui.Chat(
    id="chat",
    messages=[
        {
            "content": "Hello! I'm a chatbot with tools. I can get the time, date, weather, or do calculations. I'll also remember our conversation. How can I help?",
            "role": "assistant",
        }
    ],
)
chat.ui()


@chat.on_user_submit
async def handle_user_input(user_input: str):
    """
    Handles user input by streaming the agent's response.
    """
    config = {"configurable": {"session_id": "shiny_session_tools_1"}}

    async def stream_response():
        async for event in agent_with_chat_history.astream_events(
            {"input": user_input}, config=config, version="v1"
        ):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    yield content

    await chat.append_message_stream(stream_response())
