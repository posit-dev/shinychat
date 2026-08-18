from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from math import isfinite
from typing import TYPE_CHECKING, Literal, cast

from htmltools import HTML, Tag, TagAttrValue, TagChild

if TYPE_CHECKING:
    from shiny.ui.css import CssUnit

__all__ = (
    "ChatArtifact",
    "ChatNavPanel",
    "ChatSidebar",
    "chat_artifact",
    "chat_nav_panel",
    "chat_sidebar",
    "chat_ui_history",
)

ChatSidebarOpen = Literal["auto", "open", "closed", "always"]

_CSS_WIDTH_RE = re.compile(
    r"^(?:"
    r"auto|inherit|fit-content|calc\(.+\)|"
    r"(?:\.[0-9]+|[0-9]+(?:\.[0-9]+)?)(?:%|in|cm|mm|ch|em|ex|rem|pt|pc|px|vh|vw|vmin|vmax)"
    r")$"
)


@dataclass(frozen=True)
class ChatSidebar:
    content: tuple[TagChild, ...]
    history: bool
    width: str
    open: ChatSidebarOpen
    resizable: bool


@dataclass(frozen=True)
class ChatArtifact:
    content: tuple[TagChild, ...]
    title: str | None
    width: str
    open: bool
    resizable: bool


@dataclass(frozen=True)
class ChatNavPanel:
    title: str
    content: tuple[TagChild, ...]
    value: str | None
    icon: TagChild | None
    sidebar: bool | ChatSidebar


def _validate_bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"`{name}` must be a bool, not {type(value).__name__}.")
    return value


def _validate_css_width(value: object, name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise TypeError(
            f"`{name}` must be a CSS width string or a positive number, "
            f"not {type(value).__name__}."
        )
    if isinstance(value, str):
        if not value.strip():
            raise ValueError(f"`{name}` must not be an empty CSS width.")
        if not _CSS_WIDTH_RE.fullmatch(value):
            raise ValueError(f"`{name}` must be a valid CSS width.")
        return value
    if not isfinite(value) or value <= 0:
        raise ValueError(f"`{name}` must be a finite, positive CSS width.")

    return f"{format(Decimal(str(value)).normalize(), 'f')}px"


def _validate_content(content: tuple[TagChild, ...], name: str) -> None:
    if any(isinstance(item, dict) for item in content):
        raise TypeError(
            f"`{name}` content must be HTML children, not an attribute dictionary."
        )


def chat_sidebar(
    *content: TagChild,
    history: bool = False,
    width: "CssUnit" = 280,
    open: ChatSidebarOpen | bool = "auto",
    resizable: bool = True,
) -> ChatSidebar:
    _validate_content(content, "chat_sidebar()")
    open_value: ChatSidebarOpen
    if open is True:
        open_value = "open"
    elif open is False:
        open_value = "closed"
    elif not isinstance(open, str):
        raise TypeError(f"`open` must be a string, not {type(open).__name__}.")
    elif open not in ("auto", "open", "closed", "always"):
        raise ValueError(
            '`open` must be one of "auto", "open", "closed", or "always", '
            f"not {open!r}."
        )
    else:
        open_value = cast(ChatSidebarOpen, open)
    return ChatSidebar(
        content=content,
        history=_validate_bool(history, "history"),
        width=_validate_css_width(width, "width"),
        open=open_value,
        resizable=_validate_bool(resizable, "resizable"),
    )


def chat_artifact(
    *content: TagChild,
    title: str | None = None,
    width: "CssUnit" = 400,
    open: bool = False,
    resizable: bool = True,
) -> ChatArtifact:
    _validate_content(content, "chat_artifact()")
    if title is not None and not isinstance(title, str):
        raise TypeError(
            f"`title` must be a string or None, not {type(title).__name__}."
        )
    return ChatArtifact(
        content=content,
        title=title,
        width=_validate_css_width(width, "width"),
        open=_validate_bool(open, "open"),
        resizable=_validate_bool(resizable, "resizable"),
    )


def chat_nav_panel(
    title: str,
    *content: TagChild,
    value: str | None = None,
    icon: TagChild | None = None,
    sidebar: bool | ChatSidebar = False,
) -> ChatNavPanel:
    if not isinstance(title, str):
        raise TypeError(
            f"`title` must be a string, not {type(title).__name__}."
        )
    if not title.strip():
        raise ValueError("`title` must not be an empty string.")
    _validate_content(content, "chat_nav_panel()")
    if value is not None and not isinstance(value, str):
        raise TypeError(
            f"`value` must be a string or None, not {type(value).__name__}."
        )
    if value == "":
        raise ValueError("`value` must not be an empty string.")
    if icon is not None and isinstance(icon, (bool, dict)):
        raise TypeError("`icon` must be an HTML child or None.")
    if not isinstance(sidebar, (bool, ChatSidebar)):
        raise TypeError(
            "`sidebar` must be False, True, or a shinychat `ChatSidebar`; "
            "raw Shiny Sidebar objects are not supported."
        )
    return ChatNavPanel(
        title=title,
        content=content,
        value=value,
        icon=icon,
        sidebar=sidebar,
    )


def chat_ui_history(id: str, **attrs: TagAttrValue) -> Tag:
    from shiny.module import resolve_id

    from ._html_deps_py_shiny import shinychat_dependency

    if "for" in attrs or "for_" in attrs:
        raise ValueError("`chat_ui_history()` sets its own `for` attribute.")
    for name, value in attrs.items():
        if (
            not isinstance(value, (str, int, float, bool, HTML))
            and value is not None
        ):
            raise TypeError(
                f"`{name}` must be an HTML attribute value, not "
                f"{type(value).__name__}."
            )

    return Tag(
        "shiny-chat-history",
        shinychat_dependency(),
        for_=resolve_id(id),
        **attrs,
    )


def render_chat_artifact(artifact: ChatArtifact) -> Tag:
    return Tag(
        "shiny-chat-artifact",
        *artifact.content,
        title=artifact.title,
        width=artifact.width,
        open=artifact.open,
        resizable="false" if not artifact.resizable else None,
    )
