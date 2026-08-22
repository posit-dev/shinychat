from shiny import App, reactive, render, ui

from shinychat import (
    Chat,
    chat_artifact_panel,
    chat_nav_panel,
    chat_sidebar,
    page_chat,
)


def artifact_content(version: str):
    return ui.tags.section(
        ui.p(ui.strong(version), " content with a live Shiny binding."),
        ui.input_text("artifact_note", "Artifact note", f"{version} draft"),
        ui.output_text_verbatim("artifact_echo"),
    )


app_ui = page_chat(
    "Artifact controls",
    id="chat",
    toolbar=ui.toolbar(
        ui.toolbar_input_button("show_artifact", "Show"),
        ui.toolbar_input_button("update_artifact", "Update"),
        ui.toolbar_input_button("clear_artifact", "Clear"),
        ui.toolbar_input_button("hide_artifact", "Hide"),
        ui.toolbar_input_button("toggle_artifact", "Toggle"),
    ),
    sidebar=False,
    pages_navbar=[
        chat_nav_panel(
            "Inspector",
            ui.h2("Mounted-state inspector"),
            ui.p(
                "Open the artifact, edit its note, visit this page, then "
                "return to the chat."
            ),
            sidebar=chat_sidebar(
                ui.p("A closed, resizable page-specific sidebar."),
                width=260,
                open="closed",
            ),
            toolbar=ui.toolbar(
                ui.toolbar_input_button(
                    "refresh_artifact",
                    "Refresh artifact",
                ),
            ),
        ),
    ],
    artifact_panel=chat_artifact_panel(
        artifact_content("Initial"),
        title="Live artifact",
        width="34rem",
        open=True,
    ),
    greeting="## Artifact controls\n\nUse the toolbar to change this panel.",
)


def server(input, output, session):
    chat = Chat("chat")

    @render.text
    def artifact_echo():
        return f"Bound value: {input.artifact_note() or ''}"

    @chat.on_user_submit
    async def _reply(user_input: str):
        await chat.append_message(f"You said: {user_input}")

    @reactive.effect
    @reactive.event(input.show_artifact)
    async def _show_artifact():
        await chat.artifact_panel.show(
            artifact_content("Shown"),
            title="Shown artifact",
        )

    @reactive.effect
    @reactive.event(input.update_artifact)
    async def _update_artifact():
        await chat.artifact_panel.update(
            artifact_content("Updated"),
            title="Updated artifact",
        )

    @reactive.effect
    @reactive.event(input.clear_artifact)
    async def _clear_artifact():
        await chat.artifact_panel.update(ui.TagList(), title="")

    @reactive.effect
    @reactive.event(input.hide_artifact)
    async def _hide_artifact():
        await chat.artifact_panel.hide()

    @reactive.effect
    @reactive.event(input.toggle_artifact)
    async def _toggle_artifact():
        await chat.artifact_panel.toggle()

    @reactive.effect
    @reactive.event(input.refresh_artifact)
    async def _refresh_artifact():
        await chat.artifact_panel.update(
            artifact_content("Inspector refresh"),
            title="Inspector artifact",
        )


app = App(app_ui, server)
