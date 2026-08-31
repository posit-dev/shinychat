from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Optional, Sequence, Union

from htmltools import (
    HTML,
    HTMLDependency,
    MetadataNode,
    RenderedHTML,
    ReprHtml,
    Tag,
    Tagifiable,
    TagList,
)
from packaging import version
from pydantic import BaseModel, field_serializer, field_validator
from typing_extensions import TypeAliasType

from ._chat_types import ChatMessage, ToolRequestBlock, ToolResultBlock
from ._htmltools_serialization import SerializedHTML, serialize_htmltools

if TYPE_CHECKING:
    from chatlas.types import ContentToolRequest, ContentToolResult
    from htmltools import Tagified

__all__ = [
    "ToolResultDisplay",
]

# A version of the (recursive) TagChild type that actually works with Pydantic
# https://docs.pydantic.dev/2.11/concepts/types/#named-type-aliases
TagNode = Union[Tagifiable, MetadataNode, ReprHtml, str, HTML]
TagChild = TypeAliasType(
    "TagChild",
    "Union[TagNode, TagList, float, None, Sequence[TagChild]]",
)


def _serialize_htmltools(
    value: TagChild,
) -> Optional[SerializedHTML]:
    if value is None:
        return None
    return serialize_htmltools(value)


class ToolCardComponent(BaseModel):
    "A class that mirrors the ShinyToolCard component class in chat-tools.ts"

    request_id: str
    """
    Unique identifier for the tool request or result.
    This value links a request to a result and is therefore not unique on the page.
    """

    tool_name: str
    "Name of the tool being executed, e.g. `get_weather`."

    tool_title: Optional[str] = None
    "Display title for the card. If not provided, falls back to `tool_name`."

    icon: TagChild = None
    "HTML content for the icon displayed in the card header."

    intent: Optional[str] = None
    "Optional intent description explaining the purpose of the tool execution."

    grouping: Optional[Literal["none", "tool", "all"]] = None
    """
    Per-tool override for how consecutive tool calls are grouped in the UI.
    Read from the tool's `annotations["grouping"]`. If not provided, falls
    back to the chat-level `tool_grouping` setting.
    """

    model_config = {"arbitrary_types_allowed": True}

    @field_serializer("icon")
    def _serialize_icon(self, value: TagChild) -> Optional[SerializedHTML]:
        return _serialize_htmltools(value)

    @field_validator("icon", mode="before")
    @classmethod
    def _validate_icon(cls, value: TagChild) -> TagChild:
        if isinstance(value, dict):
            return restore_rendered_html(value)
        else:
            return value


class ToolRequestComponent(ToolCardComponent):
    "A class that mirrors the ShinyToolRequest component class from chat-tools.ts"

    arguments: str = ""
    "The function arguments as requested by the LLM, typically in JSON format."

    def tagify(self) -> Tagified:
        icon_ui = TagList(self.icon).render()

        return Tag(
            "shiny-tool-request",
            data_shinychat_react=True,
            request_id=self.request_id,
            tool_name=self.tool_name,
            tool_title=self.tool_title,
            icon=icon_ui["html"] if self.icon else None,
            intent=self.intent,
            arguments=self.arguments,
            grouping=self.grouping,
            *icon_ui["dependencies"],
        ).tagify()


ValueType = Literal["html", "markdown", "text", "code", "content_extra"]


def is_content(value: object) -> bool:
    from chatlas.types import Content

    return isinstance(value, Content)


def is_content_extra(value: object) -> bool:
    from chatlas.types import ContentImageInline, ContentImageRemote, ContentPDF

    return isinstance(
        value, (ContentImageInline, ContentImageRemote, ContentPDF)
    )


def as_content_extra_item(value: object) -> dict[str, str]:
    from chatlas.types import ContentImageInline, ContentImageRemote, ContentPDF

    if isinstance(value, ContentImageRemote):
        return {"type": "image", "src": value.url}
    elif isinstance(value, ContentImageInline):
        return {
            "type": "image",
            "src": f"data:{value.image_content_type};base64,{value.data}",
        }
    elif isinstance(value, ContentPDF):
        return {"type": "pdf", "filename": value.filename or "document.pdf"}
    raise TypeError(f"Unexpected content extra type: {type(value)}")


