from __future__ import annotations

import inspect
from typing import Any, cast

import pytest
from htmltools import HTMLDependency, tags
from shiny import module, ui
from shinychat import (
    ChatArtifact,
    ChatNavPanel,
    ChatSidebar,
    chat_artifact,
    chat_nav_panel,
    chat_sidebar,
    chat_ui,
    chat_ui_history,
)
from shinychat.express import Chat as ExpressChat


def test_public_page_chat_configuration_exports() -> None:
    assert isinstance(chat_sidebar(), ChatSidebar)
    assert isinstance(chat_artifact(), ChatArtifact)
    assert isinstance(chat_nav_panel("About"), ChatNavPanel)


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
        open=True,
        resizable=False,
    )

    assert artifact.title == "Preview"
    assert artifact.width == "32rem"
    assert artifact.open is True
    assert artifact.resizable is False

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

    with pytest.raises(TypeError, match="raw Shiny Sidebar objects"):
        chat_nav_panel("About", sidebar=ui.sidebar())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="`value` must not be an empty"):
        chat_nav_panel("About", value="")
    with pytest.raises(ValueError, match="`title` must not be an empty"):
        chat_nav_panel("")
    with pytest.raises(TypeError, match="`title` must be a string"):
        chat_nav_panel(cast(Any, tags.span("About")))


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
        open=True,
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
