library(shiny)
library(shinychat)
library(ellmer)

setClass(
  "PageChatEchoProvider",
  representation(name = "character", model = "character")
)

make_echo_client <- function() {
  stored_turns <- list()
  client <- list(
    get_turns = function() stored_turns,
    set_turns = function(value) {
      stored_turns <<- value
      invisible(client)
    },
    get_tools = function() list(),
    get_provider = function() {
      methods::new(
        "PageChatEchoProvider",
        name = "Local echo",
        model = "local-echo"
      )
    },
    get_model = function() "local-echo",
    clone = function() make_echo_client()
  )
  class(client) <- c("Chat", "R6")
  client
}

record_exchange <- function(client, user_text, assistant_text) {
  client$set_turns(c(
    client$get_turns(),
    list(
      UserTurn(contents = list(ContentText(user_text))),
      AssistantTurn(contents = list(ContentText(assistant_text)))
    )
  ))
}

artifact_content <- function(label) {
  tags$section(
    tags$h3("Preview"),
    tags$p(label)
  )
}

ui <- page_chat(
  "Field notes",
  id = "chat",
  toolbar = bslib::toolbar(
    bslib::toolbar_input_button("clear_chat", "Clear conversation"),
    bslib::toolbar_input_button("show_preview", "Show preview")
  ),
  toolbar_global = bslib::toolbar(
    bslib::toolbar_input_button("help", "Help")
  ),
  sidebar = chat_sidebar(
    tags$h3("Workspace", class = "h6"),
    textInput("project_name", "Project", "Coastal survey"),
    # history = TRUE,
    width = 320,
    open = "auto"
  ),
  pages = list(
    chat_nav_panel(
      "Sources",
      tags$h2("Source checklist"),
      checkboxGroupInput(
        "sources",
        "Include in the analysis",
        c("Field observations", "Published research", "Local guidance"),
        selected = c("Field observations", "Published research")
      ),
      sidebar = TRUE,
      # Compatibility alias: reuse the home-page toolbar here.
      toolbar = TRUE
    ),
    chat_nav_panel(
      "Settings",
      tags$h2("Answer settings"),
      sliderInput("length", "Target length", 100, 1000, 400),
      checkboxInput("citations", "Request citations", TRUE),
      sidebar = chat_sidebar(
        tags$p("This page has a fixed, page-specific sidebar."),
        history = FALSE,
        width = "18rem",
        open = "always",
        resizable = FALSE
      ),
      toolbar = bslib::toolbar(
        bslib::toolbar_input_button("reset_settings", "Reset settings")
      )
    ),
    chat_nav_panel(
      "About",
      tags$h2("About this example"),
      tags$p(
        "This page has no page-scoped toolbar and no page-specific sidebar."
      ),
      sidebar = FALSE,
      toolbar = NULL
    )
  ),
  artifact = chat_artifact(
    artifact_content("Use the home toolbar to open this preview."),
    title = "Working preview",
    width = 420
  ),
  greeting = "## Field notes\n\nTry the local echo response.",
  placeholder = "Describe what you observed..."
)

server <- function(input, output, session) {
  client <- make_echo_client()
  chat_enable_history(
    "chat",
    client,
    options = history_options(store = "memory", title = NULL)
  )

  observeEvent(input$chat_user_input, {
    user_text <- if (is.list(input$chat_user_input)) {
      input$chat_user_input[[1]]
    } else {
      input$chat_user_input
    }
    assistant_text <- paste0("You said: ", user_text)
    record_exchange(client, user_text, assistant_text)
    chat_append("chat", assistant_text)
    chat_artifact_update(
      "chat",
      artifact_content(paste("Latest request:", user_text)),
      title = "Latest request"
    )
  })

  observeEvent(input$clear_chat, {
    chat_clear("chat", greeting = TRUE)
  })

  observeEvent(input$show_preview, {
    chat_artifact_show("chat", title = "Working preview")
  })

  observeEvent(input$reset_settings, {
    updateSliderInput(session, "length", value = 400)
    updateCheckboxInput(session, "citations", value = TRUE)
  })

  observeEvent(input$help, {
    bslib::show_toast(
      bslib::toast(
        "The Help control is global and remains available on every page.",
        header = "Help",
        type = "info"
      )
    )
  })
}

shinyApp(ui, server)
