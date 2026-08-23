library(bslib)
library(htmltools)
library(shiny)
library(shinychat)

# Fixture app for testing programmatic navigation visibility:
#   bslib::nav_select(), nav_hide(), nav_show(), and nav_show(select = TRUE)
# on a page_chat() root element. The server wires action buttons to each
# operation so shinytest2 can trigger them and read DOM + Shiny input state.

ui <- page_chat(
  title = "Nav visibility test",
  id = "chat",
  messages = "Welcome!",
  sidebar = chat_sidebar(
    div(id = "home-sidebar", "Home sidebar"),
    history = FALSE,
    open = "open"
  ),
  pages_navbar = list(
    chat_nav_panel(
      "About",
      div(id = "about-page", "About page"),
      value = "about",
      sidebar = FALSE
    ),
    bslib::nav_panel_hidden(
      "secret",
      div(id = "secret-page", "Secret page")
    ),
    bslib::nav_menu(
      "More",
      chat_nav_panel(
        "Nested",
        div(id = "nested-page", "Nested page"),
        value = "nested",
        sidebar = FALSE
      )
    )
  ),
  # A single persistent trigger keeps the header deterministic (replacing the
  # default dark-mode toggle); the nav-driving buttons live in an offcanvas,
  # mirroring the paired navigation example, so they stay reachable while any
  # page is active without crowding the header. The active page value output
  # must stay visible, so it remains in the global toolbar.
  toolbar_global = bslib::toolbar(
    bslib::toolbar_input_button("nav_controls", "Navigation controls"),
    textOutput("page_value", inline = TRUE)
  ),
  artifact_panel = FALSE
)

server <- function(input, output, session) {
  # Render the server-visible input value so tests can assert it.
  output$page_value <- renderText({
    input$chat_page
  })

  observeEvent(input$nav_controls, {
    bslib::show_offcanvas(
      bslib::offcanvas(
        title = "Navigation controls",
        id = "nav_controls_panel",
        placement = "right",
        actionButton("select_about", "Select About"),
        actionButton("select_nested", "Select Nested"),
        actionButton("select_secret", "Select Secret"),
        actionButton("select_home", "Select Home"),
        actionButton("hide_about", "Hide About"),
        actionButton("hide_nested", "Hide Nested"),
        actionButton("show_about", "Show About"),
        actionButton("show_nested", "Show Nested"),
        actionButton("show_secret_select", "Show Secret & Select"),
        actionButton("hide_home", "Hide Home (error)"),
        actionButton("hide_unknown", "Hide Unknown (error)")
      ),
      session = session
    )
  })

  observeEvent(input$select_about, {
    bslib::nav_select("chat_page", "about")
  })

  observeEvent(input$select_nested, {
    bslib::nav_select("chat_page", "nested")
  })

  observeEvent(input$select_secret, {
    bslib::nav_select("chat_page", "secret")
  })

  observeEvent(input$select_home, {
    bslib::nav_select("chat_page", "__home__")
  })

  observeEvent(input$hide_about, {
    bslib::nav_hide("chat_page", "about")
  })

  observeEvent(input$hide_nested, {
    bslib::nav_hide("chat_page", "nested")
  })

  observeEvent(input$show_about, {
    bslib::nav_show("chat_page", "about")
  })

  observeEvent(input$show_nested, {
    bslib::nav_show("chat_page", "nested")
  })

  observeEvent(input$show_secret_select, {
    bslib::nav_show("chat_page", "secret", select = TRUE)
  })

  observeEvent(input$hide_home, {
    bslib::nav_hide("chat_page", "__home__")
  })

  observeEvent(input$hide_unknown, {
    bslib::nav_hide("chat_page", "nonexistent")
  })
}

shinyApp(ui, server)
