import json
from typing import List, Optional

from dotenv import load_dotenv
from llama_index.core.llms import ChatMessage
from llama_index.core.program import LLMTextCompletionProgram
from llama_index.llms.openai import OpenAI
from pydantic import BaseModel, Field
from shiny.express import ui

# Load environment variables from .env file
_ = load_dotenv()


# Define structured output models
class PirateResponse(BaseModel):
    """A pirate's response with personality and structured data."""

    message: str = Field(description="The pirate's main response message")
    mood: str = Field(
        description="The pirate's current mood (e.g., jolly, grumpy, excited)"
    )
    treasure_count: Optional[int] = Field(
        description="Number of treasures mentioned, if any"
    )
    nautical_terms: List[str] = Field(description="List of nautical/pirate terms used")


class CrewMember(BaseModel):
    """Information about a pirate crew member."""

    name: str = Field(description="The crew member's name")
    role: str = Field(description="Their role on the ship")
    experience_years: int = Field(description="Years of sailing experience")


class PirateStory(BaseModel):
    """A structured pirate story response."""

    title: str = Field(description="Title of the pirate story")
    story: str = Field(description="The main story content")
    characters: List[CrewMember] = Field(description="Characters in the story")
    moral: Optional[str] = Field(description="The moral of the story, if any")


_ = PirateResponse.model_rebuild()
_ = CrewMember.model_rebuild()
_ = PirateStory.model_rebuild()


llm = OpenAI(
    model="gpt-4o-mini",
)

ui.page_opts(
    title="Shiny Chat with LlamaIndex Structured Output",
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
            "content": "Arrr, they call me Captain Cog, the chattiest pirate on the seven seas! Ask me about a short story or a tale, and I'll spin you a yarn full of adventure and treasure!",
        },
    ],
)
chat.ui()


async def get_response_tokens(conversation: list[ChatMessage]):
    last_message = (
        conversation[-1].content.lower()
        if conversation and conversation[-1].content
        else ""
    )

    if "story" in last_message or "tale" in last_message:
        program = LLMTextCompletionProgram.from_defaults(
            output_cls=PirateStory,
            llm=llm,
            prompt_template_str=(
                "You are a pirate storyteller. Based on this conversation: {conversation}\n"
                "Create a pirate story with characters and a moral."
            ),
        )
        response = await program.acall(conversation=str(conversation))
    else:
        program = LLMTextCompletionProgram.from_defaults(
            output_cls=PirateResponse,
            llm=llm,
            prompt_template_str=(
                "You are a pirate with a colorful personality. "
                "Based on this conversation: {conversation}\n"
                "Respond in character and include relevant nautical terms."
            ),
        )
        response = await program.acall(conversation=str(conversation))

    yield f"```json\n{json.dumps(response.dict(), indent=2)}\n```"


@chat.on_user_submit
async def handle_user_input():
    conversation = [
        ChatMessage(role=msg["role"], content=msg["content"]) for msg in chat.messages()
    ]

    await chat.append_message_stream(get_response_tokens(conversation))
