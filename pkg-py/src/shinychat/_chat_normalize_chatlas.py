import json
import os
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeGuard

from htmltools import RenderedHTML, Tag, TagChild, Tagifiable, TagList
from packaging import version

if TYPE_CHECKING:
    from chatlas.types import ContentToolRequest, ContentToolResult

__all__ = [
    "ToolResultDisplay",
]


@dataclass
class ToolCardComponent:
    "Data class mirroring the ShinyToolCard component class in chat-tools.ts"

    request_id: str
    """
    Unique identifier for the tool request or result.
    This value links a request to a result and is therefore not unique on the page.
    """

    tool_name: str
    "Name of the tool being executed, e.g. `get_weather`."

    tool_title: str | None = None
    "Display title for the card. If not provided, falls back to `tool_name`."

    icon: TagChild = None
    "HTML content for the icon displayed in the card header."

    intent: str | None = None
    "Optional intent description explaining the purpose of the tool execution."

    expanded: bool = False
    "Controls whether the card content is expanded/visible."


@dataclass
class ToolRequestComponent(ToolCardComponent):
    "Data class mirroring the ShinyToolRequest component class from chat-tools.ts"

    arguments: str = ""
    "The function arguments as requested by the LLM, typically in JSON format."

    def tagify(self):
        icon_ui = TagList(self.icon).render()

        return Tag(
            "shiny-tool-request",
            request_id=self.request_id,
            tool_name=self.tool_name,
            tool_title=self.tool_title,
            icon=icon_ui["html"] if self.icon else None,
            intent=self.intent,
            expanded="" if self.expanded else None,
            arguments=self.arguments,
            *icon_ui["dependencies"],
        )


ValueType = Literal["html", "markdown", "text", "code"]


@dataclass
class ToolResultComponent(ToolCardComponent):
    "Data class mirroring the ShinyToolResult component class from chat-tools.ts"

    request_call: str = ""
    "The original tool call that generated this result. Used to display the tool invocation."

    status: Literal["success", "error"] = "success"
    """
    The status of the tool execution. When set to "error", displays in an error state with
    red text and an exclamation icon.
    """

    show_request: bool = True
    "Should the tool request should be displayed alongside the result?"

    value: TagChild = None
    "The actual result content returned by the tool execution."

    value_type: ValueType = "code"
    """
    Specifies how the value should be rendered. Supported types:
        - "html": Renders the value as raw HTML
        - "text": Renders the value as plain text in a paragraph
        - "markdown": Renders the value as Markdown (default)
        - "code": Renders the value as a code block
     Any other value defaults to markdown rendering.
    """

    def tagify(self):
        icon_ui = TagList(self.icon).render()

        if self.value_type == "html":
            value_ui = TagList(self.value).render()
        else:
            value_ui: "RenderedHTML" = {
                "html": str(self.value),
                "dependencies": [],
            }

        return Tag(
            "shiny-tool-result",
            request_id=self.request_id,
            tool_name=self.tool_name,
            tool_title=self.tool_title,
            icon=icon_ui["html"] if self.icon else None,
            intent=self.intent,
            request_call=self.request_call,
            status=self.status,
            value=value_ui["html"],
            value_type=self.value_type,
            show_request="" if self.show_request else None,
            expanded="" if self.expanded else None,
            *icon_ui["dependencies"],
            *value_ui["dependencies"],
        )


@dataclass
class ToolResultDisplay:
    "Data class to for users to customize how tool results are displayed"

    html: TagChild = None
    markdown: str | None = None
    text: str | None = None
    show_request: bool = True
    open: bool = False
    title: str | None = None
    icon: TagChild = None
    expanded: bool | None = None


def tool_request_contents(x: "ContentToolRequest") -> Tagifiable:
    if tool_display_override() == "none":
        return TagList()

    # These content objects do have tagify() methods,
    # but that's for legacy behavior
    if is_legacy():
        return x

    intent = None
    if isinstance(x.arguments, dict):
        intent = x.arguments.get("_intent")

    tool_title = None
    if x.tool and x.tool.annotations:
        tool_title = x.tool.annotations.get("title")

    return ToolRequestComponent(
        request_id=x.id,
        tool_name=x.name,
        arguments=json.dumps(x.arguments),
        intent=intent,
        tool_title=tool_title,
    )


