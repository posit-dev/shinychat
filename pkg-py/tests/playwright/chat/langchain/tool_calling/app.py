import os
from datetime import datetime

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
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

ui.page_opts(
    title="Hello LangChain Chat Models with Tools",
    fillable=True,
    fillable_mobile=True,
)

chat = ui.Chat(
    id="chat",
    messages=[
        "Hello! I can help with time, date, calculator and other questions!"
    ],
)
chat.ui()


@chat.on_user_submit
async def handle_user_input(user_input: str):
    def convert_to_langchain_messages(messages):
        return [
            HumanMessage(content=msg["content"])
            if msg["role"] == "user"
            else AIMessage(content=msg["content"])
            for msg in messages
            if msg["role"] in ["user", "assistant"]
        ]

    current_messages = chat.messages()[:-1]
    langchain_history = convert_to_langchain_messages(current_messages)

    async def stream_response():
        async for chunk in agent_executor.astream(
            {"input": user_input, "chat_history": langchain_history}
        ):
            if chunk.get("output"):
                yield chunk["output"]

    await chat.append_message_stream(stream_response())