def as_content_extra_item_or_text(value: object) -> dict[str, str]:
    from chatlas.types import ContentText

    if is_content_extra(value):
        return as_content_extra_item(value)
    elif isinstance(value, ContentText):
        return {"type": "text", "value": value.text, "value_type": "markdown"}
    else:
        return {"type": "text", "value": str(value), "value_type": "markdown"}


class ToolResultComponent(ToolCardComponent):
    "A class that mirrors the ShinyToolResult component class from chat-tools.ts"

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

    footer: TagChild = None
    "Optional HTML content to display in the card footer (below the card body)."

    full_screen: bool = False
    "Controls whether a fullscreen toggle button is displayed on the card."

    open_style: Literal["minimal", "framed"] = "minimal"
    "Controls whether the result uses the minimal or framed style when open."

    expanded: bool = False
    "Controls whether the card content is expanded/visible."

    label: Optional[str] = None
    "A short, per-call identifying value shown alongside the tool title."

    value_preview: Optional[str] = None
    "A terse per-call preview of the tool result, shown in the condensed view."

    custom_display: bool = False
    """
    Internal provenance marker only: set when `_chat_normalize.py` wraps an
    author's own `message_content_chunk` override for a `ContentToolResult`
    subclass through its internal normalization boundary, never by an author.
    Not part of `ToolResultDisplay` or any author-facing
    API. Records *that* shinychat performed the wrap, not how the client
    should behave -- that interpretation stays free to change independently.
    """

    def tagify(self) -> Tagified:
        icon_ui = TagList(self.icon).render()

        if self.value_type == "html":
            value_ui = TagList(self.value).render()
        else:
            value_ui = RenderedHTML(
                html=str(self.value),
                dependencies=[],
            )

        footer_ui = TagList(self.footer).render()

        return Tag(
            "shiny-tool-result",
            data_shinychat_react=True,
            request_id=self.request_id,
            tool_name=self.tool_name,
            tool_title=self.tool_title,
            icon=icon_ui["html"] if self.icon else None,
            intent=self.intent,
            request_call=self.request_call or None,
            status=self.status,
            value=value_ui["html"],
            value_type=self.value_type,
            show_request="" if self.show_request else None,
            expanded="" if self.expanded else None,
            footer=footer_ui["html"] if self.footer else None,
            full_screen="" if self.full_screen else None,
            open_style="framed" if self.open_style == "framed" else None,
            grouping=self.grouping,
            label=self.label,
            value_preview=self.value_preview,
            custom_display="" if self.custom_display else None,
            *icon_ui["dependencies"],
            *value_ui["dependencies"],
            *footer_ui["dependencies"],
        ).tagify()


class ShinyToolCardMessage(ChatMessage):
    """Marker for shinychat's own rich tool-result card."""

    pass


def citation_aside(
    url: str,
    title: Optional[str],
    grounded_span: Optional[str] = None,
    cited_quote: Optional[str] = None,
) -> str:
    "Render a chatlas web citation as <shiny-aside> markup."
    return str(
        Tag(
            "shiny-aside",
            Tag("a", title or url, href=url),
            data_citation="",
            url=url,
            grounded_span=grounded_span,
            cited_quote=cited_quote,
        )
    )


