from __future__ import annotations

import importlib
import inspect
import re
from typing import Any, cast

import pytest
import shinychat
from htmltools import HTMLDependency, Tag, tags
from shiny import module, ui
from shinychat import (
    chat_artifact,
    chat_nav_panel,
    chat_sidebar,
    chat_ui,
    chat_ui_history,
    page_chat,
    page_chat_theme,
)
from shinychat._utils_types import MISSING
from shinychat.express import Chat as ExpressChat
from shinychat.types import ChatArtifact, ChatNavPanel, ChatSidebar


def test_public_page_chat_configuration_exports() -> None:
    assert isinstance(chat_sidebar(), ChatSidebar)
    assert chat_sidebar().history is MISSING
    artifact = chat_artifact()
    assert isinstance(artifact, ChatArtifact)
    assert artifact.open is True
    assert isinstance(chat_nav_panel("About"), ChatNavPanel)
    assert callable(page_chat)
    assert callable(page_chat_theme)
    assert not hasattr(shinychat, "ChatArtifact")
    assert not hasattr(shinychat, "ChatNavPanel")
    assert not hasattr(shinychat, "ChatSidebar")


def test_page_chat_theme_composes_preset_and_caller_overrides() -> None:
    assert page_chat_theme().preset == "shiny"

    custom_theme = page_chat_theme(
        preset="flatly",
        primary="#123456",
        shiny_chat_page_canvas_bg="#f0f0f0",
    )
    assert custom_theme.preset == "flatly"

    css = custom_theme.to_css()
    assert "--shiny-chat-page-canvas-bg: #f0f0f0" in css
    assert "--bs-primary: #123456" in css
    assert "--shiny-chat-page-header-height: 3.25rem" in css
    assert "--shiny-chat-page-fill-padding:" in css
    assert (
        "--shiny-chat-fill-padding: var(--shiny-chat-page-fill-padding)" in css
    )
    assert (
        "--shiny-chat-input-padding-bottom: "
        "var(--shiny-chat-page-input-padding-bottom)" in css
    )
    assert "background:var(--shiny-chat-page-artifact-bg)" in css
    assert "box-shadow:var(--shiny-chat-page-artifact-box-shadow)" in css
    assert "background:var(--shiny-chat-page-artifact-header-bg)" in css


def test_chat_sidebar_normalizes_and_validates_values() -> None:
    sidebar = chat_sidebar(
        tags.p("Sidebar"),
        history=True,
        width=280,
        open="always",
        resizable=False,
    )

    assert sidebar.content == (tags.p("Sidebar"),)
    assert sidebar.history is True
    assert sidebar.width == "280px"
    assert sidebar.open == "always"
    assert sidebar.resizable is False

    assert chat_sidebar(open=True).open == "open"
    assert chat_sidebar(open=False).open == "closed"
    with pytest.raises(ValueError, match="`open` must be one of"):
        chat_sidebar(open="hidden")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="`history` must be a bool"):
        chat_sidebar(history=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive CSS width"):
        chat_sidebar(width=-1)
    with pytest.raises(ValueError, match="positive CSS width"):
        chat_sidebar(width=0)
    with pytest.raises(ValueError, match="empty CSS width"):
        chat_sidebar(width="   ")

    widths = (
        "30rem",
        "calc(100% - 2rem)",
        "min(100%, 60rem)",
        "clamp(20rem, 50vw, 60rem)",
        "var(--chat-width)",
        "30cqw",
        "100dvh",
        "auto",
        "garbage",
        "clamp(20rem, 50vw, 60rem",
    )
    for width in widths:
        assert chat_sidebar(width=width).width == width


def test_chat_artifact_normalizes_and_validates_values() -> None:
    artifact = chat_artifact(
        tags.p("Artifact"),
        title="Preview",
        width="32rem",
        resizable=False,
    )

    assert artifact.title == "Preview"
    assert artifact.width == "32rem"
    assert artifact.open is True
    assert artifact.resizable is False
    assert chat_artifact(open=False).open is False

    with pytest.raises(TypeError, match="`title` must be a string"):
        chat_artifact(title=1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="`open` must be a bool"):
        chat_artifact(open="true")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="`width` must be a CSS width"):
        chat_artifact(width=True)
    assert chat_artifact(width=400).width == "400px"
    assert chat_artifact(width=400.5).width == "400.5px"


