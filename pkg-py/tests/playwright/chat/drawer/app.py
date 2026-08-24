from pathlib import Path

from htmltools import HTMLDependency, TagList, tags
from shiny import reactive
from shiny.express import input, render, ui
from shinychat.express import Chat

ASSET_DIR = Path(__file__).parent / "_assets"

drawer_dependency = HTMLDependency(
    name="drawer-browser-test",
    version="1.0.0",
    source={"subdir": str(ASSET_DIR)},
    stylesheet=[{"href": "drawer.css"}],
)

ui.page_opts(title="Drawer browser test", fillable=True)

ui.div(
    ui.input_action_button("show_drawer", "Show drawer"),
    ui.input_action_button("update_drawer", "Update drawer"),
    ui.input_action_button("clear_drawer", "Clear drawer"),
    ui.input_action_button("hide_drawer", "Hide drawer"),
    ui.input_action_button("show_preserved", "Show preserved"),
    ui.input_action_button("toggle_drawer", "Toggle drawer"),
    class_="d-flex gap-2 mb-3",
)

chat = Chat("chat")
chat.ui(
    drawer=True,
    width="100%",
    height="600px",
    fill=False,
    show_history=False,
)


def drawer_content(version: str) -> TagList:
    return TagList(
        drawer_dependency,
        tags.div(
            {"class": "drawer-dependency-marker"},
            tags.p({"class": "drawer-content-label"}, f"{version} content"),
            ui.input_text(
                "drawer_text",
                "Drawer value",
                value=version,
            ),
            tags.div(id="drawer_output", class_="shiny-text-output"),
        ),
    )


@render.text
def drawer_echo() -> str:
    return f"Echo: {input.drawer_text()}"


with ui.hold():

    @render.text
    def drawer_output() -> str:
        return f"Drawer output: {input.drawer_text()}"


@reactive.effect
@reactive.event(input.show_drawer)
async def _show_drawer() -> None:
    await chat.drawer.show(
        drawer_content("Initial"),
        title="Initial drawer",
    )


@reactive.effect
@reactive.event(input.update_drawer)
async def _update_drawer() -> None:
    await chat.drawer.update(
        drawer_content("Updated"),
        title="Updated drawer",
    )


@reactive.effect
@reactive.event(input.clear_drawer)
async def _clear_drawer() -> None:
    await chat.drawer.update(TagList(), title="")


@reactive.effect
@reactive.event(input.hide_drawer)
async def _hide_drawer() -> None:
    await chat.drawer.hide()


@reactive.effect
@reactive.event(input.show_preserved)
async def _show_preserved() -> None:
    await chat.drawer.show()


@reactive.effect
@reactive.event(input.toggle_drawer)
async def _toggle_drawer() -> None:
    await chat.drawer.toggle()
