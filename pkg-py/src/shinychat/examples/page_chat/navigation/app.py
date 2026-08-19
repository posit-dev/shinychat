from shiny import App, reactive, ui

from shinychat import (
    Chat,
    chat_artifact,
    chat_nav_panel,
    chat_sidebar,
    page_chat,
)


def artifact_content(label: str):
    return ui.tags.section(
        ui.h3("Preview"),
        ui.p(label),
    )


app_ui = page_chat(
    "Field notes",
    id="chat",
    toolbar=ui.toolbar(
        ui.toolbar_input_button("clear_chat", "Clear conversation"),
        ui.toolbar_input_button("show_preview", "Show preview"),
    ),
    toolbar_global=ui.toolbar(
        ui.toolbar_input_button("help", "Help"),
    ),
    sidebar=chat_sidebar(
        ui.h3("Workspace", class_="h6"),
        ui.input_text("project_name", "Project", "Coastal survey"),
        history=False,
        width=320,
        open="auto",
    ),
    pages=[
        chat_nav_panel(
            "Sources",
            ui.h2("Source checklist"),
            ui.input_checkbox_group(
                "sources",
                "Include in the analysis",
                ["Field observations", "Published research", "Local guidance"],
                selected=["Field observations", "Published research"],
            ),
            sidebar=True,
            # Compatibility alias: reuse the home-page toolbar here.
            toolbar=True,
        ),
        chat_nav_panel(
            "Settings",
            ui.h2("Answer settings"),
            ui.input_slider("length", "Target length", 100, 1000, 400),
            ui.input_switch("citations", "Request citations", True),
            sidebar=chat_sidebar(
                ui.p("This page has a fixed, page-specific sidebar."),
                history=False,
                width="18rem",
                open="always",
                resizable=False,
            ),
            toolbar=ui.toolbar(
                ui.toolbar_input_button(
                    "reset_settings",
                    "Reset settings",
                ),
            ),
        ),
        chat_nav_panel(
            "About",
            ui.h2("About this example"),
            ui.p(
                "This page has no page-scoped toolbar and no page-specific "
                "sidebar."
            ),
            sidebar=False,
            toolbar=None,
        ),
    ],
    artifact=chat_artifact(
        artifact_content("Use the home toolbar to open this preview."),
        title="Working preview",
        width=420,
    ),
    greeting="## Field notes\n\nTry the local echo response.",
    placeholder="Describe what you observed...",
)


def server(input, output, session):
    chat = Chat("chat")

    @chat.on_user_submit
    async def _reply(user_input: str):
        await chat.append_message(f"You said: {user_input}")
        await chat.artifact.update(
            artifact_content(f"Latest request: {user_input}"),
            title="Latest request",
        )

    @reactive.effect
    @reactive.event(input.clear_chat)
    async def _clear_chat():
        await chat.clear_messages(greeting=True)

    @reactive.effect
    @reactive.event(input.show_preview)
    async def _show_preview():
        await chat.artifact.show(title="Working preview")

    @reactive.effect
    @reactive.event(input.reset_settings)
    def _reset_settings():
        ui.update_slider("length", value=400)
        ui.update_switch("citations", value=True)

    @reactive.effect
    @reactive.event(input.help)
    def _help():
        ui.show_toast(
            ui.toast(
                "The Help control is global and remains available on every page.",
                header="Help",
                type="info",
            )
        )


app = App(app_ui, server)
