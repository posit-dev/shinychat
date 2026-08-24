from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import isfinite
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Iterable,
    Literal,
    Optional,
    Sequence,
    TypeGuard,
    Union,
    cast,
)

from htmltools import HTML, MetadataNode, Tag, TagAttrValue, TagChild, TagList

from ._page_chat_theme import page_chat_theme
from ._utils_types import MISSING, MISSING_TYPE

if TYPE_CHECKING:
    from shiny.types import NavSetArg
    from shiny.ui import Theme
    from shiny.ui._html_deps_external import ThemeProvider
    from shiny.ui._navs import NavMenu, NavPanel
    from shiny.ui.css import CssUnit

    from ._chat_types import ChatGreeting, ChatMessage, ChatMessageDict

__all__ = (
    "ChatDrawer",
    "ChatNavPanel",
    "ChatSidebar",
    "chat_drawer",
    "chat_nav_panel",
    "chat_sidebar",
    "chat_ui_history",
    "page_chat",
)

HOME_PAGE_VALUE = "__home__"

ChatSidebarOpen = Literal["auto", "open", "closed", "always"]


@dataclass(frozen=True)
class ChatSidebar:
    content: tuple[TagChild, ...]
    history: bool | MISSING_TYPE
    width: str
    open: ChatSidebarOpen
    resizable: bool


@dataclass(frozen=True)
class ChatDrawer:
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
    toolbar: TagChild | None
    content_width: str


