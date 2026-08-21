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
    toolbar_global: TagChild | None = None,
    navbar_options: Any = None,
    sidebar: bool | ChatSidebar | None = None,
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
    """
    Create the sole top-level UI item for a full-window Express chat page.

    The chat is the home page and remains mounted while users visit secondary
    pages. This function configures :func:`shiny.express.ui.page_opts`
    internally and owns the complete top-level page layout. Do not also call
    ``chat.ui()``, add unrelated top-level UI, wrap the returned chat root, or
    assign it to a variable. Compose additional UI through ``pages``,
    ``toolbar``, ``toolbar_global``, ``sidebar``, and ``artifact``.

    Parameters
    ----------
    title
        Page title displayed in the header. When it is a string and
        ``window_title`` is omitted, it is also used as the document title.
    icon
        Optional HTML child displayed next to ``title``.
    id
        Unique ID shared by the page shell and its chat. Use the same ID for
        the server-side :class:`~shinychat.express.Chat`.
    pages
        Secondary pages created with :func:`~shinychat.chat_nav_panel`.
    toolbar
        Optional home-page-scoped HTML child displayed with the navigation
        controls. A page's ``chat_nav_panel(toolbar=)`` can replace this
        segment.
    toolbar_global
        Optional persistent HTML child displayed after the page-scoped toolbar
        in the navigation controls.
    navbar_options
        Optional :func:`shiny.ui.navbar_options` that styles the page title bar.
        ``position`` and ``collapsible`` are unsupported because ``page_chat()``
        owns the full-window layout and responsive app menu.
    sidebar
        Home-page sidebar. When omitted or ``True``, the page uses the default
        conversation-history sidebar. ``False`` removes it, and a
        :class:`~shinychat.ChatSidebar` supplies custom content and behavior.
        Raw :class:`shiny.ui.Sidebar` objects are not supported.
    artifact
        Whether the chat has an artifact region. Pass a
        :class:`~shinychat.ChatArtifact` to configure its initial content and
        behavior.
    window_title
        Optional document title. Use this when ``title`` is an HTML child or
        when the browser title should differ from the displayed title.
    lang
        Optional language for the document's ``<html>`` element.
    theme
        Theme accepted by :func:`shiny.express.ui.page_opts`. By default,
        :func:`~shinychat.page_chat_theme` layers page-chat tokens over the
        ``"shiny"`` preset.
    messages
        Initial chat messages. See :meth:`shinychat.express.Chat.ui`.
    greeting
        Optional initial chat greeting. See :func:`~shinychat.chat_greeting`.
    placeholder
        Placeholder text for the chat input.
    width
        Maximum width of the chat content.
    icon_assistant
        Default icon for assistant messages. ``False`` removes it.
    enable_cancel
        Whether to show the streaming cancel control. When omitted, a chat
        constructed with ``client=`` enables it automatically.
    allow_attachments
        Whether to allow attachments, or a list of accepted MIME types. When
        omitted, a chat constructed with ``client=`` enables them
        automatically.
    footer
        Optional HTML content below the chat input.
    **kwargs
        Additional :func:`~shinychat.chat_ui` options and HTML attributes.
        ``page_chat()`` owns ``height``, ``fill``, and ``show_history``; these
        arguments cannot be overridden.

    Returns
    -------
    Tag
        The internally created chat root. It must remain the sole top-level
        Express UI item.

    Examples
    --------
    ```python
    from shiny import ui
    from shinychat import chat_nav_panel, chat_sidebar
    from shinychat.express import Chat, page_chat

    chat = Chat("chat")

    page_chat(
        "Assistant",
        pages=[
            chat_nav_panel("About", ui.p("About this app"), sidebar=False),
        ],
        sidebar=chat_sidebar(history=False),
    )
    ```

    See Also
    --------
    :func:`~shinychat.page_chat` : Create the same layout in a Core app.
    :func:`~shinychat.chat_sidebar` : Configure page sidebars.
    :func:`~shinychat.chat_nav_panel` : Configure secondary pages.
    :func:`~shinychat.chat_artifact` : Configure the artifact region.
    """
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
            toolbar_global=toolbar_global,
            navbar_options=navbar_options,
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
