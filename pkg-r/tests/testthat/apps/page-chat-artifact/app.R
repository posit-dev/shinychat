library(bslib)
library(htmltools)
library(shiny)
library(shinychat)

artifact_dependency <- htmlDependency(
  name = "page-chat-artifact-browser-test",
  version = "1.0.0",
  src = c(file = "assets"),
  stylesheet = "artifact.css"
)

artifact_content <- function(version, dependency = TRUE) {
  tagList(
    if (dependency) artifact_dependency,
    div(
      class = "artifact-dependency-marker",
      p(class = "artifact-content-label", paste(version, "content")),
      textInput(
        "artifact_text",
        "Artifact value",
        value = version
      ),
      textOutput("artifact_echo")
    )
  )
}

ui <- page_chat(
  title = "Page chat browser test",
  id = "chat",
  toolbar = tagList(
    actionButton("show_artifact", "Show artifact"),
    actionButton("update_artifact", "Update artifact"),
    actionButton("hide_artifact", "Hide artifact"),
    actionButton("toggle_artifact", "Toggle artifact"),
    actionButton("show_preserved", "Show preserved")
  ),
  sidebar = chat_sidebar(
    div(id = "home-sidebar", "Home sidebar"),
    history = FALSE,
    width = 280,
    open = "open"
  ),
  pages = list(
    chat_nav_panel(
      "About",
      div(id = "about-page", "About page"),
      value = "about",
      sidebar = FALSE
    ),
    chat_nav_panel(
      "Settings",
      div(id = "settings-page", "Settings page"),
      value = "settings",
      sidebar = chat_sidebar(
        div(id = "settings-sidebar", "Settings sidebar"),
        history = FALSE,
        width = 320,
        open = "closed"
      )
    )
  ),
  artifact = chat_artifact(
    artifact_content("Initial", dependency = FALSE),
    title = "Initial artifact",
    open = FALSE
  )
)

server <- function(input, output, session) {
  output$artifact_echo <- renderText({
    value <- input$artifact_text
    paste0("Echo: ", if (is.null(value)) "" else value)
  })

  observeEvent(input$show_artifact, {
    chat_artifact_show(
      "chat",
      content = artifact_content("Initial"),
      title = "Initial artifact",
      session = session
    )
  })

  observeEvent(input$update_artifact, {
    chat_artifact_update(
      "chat",
      content = artifact_content("Updated"),
      title = "Updated artifact",
      session = session
    )
  })

  observeEvent(input$hide_artifact, {
    chat_artifact_hide("chat", session = session)
  })

  observeEvent(input$toggle_artifact, {
    chat_artifact_toggle("chat", session = session)
  })

  observeEvent(input$show_preserved, {
    chat_artifact_show("chat", session = session)
  })
}

shinyApp(ui, server)