def page_chat(
    title: TagChild,
    *,
    id: str = "chat",
    icon: TagChild | None = None,
    pages_navbar: Sequence[ChatNavPanel | NavSetArg | MetadataNode]
    | None = None,
    toolbar: TagChild | None = None,
    toolbar_global: TagChild | None | MISSING_TYPE = MISSING,
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
        Unique ID shared by the page shell and its chat. The currently
        selected page is readable server-side as ``input["<id>_page"]()``
        and settable via :func:`shiny.ui.update_navset`. The reserved value
        ``"__home__"`` represents the main chat page.
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
    navbar_options
        Optional :func:`shiny.ui.navbar_options` that styles the page title bar.
        Its ``bg``, ``theme``, ``underline``, and HTML attributes are supported.
        ``position`` and ``collapsible`` are unsupported because ``page_chat()``
        owns the full-window layout and responsive app menu.
    sidebar
        Home-page sidebar. ``True`` uses the default conversation-history
        sidebar, ``False`` removes it, and a
        :class:`~shinychat.types.ChatSidebar` supplies custom content and behavior.
        A sidebar created without ``history=`` defaults to ``True`` here.
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
        pages_navbar=[
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
    :func:`~shinychat.chat_nav_panel` : Configure secondary navbar pages.
    :func:`~shinychat.chat_drawer` : Configure the artifact panel.
    :func:`~shinychat.express.page_chat` : Create the same layout in Express.
    """
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
        footer=footer,
        **kwargs,
    )
    return _render_page_chat(
        chat_root,
        title,
        icon,
        id=id,
        pages_navbar=pages_navbar,
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
    history: bool | MISSING_TYPE = MISSING,
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
        When omitted, ``page_chat()`` defaults to ``True`` and
        ``chat_nav_panel()`` defaults to ``False``.
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
        history=(
            history
            if isinstance(history, MISSING_TYPE)
            else _validate_bool(history, "history")
        ),
        width=_validate_css_width(width, "width"),
        open=open_value,
        resizable=_validate_bool(resizable, "resizable"),
    )


def chat_drawer(
    *content: TagChild,
    title: str | None = None,
    width: "CssUnit" = 400,
    open: bool = True,
    resizable: bool = True,
) -> ChatDrawer:
    """
    Configure content displayed adjacent to a chat interface.

    An artifact panel can show a preview, generated report, or detail view beside
    the conversation. Pass this configuration to ``chat_ui(drawer=)`` or
    ``page_chat(drawer=)`` for its initial content and layout, then update it
    through the chat artifact controller.

    Parameters
    ----------
    *content
        Initial HTML children for the artifact panel.
    title
        Optional accessible and visible title for the artifact panel.
    width
        Initial artifact-panel width. A positive number is interpreted as pixels; a
        string may use any valid CSS width.
    open
        Whether the artifact panel is initially visible.
    resizable
        Whether the artifact panel can be resized on desktop.

    Returns
    -------
    ChatDrawer
        An artifact-panel configuration for ``page_chat(drawer=)`` or
        ``chat_ui(drawer=)``.

    Examples
    --------
    ```python
    from shiny import ui
    from shinychat import chat_drawer

    artifact = chat_drawer(
        ui.p("No result selected."),
        title="Result",
        width=480,
    )
    ```

    See Also
    --------
    :func:`~shinychat.page_chat` : Create a page with an artifact panel.
    :func:`~shinychat.chat_ui` : Create an embedded chat with an artifact panel.
    :class:`~shinychat.types.ChatDrawerController` : Update the panel from the server.
    """
    _validate_content(content, "chat_drawer()")
    if title is not None and not isinstance(title, str):
        raise TypeError(
            f"`title` must be a string or None, not {type(title).__name__}."
        )
    return ChatDrawer(
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
    toolbar: TagChild | None = None,
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
        ``"__home__"`` is reserved for the main chat page.
    icon
        Optional HTML child displayed with the navigation label.
    sidebar
        Sidebar for this page. ``False`` shows no page-specific sidebar,
        ``True`` uses the default conversation-history sidebar, and a
        :class:`~shinychat.types.ChatSidebar` supplies a page-specific sidebar.
        A sidebar created without ``history=`` defaults to ``False`` here.
        Raw :class:`shiny.ui.Sidebar` objects are not supported.
    toolbar
        Toolbar for this page. ``None`` (the default) shows no page-scoped
        toolbar. An HTML child, typically :func:`shiny.ui.toolbar`, supplies a
        page-specific toolbar.
    content_width
        Maximum width for the panel content. Content is centered and receives
        responsive inline padding. ``"100%"``, ``"100vw"``, and ``"100dvw"``
        create a full-bleed panel without component-provided inline padding.

    Returns
    -------
    ChatNavPanel
        A navigation-panel configuration for ``page_chat(pages_navbar=)``.

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
    if not isinstance(sidebar, (bool, ChatSidebar)):
        raise TypeError(
            "`sidebar` must be False, True, or a shinychat `ChatSidebar`; "
            "raw Shiny Sidebar objects are not supported."
        )
    if isinstance(toolbar, bool):
        raise TypeError(
            "`toolbar` must be an HTML child or None, "
            f"not {type(toolbar).__name__}."
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


def render_chat_drawer(drawer: ChatDrawer) -> Tag:
    return Tag(
        "shiny-chat-drawer",
        *drawer.content,
        title=drawer.title,
        width=drawer.width,
        open=drawer.open,
        resizable="false" if not drawer.resizable else None,
    )


@dataclass(frozen=True)
class _NormalizedPage:
    panel: ChatNavPanel
    value: str
    sidebar_key: str | None
    toolbar_key: str | None
    has_nav_control: bool


@dataclass(frozen=True)
class _NormalizedSidebar:
    key: str
    config: ChatSidebar


@dataclass(frozen=True)
class _PageNavItem:
    kind: Literal["page", "menu", "control", "spacer", "divider", "header"]
    page_index: int | None = None
    label: tuple[TagChild, ...] = ()
    children: tuple["_PageNavItem", ...] = ()


def _normalize_sidebar_config(
    sidebar: ChatSidebar,
    *,
    default_history: bool,
) -> ChatSidebar:
    if not isinstance(sidebar.content, tuple):
        raise TypeError(
            "`ChatSidebar.content` must be a tuple of HTML children."
        )
    return chat_sidebar(
        *sidebar.content,
        history=(
            default_history
            if isinstance(sidebar.history, MISSING_TYPE)
            else sidebar.history
        ),
        width=sidebar.width,
        open=sidebar.open,
        resizable=sidebar.resizable,
    )


def is_shiny_nav_panel(value: object) -> TypeGuard[NavPanel]:
    from shiny.ui._navs import NavPanel

    return isinstance(value, NavPanel)


def is_shiny_nav_menu(value: object) -> TypeGuard[NavMenu]:
    from shiny.ui._navs import NavMenu

    return isinstance(value, NavMenu)


def _nav_panel_label(panel: NavPanel) -> tuple[TagChild, ...]:
    nav = panel.nav
    if not isinstance(nav, Tag) or not nav.children:
        raise TypeError(
            "Shiny navigation panels must contain a navigation link."
        )
    link = nav.children[0]
    if not isinstance(link, Tag):
        raise TypeError(
            "Shiny navigation panels must contain a navigation link."
        )
    return tuple(link.children)


def _nav_panel_title(label: tuple[TagChild, ...], value: str) -> str:
    for child in reversed(label):
        if isinstance(child, str) and child.strip():
            return child
    return value


def _normalize_standard_nav_items(
    pages_navbar: Sequence[ChatNavPanel | NavSetArg | MetadataNode] | None,
) -> tuple[tuple[ChatNavPanel, ...], tuple[_PageNavItem, ...]]:
    if pages_navbar is None:
        return (), ()
    if isinstance(pages_navbar, (str, bytes)) or not isinstance(
        pages_navbar, Sequence
    ):
        raise TypeError(
            "`pages_navbar` must be a sequence of `ChatNavPanel` or supported "
            "Shiny navigation items."
        )

    pages: list[ChatNavPanel] = []

    def normalize_item(
        item: ChatNavPanel | NavSetArg | MetadataNode | str,
        location: str,
        in_menu: bool,
    ) -> _PageNavItem:
        if isinstance(item, str):
            if not in_menu:
                raise TypeError(
                    f"`pages_navbar` item {location} is a string; strings are "
                    "only supported as nav-menu headers or dividers."
                )
            if len(item) >= 2 and set(item) == {"-"}:
                return _PageNavItem("divider")
            return _PageNavItem("header", label=(item,))

        if isinstance(item, ChatNavPanel):
            pages.append(item)
            return _PageNavItem("page", page_index=len(pages) - 1)

        if is_shiny_nav_menu(item):
            controls = item.nav_controls
            if not isinstance(controls, list):
                raise TypeError(f"`pages_navbar` menu {location} is malformed.")
            title = item.title
            label = tuple(title) if isinstance(title, TagList) else (title,)
            return _PageNavItem(
                "menu",
                label=label,
                children=tuple(
                    normalize_item(child, f"{location}.{index}", True)
                    for index, child in enumerate(controls, start=1)
                ),
            )

        if is_shiny_nav_panel(item):
            content = item.content
            nav = item.nav
            if not isinstance(nav, Tag):
                raise TypeError(f"`pages_navbar` item {location} is malformed.")
            if content is None:
                if nav.has_class("bslib-nav-spacer"):
                    return _PageNavItem("spacer")
                if nav.has_class("dropdown-divider"):
                    return _PageNavItem("divider")
                if nav.has_class("dropdown-header"):
                    return _PageNavItem("header", label=tuple(nav.children))
                return _PageNavItem("control", label=tuple(nav.children))
            if not isinstance(content, Tag):
                raise TypeError(f"`pages_navbar` item {location} is malformed.")
            value = item.get_value()
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"`pages_navbar` item {location} must have a non-empty "
                    "navigation value."
                )
            label = _nav_panel_label(item)
            pages.append(
                ChatNavPanel(
                    title=_nav_panel_title(label, value),
                    content=tuple(content.children),
                    value=value,
                    icon=None,
                    sidebar=False,
                    toolbar=None,
                    content_width="min(680px, 100%)",
                )
            )
            return _PageNavItem(
                "page",
                page_index=len(pages) - 1,
                label=label,
            )

        raise TypeError(
            f"`pages_navbar` item {location} must be a `ChatNavPanel` or a "
            "supported Shiny navigation item."
        )

    nav_items = tuple(
        normalize_item(item, str(index), False)
        for index, item in enumerate(pages_navbar, start=1)
    )
    return tuple(pages), nav_items


def _nav_control_page_indexes(items: Sequence[_PageNavItem]) -> set[int]:
    indexes: set[int] = set()
    for item in items:
        if item.kind == "page" and item.page_index is not None:
            indexes.add(item.page_index)
        indexes.update(_nav_control_page_indexes(item.children))
    return indexes


def _normalize_page_config(
    pages_navbar: Sequence[ChatNavPanel | NavSetArg | MetadataNode] | None,
    sidebar: bool | ChatSidebar,
) -> tuple[
    tuple[_NormalizedPage, ...],
    tuple[_NormalizedSidebar, ...],
    str | None,
    ChatSidebar | None,
    tuple[_PageNavItem, ...],
]:
    if not isinstance(sidebar, (bool, ChatSidebar)):
        raise TypeError(
            "`sidebar` must be False, True, or a shinychat `ChatSidebar`; "
            "raw Shiny Sidebar objects are not supported."
        )

    default_sidebar: ChatSidebar | None = None
    home_sidebar: ChatSidebar | None
    sidebars: list[_NormalizedSidebar] = []
    if sidebar is True:
        default_sidebar = chat_sidebar(history=True)
        home_sidebar = default_sidebar
        home_sidebar_key = "default"
        sidebars.append(_NormalizedSidebar("default", default_sidebar))
    elif isinstance(sidebar, ChatSidebar):
        home_sidebar = _normalize_sidebar_config(
            sidebar,
            default_history=True,
        )
        home_sidebar_key = "home"
        sidebars.append(_NormalizedSidebar("home", home_sidebar))
    else:
        home_sidebar = None
        home_sidebar_key = None

    page_items, nav_items = _normalize_standard_nav_items(pages_navbar)
    nav_control_indexes = _nav_control_page_indexes(nav_items)

    normalized_pages: list[_NormalizedPage] = []
    values = {HOME_PAGE_VALUE}
    for index, panel in enumerate(page_items):
        if not isinstance(panel, ChatNavPanel):
            raise TypeError(
                "`pages_navbar` must contain only `ChatNavPanel` objects "
                "or supported Shiny navigation items, "
                f"not {type(panel).__name__}."
            )
        if not isinstance(panel.title, str) or not panel.title.strip():
            raise ValueError(
                "Navigation page titles must be non-empty strings."
            )
        if panel.value is not None and not isinstance(panel.value, str):
            raise TypeError("Navigation page values must be strings or None.")
        if not isinstance(panel.sidebar, (bool, ChatSidebar)):
            raise TypeError(
                "Navigation page sidebars must be False, True, or a "
                "shinychat `ChatSidebar`."
            )
        if isinstance(panel.toolbar, bool):
            raise TypeError(
                "`toolbar` must be an HTML child or None, "
                f"not {type(panel.toolbar).__name__}."
            )
        value = panel.title if panel.value is None else panel.value
        if not value.strip():
            raise ValueError("Navigation page values must not be empty.")
        if value == HOME_PAGE_VALUE:
            raise ValueError(
                f'Navigation page value "{HOME_PAGE_VALUE}" is reserved.'
            )
        if value in values:
            raise ValueError(f"Duplicate navigation page value {value!r}.")
        values.add(value)

        if panel.sidebar is True:
            sidebar_key = "default"
            if default_sidebar is None:
                default_sidebar = chat_sidebar(history=True)
                sidebars.append(_NormalizedSidebar("default", default_sidebar))
        elif panel.sidebar is False:
            sidebar_key = None
        else:
            sidebar_key = f"page-{index + 1}"
            sidebars.append(
                _NormalizedSidebar(
                    sidebar_key,
                    _normalize_sidebar_config(
                        panel.sidebar,
                        default_history=False,
                    ),
                )
            )

        toolbar_key = f"page-{index + 1}" if panel.toolbar is not None else None
        normalized_pages.append(
            _NormalizedPage(
                panel=panel,
                value=value,
                sidebar_key=sidebar_key,
                toolbar_key=toolbar_key,
                has_nav_control=index in nav_control_indexes,
            )
        )

    sidebar_order = {"default": 0, "home": 1}
    sidebars.sort(key=lambda item: sidebar_order.get(item.key, 2))

    return (
        tuple(normalized_pages),
        tuple(sidebars),
        home_sidebar_key,
        home_sidebar,
        nav_items,
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
    label: tuple[TagChild, ...] | None = None,
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
            *(label if label else (page.panel.title,)),
            class_="shiny-chat-page-nav-title",
        ),
        type="button",
        id=control_id,
        class_="shiny-chat-page-nav-link",
        aria_controls=panel_id,
        data_page_target=page.value,
    )


def _render_page_nav_item(
    item: _PageNavItem,
    pages: tuple[_NormalizedPage, ...],
    resolved_id: str,
) -> Tag:
    if item.kind == "page":
        assert item.page_index is not None
        return _render_page_control(
            pages[item.page_index],
            resolved_id,
            item.page_index + 1,
            item.label,
        )
    if item.kind == "control":
        return Tag(
            "span",
            *item.label,
            class_="shiny-chat-page-nav-control",
        )
    if item.kind == "spacer":
        return Tag("span", class_="bslib-nav-spacer")
    if item.kind == "divider":
        return Tag("hr", class_="shiny-chat-page-nav-divider")
    if item.kind == "header":
        return Tag(
            "span",
            *item.label,
            class_="shiny-chat-page-nav-menu-header",
        )
    return Tag(
        "details",
        Tag(
            "summary",
            *item.label,
            class_="shiny-chat-page-nav-menu-toggle",
        ),
        Tag(
            "div",
            *(
                _render_page_nav_item(child, pages, resolved_id)
                for child in item.children
            ),
            class_="shiny-chat-page-nav-menu-items",
        ),
        class_="shiny-chat-page-nav-menu",
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
    drawer: bool | ChatDrawer = True,
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
        drawer=drawer,
        show_history=True,
        **kwargs,
    )


def _render_page_chat(
    chat_root: Tag,
    title: TagChild,
    icon: TagChild | None = None,
    *,
    id: str = "chat",
    pages_navbar: Sequence[ChatNavPanel | NavSetArg | MetadataNode]
    | None = None,
    toolbar: TagChild | None = None,
    toolbar_global: TagChild | None | MISSING_TYPE = MISSING,
    navbar_options: Any = None,
    sidebar: bool | ChatSidebar = True,
    window_title: str | None = None,
    lang: str | None = None,
    theme: str | Path | Theme | ThemeProvider | None = None,
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
    if isinstance(toolbar_global, MISSING_TYPE):
        toolbar_global_content: TagChild | None = ui.toolbar(
            ui.input_dark_mode()
        )
    else:
        toolbar_global_content = toolbar_global

    (
        normalized_pages,
        normalized_sidebars,
        home_sidebar_key,
        home_sidebar,
        nav_items,
    ) = _normalize_page_config(pages_navbar, sidebar)
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
                _render_page_nav_item(item, normalized_pages, resolved_id)
                for item in nav_items
            ),
            class_="shiny-chat-page-nav",
            aria_label="Pages",
        ),
        Tag(
            "div",
            Tag("div", class_="shiny-chat-page-toolbar-scoped"),
            Tag(
                "div",
                toolbar_global_content,
                class_="shiny-chat-page-toolbar-global",
            ),
            class_="shiny-chat-page-toolbar",
        ),
        class_="shiny-chat-page-controls",
    )
    toolbar_sources = Tag(
        "div",
        _render_toolbar_source("home", toolbar),
        *(
            _render_toolbar_source(
                page.toolbar_key,
                page.panel.toolbar,
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
                data_page_value=HOME_PAGE_VALUE,
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
                    aria_labelledby=(
                        f"{resolved_id}-nav-{index}"
                        if page.has_nav_control
                        else None
                    ),
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
        id=f"{resolved_id}_page",
        data_chat_id=resolved_id,
        data_active_page=HOME_PAGE_VALUE,
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