def tool_result_contents(x: "ContentToolResult") -> Tagifiable:
    if tool_display_override() == "none":
        return TagList()

    # These content objects do have tagify() methods,
    # but that's the legacy behavior
    if is_legacy():
        return x

    if x.request is None:
        raise ValueError(
            "`ContentToolResult` objects must have an associated `.request` attribute."
        )

    # TODO: look into better formating of the call?
    request_call = json.dumps(
        {
            "id": x.id,
            "name": x.request.name,
            "arguments": x.request.arguments,
        },
        indent=2,
    )

    display = get_tool_result_display(x, x.request)
    value, value_type = tool_result_display(x, display)

    intent = None
    if isinstance(x.arguments, dict):
        intent = x.arguments.get("_intent")

    tool = x.request.tool
    tool_title = None
    if tool and tool.annotations:
        tool_title = tool.annotations.get("title")

    # display (tool *result* level) takes precedence over
    # annotations (tool *definition* level)
    return ToolResultComponent(
        request_id=x.id,
        request_call=request_call,
        tool_name=x.request.name,
        tool_title=display.title or tool_title,
        status="success" if x.error is None else "error",
        value=value,
        value_type=value_type,
        icon=display.icon,
        intent=intent,
        show_request=display.show_request,
        expanded=display.open,
    )


def get_tool_result_display(
    x: "ContentToolResult",
    request: "ContentToolRequest",
) -> ToolResultDisplay:
    if not isinstance(x.extra, dict) or tool_display_override() == "basic":
        return ToolResultDisplay()

    display = x.extra.get("display", ToolResultDisplay())

    if isinstance(display, ToolResultDisplay):
        return display

    if isinstance(display, dict):
        return ToolResultDisplay(**display)

    warnings.warn(
        "Invalid `display` value inside `ContentToolResult(extra={'display': display})` "
        f"from {request.name} (call id: {request.id}). "
        "Expected either a `shinychat.ToolResultDisplay()` instance or a dictionary, "
        f"but got {type(display)}."
    )

    return ToolResultDisplay()


def tool_result_display(
    x: "ContentToolResult",
    display: ToolResultDisplay,
) -> tuple[TagChild, ValueType]:
    if x.error is not None:
        return str(x.error), "code"

    if tool_display_override() == "basic":
        return str(x.get_model_value()), "code"

    if display.html is not None:
        return display.html, "html"

    if display.markdown is not None:
        return display.markdown, "markdown"

    if display.text is not None:
        return display.text, "text"

    return str(x.get_model_value()), "code"


async def hide_corresponding_request(x: "ContentToolResult"):
    if x.request is None:
        return

    session = None
    try:
        from shiny.session import get_current_session

        session = get_current_session()
    except Exception:
        return

    if session is None:
        return

    await session.send_custom_message(
        "shiny-tool-request-hide",
        x.request.id,  # type: ignore
    )


def is_tool_result(val: object) -> "TypeGuard[ContentToolResult]":
    try:
        from chatlas.types import ContentToolResult

        return isinstance(val, ContentToolResult)
    except ImportError:
        return False


# Tools were added to ContentToolRequest class until 0.11.1
def is_legacy():
    import chatlas

    v = chatlas._version.version_tuple
    ver = f"{v[0]}.{v[1]}.{v[2]}"
    return version.parse(ver) < version.parse("0.11.1")


def tool_display_override() -> Literal["none", "basic", "rich"]:
    val = os.getenv("SHINYCHAT_TOOL_DISPLAY", "rich")
    if val == "rich" or val == "basic" or val == "none":
        return val
    else:
        raise ValueError(
            'The `SHINYCHAT_TOOL_DISPLAY` env var must be one of: "none", "basic", or "rich"'
        )
