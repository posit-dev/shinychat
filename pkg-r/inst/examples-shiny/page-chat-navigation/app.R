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

bs_icon_info_circle_fill <- htmltools::HTML(
  '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-info-circle-fill" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 16A8 8 0 1 0 8 0a8 8 0 0 0 0 16m.93-9.412-1 4.705c-.07.34.029.533.304.533.194 0 .487-.07.686-.246l-.088.416c-.287.346-.92.598-1.465.598-.703 0-1.002-.422-.808-1.319l.738-3.468c.064-.293.006-.399-.287-.47l-.451-.081.082-.381 2.29-.287zM8 5.5a1 1 0 1 1 0-2 1 1 0 0 1 0 2"/></svg>'
)

bs_icon_gear_fill <- htmltools::HTML(
  '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-gear-fill" viewBox="0 0 16 16" aria-hidden="true"><path d="M9.405 1.05c-.413-1.4-2.397-1.4-2.81 0l-.1.34a1.464 1.464 0 0 1-2.105.872l-.32-.16c-1.314-.655-2.74.771-2.084 2.085l.16.32c.38.76.011 1.673-.872 2.105l-.34.1c-1.4.413-1.4 2.397 0 2.81l.34.1c.883.432 1.252 1.345.872 2.105l-.16.32c-.656 1.314.77 2.74 2.084 2.084l.32-.16c.76-.38 1.673-.011 2.105.872l.1.34c.413 1.4 2.397 1.4 2.81 0l.1-.34a1.464 1.464 0 0 1 2.105-.872l.32.16c1.314.656 2.74-.77 2.084-2.084l-.16-.32c-.38-.76-.011-1.673.872-2.105l.34-.1c1.4-.413 1.4-2.397 0-2.81l-.34-.1a1.464 1.464 0 0 1-.872-2.105l.16-.32c.656-1.314-.77-2.74-2.084-2.084l-.32.16a1.464 1.464 0 0 1-2.105-.872zM8 10.93a2.93 2.93 0 1 1 0-5.86 2.93 2.93 0 0 1 0 5.86"/></svg>'
)

ui <- page_chat(
  "Field notes",
  id = "chat",
  toolbar = bslib::toolbar(
    bslib::toolbar_input_button("show_preview", "Show preview")
  ),
  toolbar_global = bslib::toolbar(
    bslib::toolbar_input_button(
      "show_settings",
      "Answer settings",
      icon = bs_icon_gear_fill,
      show_label = FALSE,
      tooltip = "Answer settings"
    ),
    bslib::toolbar_input_button(
      "help",
      "Help",
      icon = bs_icon_info_circle_fill,
      show_label = FALSE,
      tooltip = "Help"
    )
  ),
  sidebar = chat_sidebar(
    tags$h3("Workspace", class = "h6"),
    textInput("project_name", "Project", "Coastal survey"),
    history = TRUE,
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
      "Notebook",
      tags$h2("Observation notebook"),
      tags$p(
        "Capture source notes on the Sources page, then return here to review the fieldwork plan."
      ),
      sidebar = chat_sidebar(
        tags$p("Notebook resources"),
        history = FALSE,
        width = "18rem",
        open = "always",
        resizable = FALSE
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
    width = 420,
    open = FALSE
  ),
  greeting = paste(
    "## Field notes\n",
    "Try the local echo response.\n",
    "* <span class=\"suggestion\">Capture a new field note</span>",
    "* <span class=\"suggestion\">Organize and summarize my notes</span>",
    "* <span class=\"suggestion\">Analyze my notes for recurring observations</span>",
    sep = "\n"
  ),
  placeholder = "Describe what you observed...",
  icon_assistant = FALSE
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
    assistant_text <- paste0(
      "The assistant replied to your message: ",
      user_text
    )
    record_exchange(client, user_text, assistant_text)
    chat_append("chat", assistant_text)
    chat_artifact_update(
      "chat",
      artifact_content(paste("Latest request:", user_text)),
      title = "Latest request"
    )
  })

  observeEvent(input$show_preview, {
    chat_artifact_show("chat", title = "Working preview")
  })

  observeEvent(input$show_settings, {
    bslib::show_offcanvas(
      bslib::offcanvas(
        title = "Answer settings",
        id = "answer_settings",
        placement = "right",
        sliderInput("length", "Target length", 100, 1000, 400),
        checkboxInput("citations", "Request citations", TRUE),
        bslib::input_dark_mode(),
        footer = actionButton("reset_settings", "Reset settings")
      ),
      session = session
    )
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
