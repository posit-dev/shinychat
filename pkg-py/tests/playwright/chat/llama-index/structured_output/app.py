from datetime import datetime
from typing import List, Optional

from dotenv import load_dotenv
from llama_index.core.agent.workflow import AgentStream, FunctionAgent
from llama_index.core.workflow import Context
from llama_index.llms.openai import OpenAI
from pydantic import BaseModel, Field
from shiny.express import ui

_ = load_dotenv()


class AnalysisResponse(BaseModel):
    """A structured analysis response for complex queries."""

    summary: str = Field(description="Executive summary of the analysis")
    detailed_analysis: str = Field(description="Detailed analysis content")
    methodology: Optional[str] = Field(
        description="Methodology used for analysis"
    )
    conclusions: List[str] = Field(description="Key conclusions drawn")
    recommendations: Optional[List[str]] = Field(
        description="Actionable recommendations"
    )


_ = AnalysisResponse.model_rebuild()

llm = OpenAI(model="gpt-4.1-nano-2025-04-14")

ui.page_opts(
    title="Analysis Assistant",
    fillable=True,
    fillable_mobile=True,
)

agent = FunctionAgent(
    tools=[],
    llm=llm,
    system_prompt="""You are an analytical assistant that provides thorough analysis. 
    Be clear, concise, and analytical in your responses.""",
)

ctx = Context(agent)

if not hasattr(ctx, "conversation_history"):
    ctx.conversation_history = []

chat = ui.Chat(
    id="chat",
    messages=[
        {
            "role": "assistant",
            "content": "Hello! I'm your analysis assistant. I can help you analyze topics, data, and situations. What would you like me to analyze?",
        },
    ],
)
chat.ui()


async def stream_response_from_agent(user_message: str, context: Context):
    context.conversation_history.append(
        {
            "role": "user",
            "content": user_message,
            "timestamp": datetime.now().isoformat(),
        }
    )

    recent_context = ""
    if len(context.conversation_history) > 1:
        recent_messages = context.conversation_history[-3:]
        recent_context = "\n".join(
            [f"{msg['role']}: {msg['content']}" for msg in recent_messages]
        )

    enhanced_message = f"""
    Context from recent conversation:
    {recent_context}

    Current request: {user_message}

    Please provide a clear analytical response.
    """

    handler = agent.run(user_msg=enhanced_message, ctx=context)
    response_content = ""

    async for event in handler.stream_events():
        if isinstance(event, AgentStream):
            if event.delta:
                response_content += event.delta
                yield event.delta

    await handler

    context.conversation_history.append(
        {
            "role": "assistant",
            "content": response_content,
            "timestamp": datetime.now().isoformat(),
        }
    )


@chat.on_user_submit
async def handle_user_input():
    """Handle user input and stream response."""
    latest_messages = chat.messages()
    latest_user_message = latest_messages[-1]["content"]

    async def stream_generator():
        async for chunk in stream_response_from_agent(latest_user_message, ctx):
            yield chunk

    await chat.append_message_stream(stream_generator())