def test_chat_nav_panel_validates_sidebar_and_navigation_values() -> None:
    sidebar = chat_sidebar(tags.p("Conversation history"))
    panel = chat_nav_panel(
        "About",
        tags.p("Details"),
        value="about",
        icon=tags.span("i"),
        sidebar=sidebar,
    )

    assert panel.title == "About"
    assert panel.value == "about"
    assert panel.sidebar is sidebar
    assert panel.toolbar is None
    assert panel.content_width == "min(680px, 100%)"
    assert chat_nav_panel("Default").sidebar is False

    assert chat_nav_panel("Wide", content_width=720).content_width == "720px"
    assert (
        chat_nav_panel("Full", content_width="100vw").content_width == "100vw"
    )
    assert chat_nav_panel("Inherited", toolbar=True).toolbar is True
    assert chat_nav_panel("Legacy empty", toolbar=False).toolbar is False
    custom_toolbar = tags.span("Custom toolbar")
    assert (
        chat_nav_panel("Custom", toolbar=custom_toolbar).toolbar
        is custom_toolbar
    )

    with pytest.raises(TypeError, match="raw Shiny Sidebar objects"):
        chat_nav_panel("About", sidebar=ui.sidebar())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="`value` must not be an empty"):
        chat_nav_panel("About", value="")
    with pytest.raises(ValueError, match="`title` must not be an empty"):
        chat_nav_panel("")
    with pytest.raises(TypeError, match="`title` must be a string"):
        chat_nav_panel(cast(Any, tags.span("About")))
    with pytest.raises(ValueError, match="empty CSS width"):
        chat_nav_panel("About", content_width=" ")
    assert chat_nav_panel(
        "About", toolbar=cast(Any, {"class": "bad"})
    ).toolbar == {"class": "bad"}


def test_sidebar_history_defaults_to_its_page_owner() -> None:
    home_html = page_chat(
        "Assistant",
        sidebar=chat_sidebar(),
    ).get_html_string()
    panel_html = page_chat(
        "Assistant",
        sidebar=False,
        pages=[chat_nav_panel("About", sidebar=chat_sidebar())],
    ).get_html_string()

    assert home_html.count("<shiny-chat-history") == 1
    assert "<shiny-chat-history" not in panel_html


def test_chat_ui_history_resolves_id_and_forwards_html_attributes() -> None:
    with module.namespace_context("module"):  # pyright: ignore[reportPrivateImportUsage]
        history = chat_ui_history("chat", class_="history", data_source="page")

    html = history.get_html_string()
    assert "<shiny-chat-history" in html
    assert 'for="module-chat"' in html
    assert 'class="history"' in html
    assert 'data-source="page"' in html
    assert "shinychat" in [
        dependency.name for dependency in history.get_dependencies()
    ]


def test_chat_ui_history_rejects_structural_and_invalid_attributes() -> None:
    with pytest.raises(ValueError, match="sets its own `for`"):
        chat_ui_history("chat", **{"for": "other"})
    with pytest.raises(TypeError, match="HTML attribute value"):
        chat_ui_history(
            "chat", data_value=cast(Any, tags.span("not an attribute"))
        )


def test_chat_ui_defaults_to_closed_artifact_and_embedded_history() -> None:
    html = chat_ui("chat", fill=False).get_html_string()

    assert html.count("<shiny-chat-artifact") == 1
    assert 'width="400px"' in html
    assert "show-history" not in html
    assert " open=" not in html
    assert "resizable=" not in html


def test_chat_ui_artifact_false_omits_artifact_support() -> None:
    html = chat_ui("chat", artifact=False, fill=False).get_html_string()

    assert "shiny-chat-artifact" not in html


def test_chat_ui_artifact_carries_content_and_dependencies() -> None:
    dependency = HTMLDependency(
        "artifact-widget",
        "1.0.0",
        head="<meta name='artifact-widget'>",
    )
    artifact = chat_artifact(
        tags.div(dependency, "Artifact content"),
        title="Preview",
        width=320,
        resizable=False,
    )
    tag = chat_ui("chat", artifact=artifact, fill=False)
    html = tag.get_html_string()

    assert 'title="Preview"' in html
    assert 'width="320px"' in html
    assert 'open=""' in html
    assert 'resizable="false"' in html
    assert "Artifact content" in html
    assert "artifact-widget" in [dep.name for dep in tag.get_dependencies()]


