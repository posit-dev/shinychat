from shiny import App, reactive, ui

from shinychat import (
    Chat,
    chat_artifact,
    chat_nav_panel,
    chat_sidebar,
    page_chat,
)
from shinychat.examples._echo import EchoChatClient
from shinychat.types import HistoryOptions

bs_icon_info_circle_fill = """
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-info-circle-fill" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 16A8 8 0 1 0 8 0a8 8 0 0 0 0 16m.93-9.412-1 4.705c-.07.34.029.533.304.533.194 0 .487-.07.686-.246l-.088.416c-.287.346-.92.598-1.465.598-.703 0-1.002-.422-.808-1.319l.738-3.468c.064-.293.006-.399-.287-.47l-.451-.081.082-.381 2.29-.287zM8 5.5a1 1 0 1 1 0-2 1 1 0 0 1 0 2"/></svg>
"""

bs_icon_gear_fill = """
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-gear-fill" viewBox="0 0 16 16" aria-hidden="true"><path d="M9.405 1.05c-.413-1.4-2.397-1.4-2.81 0l-.1.34a1.464 1.464 0 0 1-2.105.872l-.32-.16c-1.314-.655-2.74.771-2.084 2.085l.16.32c.38.76.011 1.673-.872 2.105l-.34.1c-1.4.413-1.4 2.397 0 2.81l.34.1c.883.432 1.252 1.345.872 2.105l-.16.32c-.656 1.314.77 2.74 2.084 2.084l.32-.16c.76-.38 1.673-.011 2.105.872l.1.34c.413 1.4 2.397 1.4 2.81 0l.1-.34a1.464 1.464 0 0 1 2.105-.872l.32.16c1.314.656 2.74-.77 2.084-2.084l-.16-.32c-.38-.76-.011-1.673.872-2.105l.34-.1c1.4-.413 1.4-2.397 0-2.81l-.34-.1a1.464 1.464 0 0 1-.872-2.105l.16-.32c.656-1.314-.77-2.74-2.084-2.084l-.32.16a1.464 1.464 0 0 1-2.105-.872zM8 10.93a2.93 2.93 0 1 1 0-5.86 2.93 2.93 0 0 1 0 5.86"/></svg>
"""


def artifact_content(label: str):
    return ui.tags.section(
        ui.h3("Preview"),
        ui.p(label),
    )


app_ui = page_chat(
    "Field notes",
    id="chat",
    toolbar=ui.toolbar(
        ui.toolbar_input_button("show_preview", "Show preview"),
    ),
    toolbar_global=ui.toolbar(
        ui.toolbar_input_button(
            "show_settings",
            "Answer settings",
            icon=ui.HTML(bs_icon_gear_fill),
            show_label=False,
            tooltip="Answer settings",
        ),
        ui.toolbar_input_button(
            "help",
            "Help",
            icon=ui.HTML(bs_icon_info_circle_fill),
            show_label=False,
            tooltip="Help",
        ),
    ),
    sidebar=chat_sidebar(
        ui.h3("Workspace", class_="h6"),
        ui.input_text("project_name", "Project", "Coastal survey"),
        history=True,
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
            "Notebook",
            ui.h2("Observation notebook"),
            ui.p(
                "Capture source notes on the Sources page, then return here to "
                "review the fieldwork plan."
            ),
            sidebar=chat_sidebar(
                ui.p("Notebook resources"),
                history=False,
                width="18rem",
                open="always",
                resizable=False,
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
        open=False,
    ),
    greeting="""## Field notes

Try the local echo response.

* <span class=\"suggestion\">Capture a new field note</span>
* <span class=\"suggestion\">Organize and summarize my notes</span>
* <span class=\"suggestion\">Analyze my notes for recurring observations</span>
""",
    placeholder="Describe what you observed...",
    icon_assistant=False,
    # theme=ui.Theme(preset="zephyr"),
)


def server(input, output, session):
    chat = Chat(
        "chat",
        client=EchoChatClient(),
        history=HistoryOptions(store="memory", title=None),
    )

    @chat.on_user_submit
    async def _update_artifact(user_input: str):
        await chat.artifact.update(
            artifact_content(f"Latest request: {user_input}"),
            title="Latest request",
        )

    @reactive.effect
    @reactive.event(input.show_preview)
    async def _show_preview():
        await chat.artifact.show(title="Working preview")

    @reactive.effect
    @reactive.event(input.show_settings)
    def _show_settings():
        ui.show_offcanvas(
            ui.offcanvas(
                ui.input_slider("length", "Target length", 100, 1000, 400),
                ui.input_switch("citations", "Request citations", True),
                ui.input_dark_mode(),
                title="Answer settings",
                footer=ui.input_action_button(
                    "reset_settings",
                    "Reset settings",
                ),
                id="answer_settings",
                placement="right",
            )
        )

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
