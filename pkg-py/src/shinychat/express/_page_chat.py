from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Optional, Sequence, Union

from htmltools import HTML, MetadataNode, Tag, TagChild, TagList

from .._page_chat import (
    ChatDrawer,
    ChatNavPanel,
    ChatSidebar,
    _create_page_chat_root,
    _render_page_chat,
)
from .._utils_types import MISSING, MISSING_TYPE

if TYPE_CHECKING:
    from shiny.types import NavSetArg
    from shiny.ui import Theme
    from shiny.ui._html_deps_external import ThemeProvider
    from shiny.ui.css import CssUnit

    from .._chat_types import ChatGreeting, ChatMessage, ChatMessageDict

_OWNERSHIP_ERROR = (
    "shinychat.express.page_chat() owns the page layout; "
    "remove unrelated top-level UI."
)


def page_chat(
    title: TagChild,
    *,
    id: str = "chat",
    icon: TagChild | None = None,
    pages_navbar: Sequence[ChatNavPanel | NavSetArg | MetadataNode]
    | None = None,
    toolbar: TagChild | None = None,
    toolbar_global: TagChild | None | MISSING_TYPE = MISSING,
    toolbar_input: TagChild | None = None,
    navbar_options: Any = None,
    sidebar: bool | ChatSidebar = True,
    drawer: bool | ChatDrawer = True,
    window_title: str | None = None,
    lang: str | None = None,
    theme: str | Path | Theme | ThemeProvider | None = None,
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
    assign it to a variable. Compose additional UI through ``pages_navbar``,
    ``toolbar``, ``toolbar_global``, ``sidebar``, and ``drawer``.

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
    pages_navbar
        Secondary navbar items. In addition to
        :func:`~shinychat.chat_nav_panel`, this accepts Shiny's
        :func:`shiny.ui.nav_panel`, :func:`shiny.ui.nav_menu`,
        :func:`shiny.ui.nav_spacer`, and :func:`shiny.ui.nav_control`.
        Standard content panels use the normal page-chat content width and no
        page-specific sidebar or toolbar. Shiny for Python does not currently
        expose ``nav_panel_hidden()`` or ``nav_item()``; use
        :func:`shiny.ui.nav_control` for non-selecting navigation content.
        Sidebar navigation is not yet implemented.
    toolbar
        Optional home-page-scoped HTML child displayed with the navigation
        controls. Use :func:`shiny.ui.toolbar` to group toolbar controls. A
        secondary page's ``chat_nav_panel(toolbar=)`` replaces this scoped
        segment.
    toolbar_global
        Optional persistent HTML child displayed after the page-scoped toolbar
        in the navigation controls. Use :func:`shiny.ui.toolbar` to group
        toolbar controls. When omitted, it contains Shiny's dark/light mode
        toggle; pass ``None`` to opt out. It remains mounted while secondary
        pages are selected and while controls move between desktop and mobile
        layouts.
    toolbar_input
        Optional HTML content displayed directly below the chat input. Use
        :func:`shiny.ui.toolbar` to group toolbar controls. This is independent
        of the navigation ``toolbar``.
    navbar_options
        Optional :func:`shiny.ui.navbar_options` that styles the page title bar.
        ``position`` and ``collapsible`` are unsupported because ``page_chat()``
        owns the full-window layout and responsive app menu.
    sidebar
        Home-page sidebar. ``True`` uses the default conversation-history
        sidebar, ``False`` removes it, and a
        :class:`~shinychat.types.ChatSidebar` supplies custom content and behavior.
        Raw :class:`shiny.ui.Sidebar` objects are not supported.
    drawer
        Whether the chat has an artifact panel. Pass a
        :class:`~shinychat.types.ChatDrawer` to configure its initial content and
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
        Default icon for assistant messages. ``None`` (the default) or
        ``False`` omits it; ``True`` uses the built-in robot icon.
    enable_cancel
        Whether to show the streaming cancel control. When omitted, a chat
        constructed with ``client=`` enables it automatically.
    allow_attachments
        Whether to allow attachments, or a list of accepted MIME types. When
        omitted, a chat constructed with ``client=`` enables them
        automatically.
    footer
        Optional HTML content in a bottom-pinned, full-width chat region.
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
        pages_navbar=[
            chat_nav_panel("About", ui.p("About this app"), sidebar=False),
        ],
        sidebar=chat_sidebar(history=False),
    )
    ```

    See Also
    --------
    :func:`~shinychat.page_chat` : Create the same layout in a Core app.
    :func:`~shinychat.chat_sidebar` : Configure page sidebars.
    :func:`~shinychat.chat_nav_panel` : Configure secondary navbar pages.
    :func:`~shinychat.chat_drawer` : Configure the artifact panel.
    """
    from shiny.express import ui

    chat_root = _create_page_chat_root(
        id=id,
        drawer=drawer,
        messages=messages,
        greeting=greeting,
        placeholder=placeholder,
        width=width,
        icon_assistant=icon_assistant,
        enable_cancel=enable_cancel,
        allow_attachments=allow_attachments,
        toolbar_input=toolbar_input,
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
            pages_navbar=pages_navbar,
            toolbar=toolbar,
            toolbar_global=toolbar_global,
            navbar_options=navbar_options,
            sidebar=sidebar,
            window_title=page_options["window_title"],
            lang=page_options["lang"],
            theme=page_options.get("theme"),
        )

    page_options: dict[str, Any] = {
        "title": title,
        "window_title": window_title,
        "lang": lang,
        "page_fn": page_fn,
    }
    if theme is not None:
        page_options["theme"] = theme
    ui.page_opts(**page_options)
    return chat_root
