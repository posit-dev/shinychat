library(bslib)
library(htmltools)
library(shiny)
library(shinychat)

drawer_dependency <- htmlDependency(
  name = "page-chat-drawer-browser-test",
  version = "1.0.0",
  src = c(file = "assets"),
  stylesheet = "drawer.css"
)

drawer_content <- function(version, dependency = TRUE) {
  tagList(
    if (dependency) drawer_dependency,
    div(
      class = "drawer-dependency-marker",
      p(class = "drawer-content-label", paste(version, "content")),
      textInput(
        "drawer_text",
        "Drawer value",
        value = version
      ),
      textOutput("drawer_echo")
    )
  )
}

ui <- page_chat(
  title = "Page chat browser test",
  id = "chat",
  toolbar = tagList(
    actionButton("show_drawer", "Show drawer"),
    actionButton("update_drawer", "Update drawer"),
    actionButton("hide_drawer", "Hide drawer"),
    actionButton("toggle_drawer", "Toggle drawer"),
    actionButton("show_preserved", "Show preserved"),
    textInput("home_toolbar", "Home toolbar", value = "home toolbar initial")
  ),
  sidebar = chat_sidebar(
    div(id = "home-sidebar", "Home sidebar"),
    history = FALSE,
    width = 280,
    open = "open"
  ),
  pages_navbar = list(
    chat_nav_panel(
      "About",
      div(id = "about-page", "About page"),
      value = "about",
      sidebar = FALSE,
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
      ),
      toolbar = textInput(
        "settings_toolbar",
        "Settings toolbar",
        value = "settings toolbar initial"
      )
    ),
    chat_nav_panel(
      "Empty",
      div(id = "empty-page", "Empty page"),
      value = "empty",
      sidebar = FALSE
    )
  ),
  drawer = chat_drawer(
    drawer_content("Initial", dependency = FALSE),
    title = "Initial drawer",
    open = FALSE
  )
)

server <- function(input, output, session) {
  output$drawer_echo <- renderText({
    value <- input$drawer_text
    paste0("Echo: ", if (is.null(value)) "" else value)
  })

  observeEvent(input$show_drawer, {
    chat_drawer_show(
      "chat",
      content = drawer_content("Initial"),
      title = "Initial drawer",
      session = session
    )
  })

  observeEvent(input$update_drawer, {
    chat_drawer_update(
      "chat",
      content = drawer_content("Updated"),
      title = "Updated drawer",
      session = session
    )
  })

  observeEvent(input$hide_drawer, {
    chat_drawer_hide("chat", session = session)
  })

  observeEvent(input$toggle_drawer, {
    chat_drawer_toggle("chat", session = session)
  })

  observeEvent(input$show_preserved, {
    chat_drawer_show("chat", session = session)
  })
}

shinyApp(ui, server)
