from shiny import App, reactive, render, ui

from shinychat import (
    Chat,
    chat_drawer,
    chat_nav_panel,
    chat_sidebar,
    page_chat,
)


def drawer_content(version: str):
    return ui.tags.section(
        ui.p(ui.strong(version), " content with a live Shiny binding."),
        ui.input_text("drawer_note", "Drawer note", f"{version} draft"),
        ui.output_text_verbatim("drawer_echo"),
    )


app_ui = page_chat(
    "Drawer controls",
    id="chat",
    toolbar=ui.toolbar(
        ui.toolbar_input_button("show_drawer", "Show"),
        ui.toolbar_input_button("update_drawer", "Update"),
        ui.toolbar_input_button("clear_drawer", "Clear"),
        ui.toolbar_input_button("hide_drawer", "Hide"),
        ui.toolbar_input_button("toggle_drawer", "Toggle"),
    ),
    sidebar=False,
    pages_navbar=[
        chat_nav_panel(
            "Inspector",
            ui.h2("Mounted-state inspector"),
            ui.p(
                "Open the drawer, edit its note, visit this page, then "
                "return to the chat."
            ),
            sidebar=chat_sidebar(
                ui.p("A closed, resizable page-specific sidebar."),
                width=260,
                open="closed",
            ),
            toolbar=ui.toolbar(
                ui.toolbar_input_button(
                    "refresh_drawer",
                    "Refresh drawer",
                ),
            ),
        ),
    ],
    drawer=chat_drawer(
        drawer_content("Initial"),
        title="Live drawer",
        width="34rem",
        open=True,
    ),
    greeting="## Drawer controls\n\nUse the toolbar to change this panel.",
)


def server(input, output, session):
    chat = Chat("chat")

    @render.text
    def drawer_echo():
        return f"Bound value: {input.drawer_note() or ''}"

    @chat.on_user_submit
    async def _reply(user_input: str):
        await chat.append_message(f"You said: {user_input}")

    @reactive.effect
    @reactive.event(input.show_drawer)
    async def _show_drawer():
        await chat.drawer.show(
            drawer_content("Shown"),
            title="Shown drawer",
        )

    @reactive.effect
    @reactive.event(input.update_drawer)
    async def _update_drawer():
        await chat.drawer.update(
            drawer_content("Updated"),
            title="Updated drawer",
        )

    @reactive.effect
    @reactive.event(input.clear_drawer)
    async def _clear_drawer():
        await chat.drawer.update(ui.TagList(), title="")

    @reactive.effect
    @reactive.event(input.hide_drawer)
    async def _hide_drawer():
        await chat.drawer.hide()

    @reactive.effect
    @reactive.event(input.toggle_drawer)
    async def _toggle_drawer():
        await chat.drawer.toggle()

    @reactive.effect
    @reactive.event(input.refresh_drawer)
    async def _refresh_drawer():
        await chat.drawer.update(
            drawer_content("Inspector refresh"),
            title="Inspector drawer",
        )


app = App(app_ui, server)