class ToolResultDisplay(BaseModel):
    """
    Customize the condensed display for a tool result.

    Assign a `ToolResultDisplay` instance to a
    [`chatlas.ContentToolResult`](https://posit-dev.github.io/chatlas/reference/types.ContentToolResult.html)
    in its ``extra={"display": ...}`` metadata. Tool calls normally appear as a
    compact activity row, optionally expand into a grouped call list, and drill
    into a full request/result card. ``ToolResultDisplay`` customizes that row
    and card without replacing either.

    Use a present-tense definition title while the tool is running, then a
    settled result title here when that improves the wording. For example,
    register a tool with ``annotations={"title": "Looking up weather"}`` and
    return ``title="Looked up weather for Duluth"``. In a single-call row, the
    result title replaces the definition title when the result arrives. A
    multi-call group keeps the shared definition title in its group row and can
    use distinct result titles to identify calls in the expanded list.
    shinychat does not conjugate titles automatically.

    ``label`` and ``value_preview`` are compact, per-call metadata shown in the
    activity row and grouped call list. Use them to distinguish repeated calls
    without opening the card. ``html``, ``markdown``, and ``text`` customize the
    result body inside the drill-down card. ``open_style="framed"`` opts a
    substantial rich result into Shiny Chat's expanded frame;
    ``open_style="minimal"`` retains the existing drill-down presentation.
    Framing belongs to the normal tool UI. To replace the card with standalone
    UI instead, register a custom ``message_content`` or
    ``message_content_chunk`` handler for a ``ContentToolResult`` subclass;
    standalone output is not framed.

    See the [Tool calling guide](https://shiny.posit.co/py/docs/genai-tools.html)
    for complete tool-display examples.

    Examples
    --------

    ```python
    import chatlas as ctl
    from shiny import ui
    from shinychat.types import ToolResultDisplay


    def my_tool():
        display = ToolResultDisplay(
            html=ui.div(...),
            footer=ui.div(...),
            full_screen=True,
            open_style="framed",
        )
        return ctl.ContentToolResult(
            value="Value the model sees",
            extra={"display": display},
        )


    chat_client = ctl.ChatAuto()
    chat_client.register_tool(my_tool)
    ```

    Display fields
    --------------
    - ``title``:
        The settled title for this result and its drill-down card. It replaces
        the definition title in a single-call row. In a multi-call group, a
        distinct result title can identify the call in the expanded call list.
    - ``label``:
        A short, per-call identifying value shown alongside the title
        (e.g. a filename or query). Distinguishes this call from other calls
        to the same tool. Without one, shinychat falls back to the call's own
        `title` (when it differs from the group's), then a short preview of the
        call's arguments, then the tool name.
    - ``value_preview``:
        A terse, per-call preview of the tool result, shown in the condensed
        activity row and grouped call list before the full result is expanded.
    - ``icon``:
        An icon to display alongside the title in the activity row and
        drill-down card.
    - ``show_request``:
        Whether to show the tool request inside the drill-down card.
    - ``open``:
        Whether the drill-down card is expanded by default.
    - ``full_screen``:
        Whether to display a fullscreen toggle button on the drill-down card.
    - ``open_style``:
        Use ``"framed"`` to opt an expanded normal rich result into Shiny
        Chat's frame. ``"minimal"`` retains the existing presentation.
    - ``html``:
        Custom HTML content inside the drill-down card, in place of the
        default result display.
    - ``markdown``:
        Custom Markdown string inside the drill-down card, in place of the
        default result display.
    - ``text``:
        Custom plain text string inside the drill-down card, in place of the
        default result display.
    - ``footer``:
        Optional HTML content to display in the drill-down card footer.
    """

    title: Optional[str] = None
    label: Optional[str] = None
    value_preview: Optional[str] = None
    icon: TagChild = None
    html: TagChild = None
    show_request: bool = True
    open: bool = False
    full_screen: bool = False
    open_style: Literal["minimal", "framed"] = "minimal"
    markdown: Optional[str] = None
    text: Optional[str] = None
    footer: TagChild = None

    model_config = {"arbitrary_types_allowed": True}

    @field_serializer("html", "icon", "footer")
    def _serialize_html_icon(self, value: TagChild) -> Optional[SerializedHTML]:
        return _serialize_htmltools(value)

    @field_validator("html", "icon", "footer", mode="before")
    @classmethod
    def _validate_html_icon(cls, value: TagChild) -> TagChild:
        if isinstance(value, dict):
            return restore_rendered_html(value)
        else:
            return value


GroupingValue = Literal["none", "tool", "all"]


@dataclass(frozen=True)
class ResolvedToolAnnotations:
    title: Optional[str] = None
    icon: Any = None
    grouping: Optional[GroupingValue] = None


def as_grouping(value: object) -> Optional[GroupingValue]:
    "Validate a tool annotation's `grouping` value, ignoring anything unexpected."
    if value in ("none", "tool", "all"):
        return value
    return None


def _annotation_extra(annotations: object) -> dict[str, Any]:
    "Read a tool annotation's `extra` sub-dict, ignoring anything unexpected."
    if not isinstance(annotations, dict):
        return {}
    extra = annotations.get("extra")
    return extra if isinstance(extra, dict) else {}


