from pathlib import Path

from htmltools import HTMLDependency, TagList, tags
from shiny import reactive
from shiny.express import input, render, ui
from shinychat.express import Chat

ASSET_DIR = Path(__file__).parent / "_assets"

artifact_dependency = HTMLDependency(
    name="artifact-browser-test",
    version="1.0.0",
    source={"subdir": str(ASSET_DIR)},
    stylesheet=[{"href": "artifact.css"}],
)

ui.page_opts(title="Artifact browser test", fillable=True)

ui.div(
    ui.input_action_button("show_artifact", "Show artifact"),
    ui.input_action_button("update_artifact", "Update artifact"),
    ui.input_action_button("hide_artifact", "Hide artifact"),
    ui.input_action_button("show_preserved", "Show preserved"),
    ui.input_action_button("toggle_artifact", "Toggle artifact"),
    class_="d-flex gap-2 mb-3",
)

chat = Chat("chat")
chat.ui(
    artifact=True,
    width="100%",
    height="600px",
    fill=False,
    show_history=False,
)


def artifact_content(version: str) -> TagList:
    return TagList(
        artifact_dependency,
        tags.div(
            {"class": "artifact-dependency-marker"},
            tags.p({"class": "artifact-content-label"}, f"{version} content"),
            ui.input_text(
                "artifact_text",
                "Artifact value",
                value=version,
            ),
        ),
    )


@render.text
def artifact_echo() -> str:
    return f"Echo: {input.artifact_text()}"


@reactive.effect
@reactive.event(input.show_artifact)
async def _show_artifact() -> None:
    await chat.artifact.show(
        artifact_content("Initial"),
        title="Initial artifact",
    )


@reactive.effect
@reactive.event(input.update_artifact)
async def _update_artifact() -> None:
    await chat.artifact.update(
        artifact_content("Updated"),
        title="Updated artifact",
    )


@reactive.effect
@reactive.event(input.hide_artifact)
async def _hide_artifact() -> None:
    await chat.artifact.hide()


@reactive.effect
@reactive.event(input.show_preserved)
async def _show_preserved() -> None:
    await chat.artifact.show()


@reactive.effect
@reactive.event(input.toggle_artifact)
async def _toggle_artifact() -> None:
    await chat.artifact.toggle()
