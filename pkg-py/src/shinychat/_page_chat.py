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

from ._utils_types import MISSING, MISSING_TYPE

if TYPE_CHECKING:
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


@dataclass(frozen=True)
class _NormalizedPage:
    panel: ChatNavPanel
    value: str
    sidebar_key: str | None


@dataclass(frozen=True)
class _NormalizedSidebar:
    key: str
    config: ChatSidebar


def _validate_page_child(
    value: TagChild, name: str, *, allow_none: bool = False
) -> None:
    if value is None and allow_none:
        return
    if value is None or isinstance(value, (bool, dict)):
        expected = "an HTML child"
        if allow_none:
            expected += " or None"
        raise TypeError(
            f"`{name}` must be {expected}, not {type(value).__name__}."
        )


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
    sidebar: bool | ChatSidebar,
) -> tuple[
    tuple[_NormalizedPage, ...],
    tuple[_NormalizedSidebar, ...],
    str | None,
    ChatSidebar | None,
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
        if not isinstance(panel.sidebar, (bool, ChatSidebar)):
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
        elif panel.sidebar is False:
            sidebar_key = None
        else:
            sidebar_key = f"page-{index + 1}"
            sidebars.append(
                _NormalizedSidebar(
                    sidebar_key,
                    _normalize_sidebar_config(panel.sidebar),
                )
            )

        normalized_pages.append(
            _NormalizedPage(
                panel=panel,
                value=value,
                sidebar_key=sidebar_key,
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
        show_history=False,
        **kwargs,
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
    """Create a full-window page containing one persistent chat interface."""
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
        sidebar=sidebar,
        window_title=window_title,
        lang=lang,
        theme=theme,
    )


def _render_page_chat(
    chat_root: Tag,
    title: TagChild,
    icon: TagChild | None = None,
    *,
    id: str = "chat",
    pages: Sequence[ChatNavPanel] | None = None,
    toolbar: TagChild | None = None,
    sidebar: bool | ChatSidebar = True,
    window_title: str | None = None,
    lang: str | None = None,
    theme: Any = None,
) -> Tag:
    from shiny import ui
    from shiny.module import resolve_id

    if not isinstance(id, str):
        raise TypeError(f"`id` must be a string, not {type(id).__name__}.")
    if not id.strip():
        raise ValueError("`id` must not be an empty string.")
    _validate_page_child(title, "title")
    if isinstance(title, str) and not title.strip():
        raise ValueError("`title` must not be an empty string.")
    _validate_page_child(icon, "icon", allow_none=True)
    _validate_page_child(toolbar, "toolbar", allow_none=True)
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
            toolbar,
            class_="shiny-chat-page-toolbar",
        ),
        class_="shiny-chat-page-controls",
    )

    shell = Tag(
        "shiny-chat-page",
        Tag(
            "header",
            Tag(
                "button",
                Tag("span", class_="navbar-toggler-icon"),
                type="button",
                class_="shiny-chat-page-sidebar-toggle navbar-toggler",
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
        ),
        Tag(
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
                ),
                *(
                    Tag(
                        "section",
                        *page.panel.content,
                        id=f"{resolved_id}-panel-{index}",
                        class_="shiny-chat-page-panel",
                        aria_labelledby=f"{resolved_id}-nav-{index}",
                        data_page_value=page.value,
                        data_page_title=page.panel.title,
                        data_sidebar_key=page.sidebar_key,
                        hidden=True,
                    )
                    for index, page in enumerate(normalized_pages, start=1)
                ),
                class_="shiny-chat-page-main",
            ),
            class_="shiny-chat-page-body",
        ),
        data_chat_id=resolved_id,
        data_active_page="home",
    )

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
