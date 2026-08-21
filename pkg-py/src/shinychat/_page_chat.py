from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import isfinite
from typing import (
    TYPE_CHECKING,
    Any,
    Iterable,
    Literal,
    Optional,
    Sequence,
    Union,
    cast,
)

from htmltools import HTML, Tag, TagAttrValue, TagChild, TagList

from ._page_chat_theme import page_chat_theme
from ._utils_types import MISSING, MISSING_TYPE

if TYPE_CHECKING:
    from shiny.ui import Theme
    from shiny.ui.css import CssUnit

    from ._chat_types import ChatGreeting, ChatMessage, ChatMessageDict

__all__ = (
    "ChatArtifact",
    "ChatNavPanel",
    "ChatSidebar",
    "chat_artifact",
    "chat_nav_panel",
    "chat_sidebar",
    "chat_ui_history",
    "page_chat",
)

ChatSidebarOpen = Literal["auto", "open", "closed", "always"]


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
    sidebar: bool | ChatSidebar | None
    toolbar: bool | TagChild | None
    content_width: str


def page_chat(
    title: TagChild,
    *,
    icon: TagChild | None = None,
    id: str = "chat",
    pages: Sequence[ChatNavPanel] | None = None,
    toolbar: TagChild | None | MISSING_TYPE = MISSING,
    toolbar_global: TagChild | None = None,
    navbar_options: Any = None,
    sidebar: bool | ChatSidebar | None = None,
    artifact: bool | ChatArtifact = True,
    window_title: str | None = None,
    lang: str | None = None,
    theme: Theme | None = None,
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
    Create a full-window page containing one persistent chat interface.

    The chat is the home page and remains mounted while users visit secondary
    pages. ``page_chat()`` owns the document shell, responsive navigation,
    sidebars, and full-height chat layout. Use :func:`~shinychat.chat_ui`
    instead when chat should be embedded in another page layout.

    Parameters
    ----------
    title
        Page title displayed in the header. When it is a string and
        ``window_title`` is omitted, it is also used as the document title.
    icon
        Optional HTML child displayed next to ``title``.
    id
        Unique ID shared by the page shell and its chat.
    pages
        Secondary pages created with :func:`~shinychat.chat_nav_panel`.
    toolbar
        Optional home-page-scoped HTML child displayed with the navigation
        controls. When omitted, the toolbar contains Shiny's dark/light mode
        toggle. Pass ``None`` to omit it. A page's
        ``chat_nav_panel(toolbar=)`` can replace this segment.
    toolbar_global
        Optional persistent HTML child displayed after the page-scoped toolbar
        in the navigation controls. It remains mounted while pages are
        selected and while controls move between desktop and mobile layouts.
    navbar_options
        Optional :func:`shiny.ui.navbar_options` that styles the page title bar.
        Its ``bg``, ``theme``, ``underline``, and HTML attributes are supported.
        ``position`` and ``collapsible`` are unsupported because ``page_chat()``
        owns the full-window layout and responsive app menu.
    sidebar
        Home-page sidebar. When omitted or ``True``, the page uses the default
        conversation-history sidebar. ``False`` removes it, and a
        :class:`~shinychat.types.ChatSidebar` supplies custom content and behavior.
        Raw :class:`shiny.ui.Sidebar` objects are not supported.
    artifact
        Whether the chat has an artifact region. Pass a
        :class:`~shinychat.types.ChatArtifact` to configure its initial content and
        behavior.
    window_title
        Optional document title. Use this when ``title`` is an HTML child or
        when the browser title should differ from the displayed title.
    lang
        Optional language for the document's ``<html>`` element.
    theme
        Theme accepted by :func:`shiny.ui.page_fillable`. By default,
        :func:`~shinychat.page_chat_theme` layers page-chat surface tokens over
        Shiny's ``"shiny"`` preset. Pass a :class:`shiny.ui.Theme` directly to
        use another preset or a completely custom theme.
    messages
        Initial chat messages. See :func:`~shinychat.chat_ui`.
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
        A complete fillable Shiny page suitable for use as a Core app's UI.

    Examples
    --------
    ```python
    from shiny import App, ui
    from shinychat import Chat, chat_nav_panel, chat_sidebar, page_chat

    app_ui = page_chat(
        "Assistant",
        pages=[
            chat_nav_panel("About", ui.p("About this app"), sidebar=False),
        ],
        sidebar=chat_sidebar(history=False),
    )


    def server(input, output, session):
        Chat("chat")


    app = App(app_ui, server)
    ```

    See Also
    --------
    :func:`~shinychat.chat_ui` : Embed chat in an existing page layout.
    :func:`~shinychat.chat_sidebar` : Configure page sidebars.
    :func:`~shinychat.chat_nav_panel` : Configure secondary pages.
    :func:`~shinychat.chat_artifact` : Configure the artifact region.
    :func:`~shinychat.express.page_chat` : Create the same layout in Express.
    """
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
    return _render_page_chat(
        chat_root,
        title,
        icon,
        id=id,
        pages=pages,
        toolbar=toolbar,
        toolbar_global=toolbar_global,
        navbar_options=navbar_options,
        sidebar=sidebar,
        window_title=window_title,
        lang=lang,
        theme=theme,
    )


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
        # String validation is delegated to Shiny and browser CSS semantics.
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
    """
    Configure a sidebar for :func:`~shinychat.page_chat`.

    This creates a shinychat sidebar configuration, not a
    :class:`shiny.ui.Sidebar`. Raw Shiny sidebar objects cannot be passed to
    :func:`~shinychat.page_chat` or :func:`~shinychat.chat_nav_panel`.

    Parameters
    ----------
    *content
        HTML children to display in the sidebar.
    history
        Whether to include the conversation-history view for the page's chat.
    width
        Initial sidebar width. A positive number is interpreted as pixels; a
        string may use any valid CSS width.
    open
        Initial desktop state: ``"open"``, ``"closed"``, ``"always"``, or
        ``"auto"``. ``"always"`` prevents the sidebar from being collapsed.
        ``"auto"`` lets the page choose an initial state based on the sidebar
        role and restored history. ``True`` and ``False`` are aliases for
        ``"open"`` and ``"closed"``.
    resizable
        Whether the sidebar can be resized on desktop.

    Returns
    -------
    ChatSidebar
        A sidebar configuration for ``page_chat(sidebar=)`` or
        ``chat_nav_panel(sidebar=)``.

    Examples
    --------
    ```python
    from shiny import ui
    from shinychat import chat_sidebar

    sidebar = chat_sidebar(
        ui.p("Project controls"),
        history=True,
        width=320,
        open="auto",
    )
    ```

    See Also
    --------
    :func:`~shinychat.page_chat` : Create a full-window chat page.
    :func:`~shinychat.chat_nav_panel` : Add a page-specific sidebar.
    """
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
    open: bool = True,
    resizable: bool = True,
) -> ChatArtifact:
    """
    Configure content displayed adjacent to a chat interface.

    An artifact can show a preview, generated report, or detail view beside the
    conversation. Pass this configuration to ``chat_ui(artifact=)`` or
    ``page_chat(artifact=)`` for its initial content and layout, then update it
    through the chat artifact controller.

    Parameters
    ----------
    *content
        Initial HTML children for the artifact region.
    title
        Optional accessible and visible title for the artifact.
    width
        Initial artifact width. A positive number is interpreted as pixels; a
        string may use any valid CSS width.
    open
        Whether the artifact is initially visible.
    resizable
        Whether the artifact can be resized on desktop.

    Returns
    -------
    ChatArtifact
        An artifact configuration for ``page_chat(artifact=)`` or
        ``chat_ui(artifact=)``.

    Examples
    --------
    ```python
    from shiny import ui
    from shinychat import chat_artifact

    artifact = chat_artifact(
        ui.p("No result selected."),
        title="Result",
        width=480,
    )
    ```

    See Also
    --------
    :func:`~shinychat.page_chat` : Create a page with an artifact region.
    :func:`~shinychat.chat_ui` : Create an embedded chat with an artifact region.
    :class:`~shinychat.ChatArtifactController` : Update the artifact from the server.
    """
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
    sidebar: bool | ChatSidebar | None = None,
    toolbar: bool | TagChild | None = None,
    content_width: "CssUnit" = "min(680px, 100%)",
) -> ChatNavPanel:
    """
    Configure a secondary navigation page for :func:`~shinychat.page_chat`.

    The chat remains mounted on the home page while users navigate to this
    panel, preserving its current conversation and UI state.

    Parameters
    ----------
    title
        Non-empty label shown in the page navigation.
    *content
        HTML children to display on the page.
    value
        Optional unique navigation value. Defaults to ``title``. The value
        ``"home"`` is reserved for the chat page.
    icon
        Optional HTML child displayed with the navigation label.
    sidebar
        Sidebar for this page. When omitted or ``False``, this page has no
        page-specific sidebar. ``True`` uses the default conversation-history
        sidebar, and a :class:`~shinychat.types.ChatSidebar` supplies a page-specific
        sidebar. Raw :class:`shiny.ui.Sidebar` objects are not supported.
    toolbar
        Toolbar for this page. ``None`` (the default) shows no page-scoped
        toolbar. An HTML child supplies a page-specific toolbar. ``True`` and
        ``False`` are legacy aliases for reusing the home
        :func:`~shinychat.page_chat` toolbar and showing no page-scoped
        toolbar, respectively.
    content_width
        Maximum width for the panel content. Content is centered and receives
        responsive inline padding. ``"100%"``, ``"100vw"``, and ``"100dvw"``
        create a full-bleed panel without component-provided inline padding.

    Returns
    -------
    ChatNavPanel
        A navigation-panel configuration for ``page_chat(pages=)``.

    Examples
    --------
    ```python
    from shiny import ui
    from shinychat import chat_nav_panel, chat_sidebar

    settings = chat_nav_panel(
        "Settings",
        ui.input_switch("compact", "Compact answers"),
        value="settings",
        sidebar=chat_sidebar(ui.p("Display options")),
    )
    ```

    See Also
    --------
    :func:`~shinychat.page_chat` : Add navigation panels to a chat page.
    :func:`~shinychat.chat_sidebar` : Configure a panel's sidebar.
    """
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
    if sidebar is not None and not isinstance(sidebar, (bool, ChatSidebar)):
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
        toolbar=toolbar,
        content_width=_validate_css_width(content_width, "content_width"),
    )


def chat_ui_history(id: str, **attrs: TagAttrValue) -> Tag:
    """
    Create a conversation-history view bound to a chat.

    Use this helper for a custom placement of chat history. A
    :func:`~shinychat.page_chat` sidebar can include the same view more
    directly with ``chat_sidebar(history=True)``.

    Parameters
    ----------
    id
        ID of the target chat. The ID is resolved in the current Shiny module
        namespace.
    **attrs
        Additional HTML attributes for the history element. The ``for``
        attribute is owned by this helper and cannot be overridden.

    Returns
    -------
    Tag
        A ``<shiny-chat-history>`` element connected to ``id``.

    Examples
    --------
    ```python
    from shiny import ui
    from shinychat import chat_ui, chat_ui_history

    ui.div(
        chat_ui("chat", show_history=False),
        chat_ui_history("chat", class_="conversation-list"),
    )
    ```

    See Also
    --------
    :func:`~shinychat.chat_sidebar` : Include history in a page sidebar.
    :func:`~shinychat.chat_ui` : Create the target chat UI.
    """
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


@dataclass(frozen=True)
class _NormalizedPage:
    panel: ChatNavPanel
    value: str
    sidebar_key: str | None
    toolbar_key: str | None


@dataclass(frozen=True)
class _NormalizedSidebar:
    key: str
    config: ChatSidebar


def _normalize_sidebar_config(sidebar: ChatSidebar) -> ChatSidebar:
    if not isinstance(sidebar.content, tuple):
        raise TypeError(
            "`ChatSidebar.content` must be a tuple of HTML children."
        )
    return chat_sidebar(
        *sidebar.content,
        history=sidebar.history,
        width=sidebar.width,
        open=sidebar.open,
        resizable=sidebar.resizable,
    )


def _normalize_page_config(
    pages: Sequence[ChatNavPanel] | None,
    sidebar: bool | ChatSidebar | None,
) -> tuple[
    tuple[_NormalizedPage, ...],
    tuple[_NormalizedSidebar, ...],
    str | None,
    ChatSidebar | None,
]:
    if sidebar is not None and not isinstance(sidebar, (bool, ChatSidebar)):
        raise TypeError(
            "`sidebar` must be False, True, or a shinychat `ChatSidebar`; "
            "raw Shiny Sidebar objects are not supported."
        )

    default_sidebar: ChatSidebar | None = None
    home_sidebar: ChatSidebar | None
    sidebars: list[_NormalizedSidebar] = []
    if sidebar is None or sidebar is True:
        default_sidebar = chat_sidebar(history=True)
        home_sidebar = default_sidebar
        home_sidebar_key = "default"
        sidebars.append(_NormalizedSidebar("default", default_sidebar))
    elif isinstance(sidebar, ChatSidebar):
        home_sidebar = _normalize_sidebar_config(sidebar)
        home_sidebar_key = "home"
        sidebars.append(_NormalizedSidebar("home", home_sidebar))
    else:
        home_sidebar = None
        home_sidebar_key = None

    if pages is None:
        page_items: Sequence[ChatNavPanel] = ()
    elif isinstance(pages, (str, bytes)) or not isinstance(pages, Sequence):
        raise TypeError("`pages` must be a sequence of `ChatNavPanel` objects.")
    else:
        page_items = pages

    normalized_pages: list[_NormalizedPage] = []
    values = {"home"}
    for index, panel in enumerate(page_items):
        if not isinstance(panel, ChatNavPanel):
            raise TypeError(
                "`pages` must contain only `ChatNavPanel` objects, "
                f"not {type(panel).__name__}."
            )
        if not isinstance(panel.title, str) or not panel.title.strip():
            raise ValueError(
                "Navigation page titles must be non-empty strings."
            )
        if panel.value is not None and not isinstance(panel.value, str):
            raise TypeError("Navigation page values must be strings or None.")
        if panel.sidebar is not None and not isinstance(
            panel.sidebar, (bool, ChatSidebar)
        ):
            raise TypeError(
                "Navigation page sidebars must be False, True, or a "
                "shinychat `ChatSidebar`."
            )
        value = panel.title if panel.value is None else panel.value
        if not value.strip():
            raise ValueError("Navigation page values must not be empty.")
        if value == "home":
            raise ValueError('Navigation page value "home" is reserved.')
        if value in values:
            raise ValueError(f"Duplicate navigation page value {value!r}.")
        values.add(value)

        if panel.sidebar is True:
            sidebar_key = "default"
            if default_sidebar is None:
                default_sidebar = chat_sidebar(history=True)
                sidebars.append(_NormalizedSidebar("default", default_sidebar))
        elif panel.sidebar is None or panel.sidebar is False:
            sidebar_key = None
        else:
            sidebar_key = f"page-{index + 1}"
            sidebars.append(
                _NormalizedSidebar(
                    sidebar_key,
                    _normalize_sidebar_config(panel.sidebar),
                )
            )

        toolbar_key = (
            "home"
            if panel.toolbar is True
            else f"page-{index + 1}"
            if panel.toolbar is not False and panel.toolbar is not None
            else None
        )
        normalized_pages.append(
            _NormalizedPage(
                panel=panel,
                value=value,
                sidebar_key=sidebar_key,
                toolbar_key=toolbar_key,
            )
        )

    sidebar_order = {"default": 0, "home": 1}
    sidebars.sort(key=lambda item: sidebar_order.get(item.key, 2))

    return (
        tuple(normalized_pages),
        tuple(sidebars),
        home_sidebar_key,
        home_sidebar,
    )


def _render_sidebar_panel(
    sidebar: _NormalizedSidebar,
    chat_id: str,
    home_sidebar_key: str | None,
) -> Tag:
    config = sidebar.config
    return Tag(
        "div",
        chat_ui_history(chat_id) if config.history else None,
        *config.content,
        class_="shiny-chat-page-sidebar-panel",
        data_sidebar_for=sidebar.key,
        data_sidebar_open=config.open,
        data_sidebar_width=config.width,
        data_sidebar_resizable="true" if config.resizable else "false",
        hidden=True if sidebar.key != home_sidebar_key else None,
    )


def _render_page_control(
    page: _NormalizedPage,
    resolved_id: str,
    index: int,
) -> Tag:
    control_id = f"{resolved_id}-nav-{index}"
    panel_id = f"{resolved_id}-panel-{index}"
    return Tag(
        "button",
        (
            Tag(
                "span",
                page.panel.icon,
                class_="shiny-chat-page-nav-icon",
            )
            if page.panel.icon is not None
            else None
        ),
        Tag(
            "span",
            page.panel.title,
            class_="shiny-chat-page-nav-title",
        ),
        type="button",
        id=control_id,
        class_="shiny-chat-page-nav-link",
        aria_controls=panel_id,
        data_page_target=page.value,
    )


def _render_toolbar_source(key: str, content: TagChild | None) -> Tag:
    return Tag(
        "div",
        Tag(
            "div",
            content,
            class_="shiny-chat-page-toolbar-content",
        ),
        class_="shiny-chat-page-toolbar-source",
        data_page_toolbar_source=key,
    )


def _normalize_page_chat_navbar_options(options: Any) -> Any:
    from shiny import ui

    if options is None:
        return ui.navbar_options()

    options_type = type(ui.navbar_options())
    if not isinstance(options, options_type):
        raise TypeError(
            "`navbar_options` must be created by `shiny.ui.navbar_options()`."
        )

    supplied = [
        name
        for name in ("position", "collapsible")
        if not options._is_default.get(name, False)
    ]
    if supplied:
        names = ", ".join(f"`{name}`" for name in supplied)
        raise ValueError(
            f"`navbar_options` cannot set {names} in `page_chat()`; "
            "the page owns the full-window layout and responsive app menu."
        )

    return options


def _apply_page_chat_navbar_options(header: Tag, options: Any) -> None:
    header.attrs.update(options.attrs)
    if "class" in options.attrs or "class_" in options.attrs:
        header.add_class("shiny-chat-page-header", prepend=True)
    header.attrs["data-bs-theme"] = options.theme
    header.attrs["data-shiny-chat-page-nav-style"] = (
        "underline" if options.underline else "pill"
    )
    if options.bg is not None:
        header.add_style(f"background-color:{options.bg};")


def _create_page_chat_root(
    *,
    id: str = "chat",
    artifact: bool | ChatArtifact = True,
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
    from ._chat import chat_ui

    if not isinstance(id, str):
        raise TypeError(f"`id` must be a string, not {type(id).__name__}.")
    if not id.strip():
        raise ValueError("`id` must not be an empty string.")

    owned_args = {"height", "fill", "show_history"}.intersection(kwargs)
    if owned_args:
        names = ", ".join(f"`{name}`" for name in sorted(owned_args))
        raise TypeError(f"`page_chat()` owns {names}; remove from `kwargs`.")

    return chat_ui(
        id,
        messages=messages,
        greeting=greeting,
        placeholder=placeholder,
        width=width,
        height="100%",
        fill=True,
        icon_assistant=icon_assistant,
        enable_cancel=enable_cancel,
        allow_attachments=allow_attachments,
        footer=footer,
        artifact=artifact,
        show_history=True,
        **kwargs,
    )


def _render_page_chat(
    chat_root: Tag,
    title: TagChild,
    icon: TagChild | None = None,
    *,
    id: str = "chat",
    pages: Sequence[ChatNavPanel] | None = None,
    toolbar: TagChild | None | MISSING_TYPE = MISSING,
    toolbar_global: TagChild | None = None,
    navbar_options: Any = None,
    sidebar: bool | ChatSidebar | None = None,
    window_title: str | None = None,
    lang: str | None = None,
    theme: Theme | None = None,
) -> Tag:
    from shiny import ui
    from shiny.module import resolve_id

    if not isinstance(id, str):
        raise TypeError(f"`id` must be a string, not {type(id).__name__}.")
    if not id.strip():
        raise ValueError("`id` must not be an empty string.")
    if title is None:
        raise TypeError("`title` must not be None.")
    if isinstance(title, str) and not title.strip():
        raise ValueError("`title` must not be an empty string.")
    if window_title is not None and not isinstance(window_title, str):
        raise TypeError(
            "`window_title` must be a string or None, "
            f"not {type(window_title).__name__}."
        )
    if lang is not None and not isinstance(lang, str):
        raise TypeError(
            f"`lang` must be a string or None, not {type(lang).__name__}."
        )
    if isinstance(lang, str) and not lang.strip():
        raise ValueError("`lang` must not be an empty string.")
    navbar_options = _normalize_page_chat_navbar_options(navbar_options)
    if theme is None:
        theme = page_chat_theme()
    if isinstance(toolbar, MISSING_TYPE):
        toolbar_content: TagChild | None = ui.input_dark_mode()
    else:
        toolbar_content = toolbar

    (
        normalized_pages,
        normalized_sidebars,
        home_sidebar_key,
        home_sidebar,
    ) = _normalize_page_config(pages, sidebar)
    resolved_id = resolve_id(id)
    sidebar_id = f"{resolved_id}-sidebar"

    identity_content = (
        Tag(
            "span",
            icon,
            class_="shiny-chat-page-identity-icon",
        )
        if icon is not None
        else None,
        Tag(
            "span",
            title,
            class_="shiny-chat-page-identity-title",
        ),
    )
    if normalized_pages:
        identity = Tag(
            "button",
            *identity_content,
            type="button",
            class_="shiny-chat-page-identity",
            data_page_home="",
            aria_label="Return to chat",
        )
    else:
        identity = Tag(
            "div",
            *identity_content,
            class_="shiny-chat-page-identity",
        )
    controls = Tag(
        "div",
        Tag(
            "nav",
            *(
                _render_page_control(page, resolved_id, index)
                for index, page in enumerate(normalized_pages, start=1)
            ),
            class_="shiny-chat-page-nav",
            aria_label="Pages",
        ),
        Tag(
            "div",
            Tag("div", class_="shiny-chat-page-toolbar-scoped"),
            Tag(
                "div",
                toolbar_global,
                class_="shiny-chat-page-toolbar-global",
            ),
            class_="shiny-chat-page-toolbar",
        ),
        class_="shiny-chat-page-controls",
    )
    toolbar_sources = Tag(
        "div",
        _render_toolbar_source("home", toolbar_content),
        *(
            _render_toolbar_source(
                page.toolbar_key,
                cast(TagChild, page.panel.toolbar),
            )
            for page in normalized_pages
            if page.toolbar_key is not None and page.toolbar_key != "home"
        ),
        class_="shiny-chat-page-toolbar-sources",
        hidden=True,
    )

    header = Tag(
        "header",
        Tag(
            "button",
            Tag(
                "svg",
                Tag(
                    "path",
                    d=(
                        "M2.5 12a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5m0-4"
                        "a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5m0-4a.5.5 "
                        "0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5"
                    ),
                ),
                class_="shiny-chat-page-sidebar-icon bi bi-list",
                xmlns="http://www.w3.org/2000/svg",
                viewBox="0 0 16 16",
                aria_hidden="true",
                focusable="false",
            ),
            type="button",
            class_="shiny-chat-page-sidebar-toggle",
            aria_controls=sidebar_id,
            aria_expanded=(
                "true"
                if home_sidebar is not None
                and home_sidebar.open in ("open", "always")
                else "false"
            ),
            aria_label="Toggle app menu",
        ),
        identity,
        Tag(
            "div",
            controls,
            class_=(
                "shiny-chat-page-controls-mount "
                "shiny-chat-page-controls-mount-desktop"
            ),
        ),
        class_="shiny-chat-page-header",
    )
    body = Tag(
        "div",
        Tag(
            "aside",
            Tag(
                "div",
                class_=(
                    "shiny-chat-page-controls-mount "
                    "shiny-chat-page-controls-mount-mobile"
                ),
            ),
            *(
                _render_sidebar_panel(sidebar, id, home_sidebar_key)
                for sidebar in normalized_sidebars
            ),
            id=sidebar_id,
            class_="shiny-chat-page-sidebar",
            aria_label="App menu",
            data_sidebar_key=home_sidebar_key,
            data_sidebar_open=(
                home_sidebar.open if home_sidebar is not None else None
            ),
            data_sidebar_width=(
                home_sidebar.width if home_sidebar is not None else None
            ),
            data_sidebar_resizable=(
                "true"
                if home_sidebar is not None and home_sidebar.resizable
                else "false"
                if home_sidebar is not None
                else None
            ),
        ),
        Tag(
            "main",
            Tag(
                "section",
                chat_root,
                class_="shiny-chat-page-panel shiny-chat-page-home",
                data_page_value="home",
                data_sidebar_key=home_sidebar_key,
                data_page_toolbar_source="home",
            ),
            *(
                Tag(
                    "section",
                    Tag(
                        "div",
                        *page.panel.content,
                        class_="shiny-chat-page-panel-content",
                        style=(
                            "--shiny-chat-page-content-width:"
                            f"{page.panel.content_width}"
                        ),
                        data_content_full_bleed=(
                            "true"
                            if page.panel.content_width
                            in ("100%", "100vw", "100dvw")
                            else None
                        ),
                    ),
                    id=f"{resolved_id}-panel-{index}",
                    class_="shiny-chat-page-panel",
                    aria_labelledby=f"{resolved_id}-nav-{index}",
                    data_page_value=page.value,
                    data_page_title=page.panel.title,
                    data_sidebar_key=page.sidebar_key,
                    data_page_toolbar_source=page.toolbar_key,
                    hidden=True,
                )
                for index, page in enumerate(normalized_pages, start=1)
            ),
            class_="shiny-chat-page-main",
        ),
        class_="shiny-chat-page-body",
    )
    shell = Tag(
        "shiny-chat-page",
        header,
        body,
        toolbar_sources,
        data_chat_id=resolved_id,
        data_active_page="home",
    )
    _apply_page_chat_navbar_options(header, navbar_options)

    document_title = (
        title
        if window_title is None and isinstance(title, str)
        else window_title
    )
    return ui.page_fillable(
        shell,
        fillable_mobile=True,
        padding=0,
        gap=0,
        title=document_title,
        theme=theme,
        lang=lang,
    )
