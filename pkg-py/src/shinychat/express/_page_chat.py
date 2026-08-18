from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable, Optional, Sequence, Union

from htmltools import HTML, Tag, TagChild, TagList

from .._page_chat import (
    ChatArtifact,
    ChatNavPanel,
    ChatSidebar,
    _create_page_chat_root,
    _render_page_chat,
)
from .._utils_types import MISSING, MISSING_TYPE

if TYPE_CHECKING:
    from shiny.ui.css import CssUnit

    from .._chat_types import ChatGreeting, ChatMessage, ChatMessageDict

_OWNERSHIP_ERROR = (
    "shinychat.express.page_chat() owns the page layout; "
    "remove unrelated top-level UI."
)


def page_chat(
    title: TagChild,
    icon: TagChild | None = None,
    *,
    id: str = "chat",
    pages: Sequence[ChatNavPanel] | None = None,
    toolbar: TagChild | None = None,
    sidebar: bool | ChatSidebar = True,
    artifact: bool | ChatArtifact = True,
    window_title: str | None = None,
    lang: str | None = None,
    theme: Any = None,
    messages: Optional[
        Iterable[str | TagChild | "ChatMessageDict" | "ChatMessage" | Any]
    ] = None,
    greeting: Optional[Union[str, HTML, Tag, TagList, "ChatGreeting"]] = None,
    placeholder: str = "Enter a message...",
    width: "CssUnit" = "min(680px, 100%)",
    icon_assistant: Optional[HTML | Tag | TagList | bool] = None,
    enable_cancel: "bool | MISSING_TYPE" = MISSING,
    allow_attachments: "bool | list[str] | MISSING_TYPE" = MISSING,
    footer: Optional[TagChild] = None,
    **kwargs: Any,
) -> Tag:
    """Create the sole top-level UI item for a full-window Express chat page."""
    from shiny.express import ui

    chat_root = _create_page_chat_root(
        id=id,
        artifact=artifact,
        messages=messages,
        greeting=greeting,
        placeholder=placeholder,
        width=width,
        icon_assistant=icon_assistant,
        enable_cancel=enable_cancel,
        allow_attachments=allow_attachments,
        footer=footer,
        **kwargs,
    )

    def page_fn(*items: TagChild, **page_options: Any) -> Tag:
        if len(items) != 1 or items[0] is not chat_root:
            raise RuntimeError(_OWNERSHIP_ERROR)

        return _render_page_chat(
            chat_root,
            page_options["title"],
            icon,
            id=id,
            pages=pages,
            toolbar=toolbar,
            sidebar=sidebar,
            window_title=page_options["window_title"],
            lang=page_options["lang"],
            theme=page_options["theme"],
        )

    ui.page_opts(
        title=title,  # pyright: ignore[reportArgumentType]
        window_title=window_title,  # pyright: ignore[reportArgumentType]
        lang=lang,  # pyright: ignore[reportArgumentType]
        theme=theme,
        page_fn=page_fn,
    )
    return chat_root