def resolve_tool_annotations(tool: Any) -> ResolvedToolAnnotations:
    """Resolve the shared title, icon, and grouping annotation policy."""
    if not tool or not tool.annotations:
        return ResolvedToolAnnotations()

    annotations = tool.annotations
    extra = _annotation_extra(annotations)
    return ResolvedToolAnnotations(
        title=annotations.get("title"),
        icon=extra.get("icon") or annotations.get("icon"),
        grouping=as_grouping(extra.get("grouping"))
        or as_grouping(annotations.get("grouping")),
    )


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

    annotations = resolve_tool_annotations(x.tool)

    # Icon strings are HTML and never get escaped
    icon = (
        HTML(annotations.icon)
        if isinstance(annotations.icon, str)
        else annotations.icon
    )

    return ToolRequestComponent(
        request_id=x.id,
        tool_name=x.name,
        arguments=json.dumps(x.arguments),
        intent=intent,
        tool_title=annotations.title,
        # The tool *definition* icon. The result element sends the result's own
        # icon (falling back to this one), so the client needs both to tell a
        # result-specific icon from the tool's shared identity.
        icon=icon,
        grouping=annotations.grouping,
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

    annotations = resolve_tool_annotations(x.request.tool)

    # Icon strings and HTML display never get escaped
    icon = display.icon or annotations.icon
    if icon and isinstance(icon, str):
        icon = HTML(icon)
    if value_type == "html" and isinstance(value, str):
        value = HTML(value)

    # display (tool *result* level) takes precedence over
    # annotations (tool *definition* level)
    return ToolResultComponent(
        request_id=x.id,
        request_call=request_call,
        tool_name=x.request.name,
        tool_title=display.title or annotations.title,
        status="success" if x.error is None else "error",
        value=value,
        value_type=value_type,
        icon=icon,
        intent=intent,
        show_request=display.show_request,
        expanded=display.open,
        footer=display.footer,
        full_screen=display.full_screen,
        open_style=display.open_style,
        grouping=annotations.grouping,
        label=display.label,
        value_preview=display.value_preview,
    )


def tool_request_block(
    component: ToolRequestComponent,
) -> "tuple[ToolRequestBlock, list[HTMLDependency]]":
    """Build the structured `tool_request` wire block from a card component.

    Mirrors ``ToolRequestComponent.tagify()``'s rendering but produces the
    typed envelope instead of markup.
    """
    deps: list[HTMLDependency] = []

    block: ToolRequestBlock = {
        "type": "tool_request",
        "version": 1,
        "request_id": component.request_id,
        "tool_name": component.tool_name,
    }

    if component.tool_title is not None:
        block["title"] = component.tool_title
    if component.intent is not None:
        block["intent"] = component.intent
    if component.arguments:
        block["arguments"] = component.arguments
    if component.grouping is not None:
        block["grouping"] = component.grouping

    # Icon strings are HTML and never get escaped
    if component.icon is not None:
        icon_ui = TagList(component.icon).render()
        block["icon"] = str(icon_ui["html"])
        deps.extend(icon_ui["dependencies"])

    return block, deps


def tool_request_message(request: Tagifiable) -> ChatMessage:
    """Wrap shinychat's rich tool-request card in a block-carrying message."""
    if isinstance(request, ToolRequestComponent):
        # The default rich path emits the structured `tool_request` envelope.
        # The tagify code is retained for the legacy/none overrides.
        # Unlike results, requests get a plain ChatMessage: the ShinyToolCardMessage marker
        # exists for the result custom-wrap postprocessing, which requests
        # skip.
        block, deps = tool_request_block(request)
        msg = ChatMessage(content="", blocks=[block])
        msg.html_deps = deps + msg.html_deps
        return msg
    return ChatMessage(content=request)


def tool_result_block(
    component: ToolResultComponent,
) -> "tuple[ToolResultBlock, list[HTMLDependency]]":
    """Build the structured `tool_result` wire block from a card component.

    Mirrors ``ToolResultComponent.tagify()``'s rendering but produces the
    typed envelope instead of markup.
    """
    deps: list[HTMLDependency] = []

    block: ToolResultBlock = {
        "type": "tool_result",
        "version": 1,
        "request_id": component.request_id,
        "tool_name": component.tool_name,
        "status": component.status,
        "value_type": component.value_type,
        "show_request": component.show_request,
    }

    if component.tool_title is not None:
        block["title"] = component.tool_title
    if component.intent is not None:
        block["intent"] = component.intent
    if component.request_call:
        block["request_call"] = component.request_call
    if component.label is not None:
        block["label"] = component.label
    if component.value_preview is not None:
        block["value_preview"] = component.value_preview
    if component.grouping is not None:
        block["grouping"] = component.grouping
    if component.expanded:
        block["expanded"] = True
    if component.full_screen:
        block["full_screen"] = True
    if component.custom_display:
        block["custom_display"] = True
    if component.open_style == "framed":
        block["open_style"] = "framed"

    # Icon strings are HTML and never get escaped
    if component.icon is not None:
        icon_ui = TagList(component.icon).render()
        block["icon"] = str(icon_ui["html"])
        deps.extend(icon_ui["dependencies"])

    if component.value is not None:
        if component.value_type == "html":
            value_ui = TagList(component.value).render()
            block["value"] = str(value_ui["html"])
            deps.extend(value_ui["dependencies"])
        else:
            block["value"] = str(component.value)

    if component.footer is not None:
        footer_ui = TagList(component.footer).render()
        block["footer"] = str(footer_ui["html"])
        deps.extend(footer_ui["dependencies"])

    return block, deps


def tool_result_message(result: Tagifiable) -> ChatMessage:
    """Wrap shinychat's rich tool card in a marker message."""
    if isinstance(result, ToolResultComponent):
        # The default rich path emits the structured `tool_result` envelope.
        # The tagify code is retained for the legacy/none overrides.
        block, deps = tool_result_block(result)
        msg = ShinyToolCardMessage(content="", blocks=[block])
        msg.html_deps = deps + msg.html_deps
        return msg
    return ChatMessage(content=result)


def wrap_custom_tool_result(
    *,
    request_id: str,
    tool_name: str,
    status: Literal["success", "error"],
    # Not annotated `TagChild`: that name is rebound in this module to a
    # pydantic `TypeAliasType` whose recursive `Sequence[TagChild]` arm
    # pyright cannot resolve in a plain function signature. These are the only
    # two shapes callers pass -- tags for `value_type="html"`, a plain string
    # for every other mode, matching the split in `tagify()`.
    value: Union[Tagifiable, str],
    value_type: ValueType,
    grouping: Optional[GroupingValue],
) -> Tagifiable:
    """Build the `<shiny-tool-result>` wrapper for an author's custom result UI.

    Kept as a factory here so the caller only sees the opaque `Tagifiable`
    return type.
    """
    return ToolResultComponent(
        request_id=request_id,
        tool_name=tool_name,
        status=status,
        value=value,
        # Supplied by the caller, which mirrors the content mode the message
        # already had, so wrapping never changes how the author's output
        # renders (notably: a plain-string return stays on the markdown path
        # rather than being promoted to `RawHTML`'s live `innerHTML`).
        value_type=value_type,
        # Keep the wire minimal: none of these render for a migrated call.
        show_request=False,
        grouping=grouping,
        # Internal provenance marker only ("shinychat wrapped an author's
        # custom output"), not part of any author-facing API and not
        # surfaced by `ToolResultDisplay`.
        custom_display=True,
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

    if is_content_extra(x.value):
        return json.dumps([as_content_extra_item(x.value)]), "content_extra"

    if isinstance(x.value, (list, tuple)) and any(
        is_content(v) for v in x.value
    ):
        items = [as_content_extra_item_or_text(v) for v in x.value]
        return json.dumps(items), "content_extra"

    return str(x.get_model_value()), "code"


# Tools started getting added to ContentToolRequest staring with 0.11.1
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


def restore_rendered_html(x: dict[str, Any]):
    from htmltools import HTMLDependency

    if "html" not in x or "dependencies" not in x:
        raise ValueError(f"Don't know how to restore HTML from {x}")

    deps: list[HTMLDependency] = []
    for d in x["dependencies"]:
        if not isinstance(d, dict):
            continue
        name = d["name"]
        version = d["version"]
        other = {k: v for k, v in d.items() if k not in ("name", "version")}
        # TODO: warn if the source is a tempdir?
        deps.append(HTMLDependency(name=name, version=version, **other))

    res = TagList(HTML(x["html"]), *deps)
    if not deps:
        return res

    session = None
    try:
        from shiny.session import get_current_session

        session = get_current_session()
    except Exception:
        pass

    # De-dupe dependencies for the current Shiny session
    if session:
        session._process_ui(res)

    return res
