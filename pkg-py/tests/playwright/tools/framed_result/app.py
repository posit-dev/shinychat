from chatlas.types import ContentToolRequest, ContentToolResult
from shiny import reactive
from shiny.express import input, ui
from shinychat import message_content_chunk
from shinychat.express import Chat
from shinychat.types import ChatMessage, ToolResultDisplay

ui.page_opts(fillable=True, title="Framed Tool Result Test")


class CustomFramedResult(ContentToolResult):
    """A custom result whose author-rendered output bypasses tool-card chrome."""


@message_content_chunk.register
def render_custom_framed_result(message: CustomFramedResult) -> ChatMessage:
    return ChatMessage(
        content=ui.div(
            "Custom standalone result", id="custom-standalone-output"
        )
    )


def tool_request(id: str, name: str) -> ContentToolRequest:
    return ContentToolRequest(id=id, name=name, arguments={})


async def append_single_result(
    *,
    id: str,
    name: str,
    value: str,
    display: ToolResultDisplay,
    error: Exception | None = None,
) -> None:
    request = tool_request(id, name)
    await chat.append_message_stream(
        (
            request,
            ContentToolResult(
                value=value,
                request=request,
                error=error,
                extra={"display": display},
            ),
        )
    )


async def append_grouped_results() -> None:
    framed_request = tool_request("framed-pair", "pair_tool")
    default_request = tool_request("default-pair", "pair_tool")
    await chat.append_message_stream(
        (
            framed_request,
            default_request,
            ContentToolResult(
                value="Framed grouped body",
                request=framed_request,
                extra={
                    "display": ToolResultDisplay(
                        text="Framed grouped body",
                        label="framed",
                        open_style="framed",
                    )
                },
            ),
            ContentToolResult(
                value="Default grouped body",
                request=default_request,
                extra={
                    "display": ToolResultDisplay(
                        text="Default grouped body",
                        label="default",
                    )
                },
            ),
        )
    )


async def append_custom_result() -> None:
    request = tool_request("custom-framed", "custom_tool")
    await chat.append_message_stream(
        (
            request,
            CustomFramedResult(
                value="The custom handler owns this output.",
                request=request,
                extra={"display": ToolResultDisplay(open_style="framed")},
            ),
        )
    )


chat = Chat(id="chat")
chat.ui(messages=["Use the controls to add deterministic tool results."])

ui.input_action_button("add_framed", "Add framed result")
ui.input_action_button("add_default", "Add default result")
ui.input_action_button("add_grouped", "Add grouped results")
ui.input_action_button("add_fullscreen", "Add fullscreen result")
ui.input_action_button("add_error", "Add errored result")
ui.input_action_button("add_custom", "Add custom result")


@reactive.effect
@reactive.event(input.add_framed)
async def add_framed_result() -> None:
    await append_single_result(
        id="framed-single",
        name="framed_tool",
        value="Recognizable framed body",
        display=ToolResultDisplay(
            text="Recognizable framed body",
            footer=ui.span("Recognizable framed footer"),
            open_style="framed",
        ),
    )


@reactive.effect
@reactive.event(input.add_default)
async def add_default_result() -> None:
    await append_single_result(
        id="default-single",
        name="default_tool",
        value="Recognizable default body",
        display=ToolResultDisplay(
            text="Recognizable default body",
            footer=ui.span("Recognizable default footer"),
        ),
    )


@reactive.effect
@reactive.event(input.add_grouped)
async def add_grouped_results() -> None:
    await append_grouped_results()


@reactive.effect
@reactive.event(input.add_fullscreen)
async def add_fullscreen_result() -> None:
    await append_single_result(
        id="framed-fullscreen",
        name="fullscreen_tool",
        value="Fullscreen framed body",
        display=ToolResultDisplay(
            text="Fullscreen framed body",
            full_screen=True,
            open_style="framed",
        ),
    )


@reactive.effect
@reactive.event(input.add_error)
async def add_error_result() -> None:
    await append_single_result(
        id="framed-error",
        name="error_tool",
        value="The model never sees this.",
        error=ValueError("Recognizable framed error"),
        display=ToolResultDisplay(open_style="framed"),
    )


@reactive.effect
@reactive.event(input.add_custom)
async def add_custom_result() -> None:
    await append_custom_result()
