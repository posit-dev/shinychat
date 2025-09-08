import asyncio
import os
import random
import time

import faicons
from chatlas import ChatAuto, ContentToolResult
from chatlas.types import ToolAnnotations
from shiny import reactive
from shiny.express import input, ui

from shinychat.express import Chat
from shinychat.types import ToolResultDisplay

TOOL_OPTS = {
    "async": os.getenv("TEST_TOOL_ASYNC", "TRUE").lower() == "true",
    "with_intent": os.getenv("TEST_TOOL_WITH_INTENT", "TRUE").lower() == "true",
    "with_title": os.getenv("TEST_TOOL_WITH_TITLE", "TRUE").lower() == "true",
    "with_icon": os.getenv("TEST_TOOL_WITH_ICON", "TRUE").lower() == "true",
}

chat_client = ChatAuto(provider="openai", model="gpt-4.1-nano")


def list_files_impl():
    # Randomly fail sometimes to test error handling
    if random.choice([True, False, False, False]):
        raise Exception("An error occurred while listing files.")

    extra = {}
    if TOOL_OPTS["with_icon"]:
        extra = {
            "display": ToolResultDisplay(icon=faicons.icon_svg("folder-open")),
        }

    return ContentToolResult(
        value=["app.py", "data.csv"],
        extra=extra,
    )


annotations: ToolAnnotations = {}
if TOOL_OPTS["with_title"]:
    annotations["title"] = "List Files"

# Define the tool function based on configuration
if TOOL_OPTS["async"]:
    if TOOL_OPTS["with_intent"]:

        async def list_files(path: str, _intent: str):  # pyright: ignore[reportRedeclaration]
            """
            List files in the user's current directory. Always check again when asked.

            Parameters
            ----------
            path
                The path to list files from.
            _intent
                Reason for the request to explain the tool call to the user.
            """
            await asyncio.sleep(random.uniform(1, 10))
            return list_files_impl()

    else:

        async def list_files(path: str):  # pyright: ignore[reportRedeclaration]
            """
            List files in the user's current directory. Always check again when asked.
            """
            await asyncio.sleep(random.uniform(1, 10))
            return list_files_impl()

else:
    if TOOL_OPTS["with_intent"]:

        def list_files(path: str, _intent: str):  # pyright: ignore[reportRedeclaration]
            """
            List files in the user's current directory. Always check again when asked.

            Parameters
            ----------
            path
                The path to list files from.
            _intent
                Reason for the request to explain the tool call to the user.
            """
            time.sleep(random.uniform(1, 3))
            return list_files_impl()

    else:

        def list_files(path: str):  # pyright: ignore[reportRedeclaration]
            """
            List files in the user's current directory. Always check again when asked.
            """
            time.sleep(random.uniform(1, 3))
            return list_files_impl()

chat_client.register_tool(
    list_files,
    annotations=annotations,
)

ui.page_opts(fillable=True)

chat = Chat(id="chat")
chat.ui(
    messages=[
        """
<p class="suggestion submit">In three separate but parallel tool calls list the files in apps, data, docs</p>
<p class="suggestion submit">Write some basic Python code that demonstrates how to use pandas.</p>
<p class="suggestion submit">Brainstorm 10 ideas for a name for a package that creates interactive sparklines in tables.</p>
        """,
    ],
)


@chat.on_user_submit
async def handle_user_input(user_input: str):
    response = await chat_client.stream_async(user_input, content="all")
    await chat.append_message_stream(response)


ui.input_action_button("click", "Click me")


@reactive.effect
@reactive.event(input.click)
def _():
    ui.update_action_button(
        "click",
        label=f"Clicked {input.click()} times",
    )
