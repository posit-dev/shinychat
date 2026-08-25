library(shiny)
library(shinychat)

drawer_content <- function(version) {
  tags$section(
    tags$p(tags$strong(version), " content with a live Shiny binding."),
    textInput("drawer_note", "Drawer note", paste(version, "draft")),
    verbatimTextOutput("drawer_echo")
  )
}

ui <- page_chat(
  "Drawer controls",
  id = "chat",
  toolbar = bslib::toolbar(
    bslib::toolbar_input_button("show_drawer", "Show"),
    bslib::toolbar_input_button("update_drawer", "Update"),
    bslib::toolbar_input_button("clear_drawer", "Clear"),
    bslib::toolbar_input_button("hide_drawer", "Hide"),
    bslib::toolbar_input_button("toggle_drawer", "Toggle")
  ),
  sidebar = FALSE,
  pages_navbar = list(
    chat_nav_panel(
      "Inspector",
      tags$h2("Mounted-state inspector"),
      tags$p(
        "Open the drawer, edit its note, visit this page, then return ",
        "to the chat."
      ),
      sidebar = chat_sidebar(
        tags$p("A closed, resizable page-specific sidebar."),
        width = 260,
        open = "closed"
      ),
      toolbar = bslib::toolbar(
        bslib::toolbar_input_button("refresh_drawer", "Refresh drawer")
      )
    )
  ),
  drawer = chat_drawer(
    drawer_content("Initial"),
    title = "Live drawer",
    width = "34rem",
    open = TRUE
  ),
  greeting = "## Drawer controls\n\nUse the toolbar to change this panel."
)

server <- function(input, output, session) {
  output$drawer_echo <- renderText({
    value <- input$drawer_note
    paste("Bound value:", if (is.null(value)) "" else value)
  })

  observeEvent(input$chat_user_input, {
    chat_append("chat", paste0("You said: ", input$chat_user_input))
  })

  observeEvent(input$show_drawer, {
    chat_drawer_show(
      "chat",
      drawer_content("Shown"),
      title = "Shown drawer"
    )
  })

  observeEvent(input$update_drawer, {
    chat_drawer_update(
      "chat",
      drawer_content("Updated"),
      title = "Updated drawer"
    )
  })

  observeEvent(input$clear_drawer, {
    chat_drawer_update("chat", htmltools::tagList(), title = "")
  })

  observeEvent(input$hide_drawer, {
    chat_drawer_hide("chat")
  })

  observeEvent(input$toggle_drawer, {
    chat_drawer_toggle("chat")
  })

  observeEvent(input$refresh_drawer, {
    chat_drawer_update(
      "chat",
      drawer_content("Inspector refresh"),
      title = "Inspector drawer"
    )
  })
}

shinyApp(ui, server)