def test_chat_ui_show_history_false_is_explicit() -> None:
    html = chat_ui("chat", show_history=False, fill=False).get_html_string()

    assert 'show-history="false"' in html


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        (
            {"artifact": 1},
            "`artifact` must be a bool or a shinychat `ChatArtifact`",
        ),
        ({"show_history": "false"}, "`show_history` must be a bool"),
    ],
)
def test_chat_ui_validates_page_chat_values(
    kwargs: dict[str, object], match: str
) -> None:
    with pytest.raises(TypeError, match=match):
        chat_ui("chat", **kwargs)  # type: ignore[arg-type]


def test_core_and_express_ui_signatures_include_page_chat_values() -> None:
    for fn in (chat_ui, ExpressChat.ui):
        parameters = inspect.signature(fn).parameters
        assert parameters["artifact"].default is True
        assert parameters["show_history"].default is True
        assert parameters["artifact"].kind is inspect.Parameter.KEYWORD_ONLY
        assert parameters["show_history"].kind is inspect.Parameter.KEYWORD_ONLY


def test_page_chat_signature_makes_icon_keyword_only() -> None:
    parameters = inspect.signature(page_chat).parameters

    assert list(parameters) == [
        "title",
        "id",
        "icon",
        "pages",
        "toolbar",
        "toolbar_global",
        "navbar_options",
        "sidebar",
        "artifact",
        "window_title",
        "lang",
        "theme",
        "messages",
        "greeting",
        "placeholder",
        "width",
        "icon_assistant",
        "enable_cancel",
        "allow_attachments",
        "footer",
        "kwargs",
    ]
    assert parameters["title"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert parameters["icon"].kind is inspect.Parameter.KEYWORD_ONLY
    for name in list(parameters)[2:-1]:
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["id"].default == "chat"
    assert parameters["artifact"].default is True
    assert parameters["sidebar"].default is True
    assert parameters["toolbar"].default is None
    assert parameters["toolbar_global"].default is MISSING
    assert parameters["placeholder"].default == "Enter a message..."
    assert parameters["width"].default == "min(680px, 100%)"


def test_page_chat_builds_default_fillable_page_markup() -> None:
    html = page_chat("Assistant").get_html_string()

    assert "<title>Assistant</title>" in html
    assert (
        '<shiny-chat-page data-chat-id="chat" data-active-page="home">' in html
    )
    assert 'class="shiny-chat-page-header"' in html
    assert 'data-bs-theme="auto"' in html
    assert 'data-shiny-chat-page-nav-style="underline"' in html
    assert "<bslib-input-dark-mode" in html
    assert 'attribute="data-bs-theme"' in html
    assert html.count("<bslib-input-dark-mode") == 1
    assert 'aria-controls="chat-sidebar"' in html
    assert 'aria-expanded="false"' in html
    assert 'class="shiny-chat-page-sidebar-icon bi bi-list"' in html
    assert '<div class="shiny-chat-page-identity">' in html
    assert "data-page-home" not in html
    assert html.count('class="shiny-chat-page-controls"') == 1
    assert html.count('aria-label="Pages"') == 1
    assert html.count("shiny-chat-page-controls-mount-mobile") == 1
    assert 'id="chat-sidebar"' in html
    assert 'aria-label="App menu"' in html
    assert 'data-sidebar-key="default"' in html
    assert html.count('data-sidebar-for="default"') == 1
    assert 'data-sidebar-open="auto"' in html
    assert 'data-sidebar-width="280px"' in html
    assert 'data-sidebar-resizable="true"' in html
    assert html.count("<shiny-chat-history") == 1
    assert 'for="chat"' in html
    assert 'data-page-value="home"' in html
    assert 'id="chat"' in html
    assert "height:100%" in html
    assert 'show-history="false"' not in html


def test_page_chat_global_toolbar_dark_mode_has_explicit_opt_out() -> None:
    default_html = page_chat("Assistant").get_html_string()
    opt_out_html = page_chat("Assistant", toolbar_global=None).get_html_string()

    assert re.search(
        r'class="shiny-chat-page-toolbar-global">\s*<bslib-input-dark-mode',
        default_html,
    )
    assert "<bslib-input-dark-mode" not in opt_out_html


def test_page_chat_applies_supported_navbar_options_to_its_title_bar() -> None:
    html = page_chat(
        "Assistant",
        navbar_options=ui.navbar_options(
            bg="#123456",
            theme="dark",
            underline=False,
            class_="custom-header",
            data_test="navbar",
        ),
    ).get_html_string()

    header = re.search(r"<header[^>]*>", html)
    assert header is not None
    assert 'class="shiny-chat-page-header custom-header"' in header.group(0)
    assert 'data-test="navbar"' in header.group(0)
    assert 'data-bs-theme="dark"' in header.group(0)
    assert 'data-shiny-chat-page-nav-style="pill"' in header.group(0)
    assert "background-color:#123456;" in header.group(0)

    with pytest.raises(ValueError, match=r"cannot set `position`"):
        page_chat(
            "Assistant",
            navbar_options=ui.navbar_options(position="fixed-top"),
        )
    with pytest.raises(ValueError, match=r"cannot set `collapsible`"):
        page_chat(
            "Assistant",
            navbar_options=ui.navbar_options(collapsible=False),
        )
    with pytest.raises(TypeError, match=r"must be created by"):
        page_chat("Assistant", navbar_options=cast(Any, {}))


def test_page_chat_normalizes_navigation_toolbar_and_sidebars() -> None:
    custom_sidebar = chat_sidebar(
        tags.p("Settings menu"),
        history=True,
        width=360,
        open="closed",
        resizable=False,
    )
    with module.namespace_context("mod"):  # pyright: ignore[reportPrivateImportUsage]
        page = page_chat(
            tags.span("Reactive title"),
            icon=tags.i("icon"),
            id="assistant",
            pages=[
                chat_nav_panel(
                    "About",
                    tags.p("About content"),
                    icon=tags.i("info"),
                    sidebar=True,
                    toolbar=True,
                ),
                chat_nav_panel(
                    "Settings",
                    tags.p("Settings content"),
                    value="settings",
                    sidebar=custom_sidebar,
                    toolbar=ui.input_action_button(
                        "settings_save", "Save settings"
                    ),
                ),
                chat_nav_panel("Help", tags.p("Help content")),
            ],
            toolbar=ui.input_action_button("save", "Save"),
            toolbar_global=ui.input_action_button("help", "Help"),
            sidebar=chat_sidebar(
                tags.p("Home menu"),
                history=True,
                width="20rem",
                open="always",
            ),
            window_title="Chat window",
        )

    html = page.get_html_string()
    assert "<title>Chat window</title>" in html
    assert 'data-chat-id="mod-assistant"' in html
    assert 'aria-controls="mod-assistant-sidebar"' in html
    assert 'id="mod-assistant-sidebar"' in html
    assert '<button type="button" class="shiny-chat-page-identity"' in html
    assert html.count("<span>Reactive title</span>") == 1
    assert 'data-page-home=""' in html
    assert 'aria-label="Return to chat"' in html
    assert html.count('data-page-target="About"') == 1
    assert html.count('data-page-target="settings"') == 1
    assert html.count('data-page-target="Help"') == 1
    assert '<nav class="shiny-chat-page-nav" aria-label="Pages">' in html
    for index in range(1, 4):
        assert f'id="mod-assistant-nav-{index}"' in html
        assert f'aria-controls="mod-assistant-panel-{index}"' in html
        assert f'id="mod-assistant-panel-{index}"' in html
        assert f'aria-labelledby="mod-assistant-nav-{index}"' in html
    assert 'role="tab"' not in html
    assert "aria-selected" not in html
    assert 'tabindex="-1"' not in html
    assert 'role="tabpanel"' not in html
    assert html.count('id="mod-save"') == 1
    assert html.count('id="mod-help"') == 1
    assert html.index('class="shiny-chat-page-toolbar-scoped"') < html.index(
        'class="shiny-chat-page-toolbar-global"'
    )
    assert html.count('data-page-toolbar-source="home"') == 3
    assert html.count('data-page-toolbar-source="page-2"') == 2
    assert html.count('class="shiny-chat-page-toolbar-source"') == 2
    assert html.count('class="shiny-chat-page-toolbar-content"') == 2
    assert html.count('id="mod-settings_save"') == 1
    assert 'data-page-toolbar-source="home"' in re.search(
        r'<section[^>]*data-page-value="About"[^>]*>',
        html,
    ).group(0)  # type: ignore[union-attr]
    assert 'data-page-toolbar-source="page-2"' in re.search(
        r'<section[^>]*data-page-value="settings"[^>]*>',
        html,
    ).group(0)  # type: ignore[union-attr]
    assert "data-page-toolbar-source" not in re.search(
        r'<section[^>]*data-page-value="Help"[^>]*>',
        html,
    ).group(0)  # type: ignore[union-attr]
    assert html.count('data-sidebar-for="home"') == 1
    assert html.count('data-sidebar-for="default"') == 1
    assert html.count('data-sidebar-for="page-2"') == 1
    assert html.count("<shiny-chat-history") == 3
    assert html.count('for="mod-assistant"') == 3
    assert html.count("Settings menu") == 1
    assert 'data-sidebar-open="closed"' in html
    assert 'data-sidebar-width="360px"' in html
    assert 'data-sidebar-resizable="false"' in html
    assert 'data-page-value="About"' in html
    assert 'data-page-value="settings"' in html
    assert 'data-page-value="Help"' in html
    sidebar_panel_tags = re.findall(
        r'<div class="shiny-chat-page-sidebar-panel"[^>]*>', html
    )
    sidebar_panels: dict[str, str] = {}
    sidebar_keys: list[str] = []
    for panel in sidebar_panel_tags:
        key = re.search(r'data-sidebar-for="([^"]+)"', panel)
        assert key is not None
        sidebar_key = key.group(1)
        sidebar_keys.append(sidebar_key)
        sidebar_panels[sidebar_key] = panel
    assert sidebar_keys == ["default", "home", "page-2"]
    assert 'hidden=""' not in sidebar_panels["home"]
    assert 'hidden=""' in sidebar_panels["default"]
    assert 'hidden=""' in sidebar_panels["page-2"]
    assert html.count('hidden=""') == 6
    assert '<div class="shiny-chat-page-toolbar-sources" hidden="">' in html
    assert 'data-page-title="Settings"' in html
    assert "About content" in html
    assert "Settings content" in html
    assert "Help content" in html


def test_page_chat_sidebar_false_keeps_hidden_default_for_nav_page() -> None:
    html = page_chat(
        "Assistant",
        sidebar=False,
        pages=[chat_nav_panel("About", tags.p("About"), sidebar=True)],
    ).get_html_string()

    assert 'class="shiny-chat-page-sidebar"' in html
    assert "shiny-chat-page-controls-mount-mobile" in html
    assert html.count('data-sidebar-for="default"') == 1
    assert html.count("<shiny-chat-history") == 1
    default_panel = re.search(
        r'<div class="shiny-chat-page-sidebar-panel"'
        r'[^>]*data-sidebar-for="default"[^>]*>',
        html,
    )
    assert default_panel is not None
    assert 'hidden=""' in default_panel.group(0)
    home_start = html.index('data-page-value="home"')
    home_end = html.index("</section>", home_start)
    assert "data-sidebar-key" not in html[home_start:home_end]
    about_start = html.index('data-page-value="About"')
    about_end = html.index("</section>", about_start)
    assert 'data-sidebar-key="default"' in html[about_start:about_end]


def test_page_chat_inherited_empty_toolbar_has_one_home_source() -> None:
    html = page_chat(
        "Assistant",
        pages=[chat_nav_panel("About", tags.p("About"), toolbar=True)],
    ).get_html_string()

    assert html.count('data-page-toolbar-source="home"') == 3
    assert html.count('class="shiny-chat-page-toolbar-source"') == 1
    assert html.count('class="shiny-chat-page-toolbar-content"') == 1


def test_page_chat_nav_toolbar_defaults_and_legacy_booleans() -> None:
    html = page_chat(
        "Assistant",
        toolbar=tags.button("Home"),
        toolbar_global=tags.button("Global"),
        pages=[
            chat_nav_panel("Default"),
            chat_nav_panel("Inherited", toolbar=True),
            chat_nav_panel("Legacy empty", toolbar=False),
            chat_nav_panel("Custom", toolbar=tags.button("Custom")),
        ],
    ).get_html_string()

    assert html.count('class="shiny-chat-page-toolbar-source"') == 2
    assert html.count('class="shiny-chat-page-toolbar-content"') == 2
    assert re.search(
        r'class="shiny-chat-page-toolbar-global">\s*<button>Global</button>',
        html,
    )
    sections: dict[str, str] = {}
    for value in ("Default", "Inherited", "Legacy empty", "Custom"):
        section = re.search(
            rf'<section[^>]*data-page-value="{value}"[^>]*>', html
        )
        assert section is not None
        sections[value] = section.group(0)
    assert "data-page-toolbar-source" not in sections["Default"]
    assert 'data-page-toolbar-source="home"' in sections["Inherited"]
    assert "data-page-toolbar-source" not in sections["Legacy empty"]
    assert 'data-page-toolbar-source="page-4"' in sections["Custom"]


def test_page_chat_sidebar_false_without_nav_sidebar_has_no_panel() -> None:
    html = page_chat("Assistant", sidebar=False).get_html_string()

    assert 'class="shiny-chat-page-sidebar"' in html
    assert "shiny-chat-page-controls-mount-mobile" in html
    assert "data-sidebar-for" not in html
    assert "<shiny-chat-history" not in html


def test_page_chat_nav_panel_content_width_contract() -> None:
    html = page_chat(
        "Assistant",
        pages=[
            chat_nav_panel("Default", tags.p("Default")),
            chat_nav_panel("Custom", tags.p("Custom"), content_width="42rem"),
            chat_nav_panel("Percent", tags.p("Percent"), content_width="100%"),
            chat_nav_panel(
                "Viewport", tags.p("Viewport"), content_width="100vw"
            ),
            chat_nav_panel(
                "Dynamic", tags.p("Dynamic"), content_width="100dvw"
            ),
        ],
    ).get_html_string()

    assert html.count('class="shiny-chat-page-panel-content"') == 5
    assert "--shiny-chat-page-content-width:min(680px, 100%)" in html
    assert "--shiny-chat-page-content-width:42rem" in html
    assert html.count('data-content-full-bleed="true"') == 3


@pytest.mark.parametrize("open", ["open", "always"])
def test_page_chat_initial_sidebar_aria_matches_open_state(open: str) -> None:
    html = page_chat(
        "Assistant",
        sidebar=chat_sidebar(open=cast(Any, open)),
    ).get_html_string()

    assert 'aria-expanded="true"' in html


@pytest.mark.parametrize(
    ("sidebar", "match"),
    [
        (
            ChatSidebar(
                content=cast(Any, []),
                history=False,
                width="280px",
                open="auto",
                resizable=True,
            ),
            "content.*tuple",
        ),
        (
            ChatSidebar(
                content=(),
                history=cast(Any, "yes"),
                width="280px",
                open="auto",
                resizable=True,
            ),
            "`history` must be a bool",
        ),
        (
            ChatSidebar(
                content=(),
                history=False,
                width="",
                open="auto",
                resizable=True,
            ),
            "empty CSS width",
        ),
        (
            ChatSidebar(
                content=(),
                history=False,
                width="280px",
                open=cast(Any, "sometimes"),
                resizable=True,
            ),
            "`open` must be one of",
        ),
        (
            ChatSidebar(
                content=(),
                history=False,
                width="280px",
                open="auto",
                resizable=cast(Any, 1),
            ),
            "`resizable` must be a bool",
        ),
    ],
)
def test_page_chat_revalidates_direct_sidebar_objects(
    sidebar: ChatSidebar,
    match: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=match):
        page_chat("Assistant", sidebar=sidebar)


@pytest.mark.parametrize(
    ("pages", "match"),
    [
        ([chat_nav_panel("Home", value="home")], '"home" is reserved'),
        (
            [
                chat_nav_panel("One", value="same"),
                chat_nav_panel("Two", value="same"),
            ],
            "Duplicate navigation page value",
        ),
        ([cast(Any, tags.p("Not a panel"))], "only `ChatNavPanel`"),
        (cast(Any, "About"), "sequence of `ChatNavPanel`"),
    ],
)
def test_page_chat_rejects_invalid_pages(
    pages: Any,
    match: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=match):
        page_chat("Assistant", pages=pages)


@pytest.mark.parametrize("name", ["height", "fill", "show_history"])
def test_page_chat_rejects_overriding_owned_chat_arguments(name: str) -> None:
    with pytest.raises(TypeError, match=rf"`page_chat\(\)` owns `{name}`"):
        page_chat("Assistant", **{name: cast(Any, "override")})


@pytest.mark.parametrize(
    ("kwargs", "error", "match"),
    [
        ({"id": ""}, ValueError, "`id` must not be an empty"),
        ({"id": cast(Any, 1)}, TypeError, "`id` must be a string"),
        (
            {"title": cast(Any, None)},
            TypeError,
            "`title` must not be None",
        ),
        ({"title": " "}, ValueError, "`title` must not be an empty"),
        (
            {"sidebar": cast(Any, ui.sidebar())},
            TypeError,
            "raw Shiny Sidebar objects",
        ),
        (
            {"window_title": cast(Any, tags.span("bad"))},
            TypeError,
            "`window_title` must be a string",
        ),
        ({"lang": cast(Any, 1)}, TypeError, "`lang` must be a string"),
        ({"lang": " "}, ValueError, "`lang` must not be an empty"),
    ],
)
def test_page_chat_validates_page_arguments(
    kwargs: dict[str, Any],
    error: type[Exception],
    match: str,
) -> None:
    title = kwargs.pop("title", "Assistant")
    with pytest.raises(error, match=match):
        page_chat(title, **kwargs)


def test_page_chat_passes_generic_ui_children_to_htmltools() -> None:
    assert page_chat("Assistant", icon=cast(Any, False)) is not None
    assert (
        page_chat("Assistant", toolbar=cast(Any, {"class": "bad"})) is not None
    )
    assert chat_nav_panel("About", icon=cast(Any, False)).icon is False
    assert chat_nav_panel(
        "About", toolbar=cast(Any, {"class": "bad"})
    ).toolbar == {"class": "bad"}


def test_page_chat_forwards_original_id_and_chat_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_chat_ui(id: str, **kwargs: Any) -> Tag:
        calls.append((id, kwargs))
        return tags.div("Chat", id=f"fake-{id}")

    chat_module = importlib.import_module("shinychat._chat")
    monkeypatch.setattr(chat_module, "chat_ui", fake_chat_ui)

    with module.namespace_context("mod"):  # pyright: ignore[reportPrivateImportUsage]
        page = page_chat(
            "Assistant",
            id="chat",
            messages=["Hello"],
            greeting="Welcome",
            placeholder="Ask",
            width="40rem",
            enable_cancel=True,
            allow_attachments=["text/plain"],
            footer=tags.small("Footer"),
            artifact=False,
            submit_key="enter+modifier",
            tool_grouping="all",
            class_="chat-attrs",
        )

    assert page is not None
    assert len(calls) == 1
    called_id, options = calls[0]
    assert called_id == "chat"
    assert options["height"] == "100%"
    assert options["fill"] is True
    assert options["show_history"] is True
    assert options["messages"] == ["Hello"]
    assert options["greeting"] == "Welcome"
    assert options["placeholder"] == "Ask"
    assert options["width"] == "40rem"
    assert options["enable_cancel"] is True
    assert options["allow_attachments"] == ["text/plain"]
    assert options["artifact"] is False
    assert options["submit_key"] == "enter+modifier"
    assert options["tool_grouping"] == "all"
    assert options["class_"] == "chat-attrs"
    assert 'data-chat-id="mod-chat"' in page.get_html_string()


def test_page_chat_omits_document_title_for_non_string_title() -> None:
    html = page_chat(
        tags.span("Display title"), sidebar=False
    ).get_html_string()

    assert "<title>" not in html
    assert html.count("Display title") == 1
