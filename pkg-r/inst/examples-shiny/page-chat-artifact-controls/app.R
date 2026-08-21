library(shiny)
library(shinychat)

artifact_content <- function(version) {
  tags$section(
    tags$p(tags$strong(version), " content with a live Shiny binding."),
    textInput("artifact_note", "Artifact note", paste(version, "draft")),
    verbatimTextOutput("artifact_echo")
  )
}

ui <- page_chat(
  "Artifact controls",
  id = "chat",
  toolbar = bslib::toolbar(
    bslib::toolbar_input_button("show_artifact", "Show"),
    bslib::toolbar_input_button("update_artifact", "Update"),
    bslib::toolbar_input_button("clear_artifact", "Clear"),
    bslib::toolbar_input_button("hide_artifact", "Hide"),
    bslib::toolbar_input_button("toggle_artifact", "Toggle")
  ),
  sidebar = FALSE,
  pages = list(
    chat_nav_panel(
      "Inspector",
      tags$h2("Mounted-state inspector"),
      tags$p(
        "Open the artifact, edit its note, visit this page, then return ",
        "to the chat."
      ),
      sidebar = chat_sidebar(
        tags$p("A closed, resizable page-specific sidebar."),
        width = 260,
        open = "closed"
      ),
      toolbar = bslib::toolbar(
        bslib::toolbar_input_button("refresh_artifact", "Refresh artifact")
      )
    )
  ),
  artifact = chat_artifact(
    artifact_content("Initial"),
    title = "Live artifact",
    width = "34rem",
    open = TRUE
  ),
  greeting = "## Artifact controls\n\nUse the toolbar to change this panel.",
  toolbar_input = bslib::toolbar(
    align = "left",
    bslib::toolbar_input_select(
      "model",
      "Model",
      c("GLM 5.2", "Kimi K3", "Claude Sonnet 5", "GPT 5.6 Sol")
    )
  )
)

server <- function(input, output, session) {
  output$artifact_echo <- renderText({
    value <- input$artifact_note
    paste("Bound value:", if (is.null(value)) "" else value)
  })

  observeEvent(input$chat_user_input, {
    chat_append("chat", paste0("You said: ", input$chat_user_input))
  })

  observeEvent(input$show_artifact, {
    chat_artifact_show(
      "chat",
      artifact_content("Shown"),
      title = "Shown artifact"
    )
  })

  observeEvent(input$update_artifact, {
    chat_artifact_update(
      "chat",
      artifact_content("Updated"),
      title = "Updated artifact"
    )
  })

  observeEvent(input$clear_artifact, {
    chat_artifact_update("chat", htmltools::tagList(), title = "")
  })

  observeEvent(input$hide_artifact, {
    chat_artifact_hide("chat")
  })

  observeEvent(input$toggle_artifact, {
    chat_artifact_toggle("chat")
  })

  observeEvent(input$refresh_artifact, {
    chat_artifact_update(
      "chat",
      artifact_content("Inspector refresh"),
      title = "Inspector artifact"
    )
  })
}

shinyApp(ui, server)
