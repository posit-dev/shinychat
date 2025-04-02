#' Open a live chat application in the browser
#'
#' @description
#' Create a simple Shiny app for live chatting using an [ellmer::Chat] object.
#' Note that these functions will mutate the input `client` object as
#' you chat because your turns will be appended to the history.
#'
#' @examples
#' \dontrun{
#' # Interactive in the console ----
#' client <- ellmer::chat_claude()
#' chat_app(client)
#'
#' # Inside a Shiny app ----
#' library(shiny)
#' library(bslib)
#' library(shinychat)
#'
#' ui <- page_navbar(
#'   title = "shinychat",
#'
#'   nav_panel(
#'     "Claude",
#'     h2("Chat with Claude"),
#'     chat_mod_ui(
#'       "claude",
#'       messages = list(
#'         "Hi! Use this chat interface to chat with Anthropic's `claude-3-5-sonnet`."
#'       )
#'     )
#'   ),
#'
#'   nav_panel(
#'     "ChatGPT",
#'     h2("Chat with ChatGPT"),
#'     chat_mod_ui(
#'       "openai",
#'       messages = list(
#'         "Hi! Use this chat interface to chat with OpenAI's `gpt-4o`."
#'       )
#'     )
#'   )
#' )
#'
#' server <- function(input, output, session) {
#'   claude <- ellmer::chat_claude(model = "claude-3-5-sonnet-latest") # Requires ANTHROPIC_API_KEY
#'   openai <- ellmer::chat_openai(model = "gpt-4o") # Requires OPENAI_API_KEY
#'
#'   chat_mod_server("claude", claude)
#'   chat_mod_server("openai", openai)
#' }
#'
#' shinyApp(ui, server)
#' }
#'
#' @param client A chat object created by \pkg{ellmer}, e.g.
#'   [ellmer::chat_openai()] and friends.
#' @param ... In `chat_app()`, additional arguments are passed to
#'   [shiny::shinyApp()]. In `chat_mod_ui()`, additional arguments are passed to
#'   [chat_ui()].
#'
#' @returns A [shiny::shinyApp()] object.
#'
#' @describeIn chat_app A simple Shiny app for live chatting.
#' @export
chat_app <- function(client, ...) {
  check_ellmer_chat(client)

  ui <- bslib::page_fillable(
    chat_mod_ui("chat", client = client, height = "100%"),
    shiny::actionButton(
      "close_btn",
      label = "",
      class = "btn-close",
      style = "position: fixed; top: 6px; right: 6px;"
    )
  )

  server <- function(input, output, session) {
    chat_mod_server("chat", client)

    shiny::observeEvent(input$close_btn, {
      shiny::stopApp()
    })
  }

  shiny::shinyApp(ui, server, ...)
}

check_ellmer_chat <- function(client) {
  if (!inherits(client, "Chat")) {
    abort("`client` must be an `ellmer::Chat` object.")
  }
}

#' @describeIn chat_app A simple chat app module UI.
#' @param id The chat module ID.
#' @param messages Initial messages shown in the chat, used when `client` is not
#'   provided or when the chat `client` doesn't already contain turns. Passed to
#'   `messages` in [chat_ui()].
#' @export
chat_mod_ui <- function(id, ..., client = NULL, messages = NULL) {
  if (!is.null(client)) {
    check_ellmer_chat(client)

    client_msgs <- map(client$get_turns(), function(turn) {
      content <- ellmer::contents_markdown(turn)
      if (is.null(content) || identical(content, "")) {
        return(NULL)
      }
      list(role = turn@role, content = content)
    })
    client_msgs <- compact(client_msgs)

    if (length(client_msgs)) {
      if (!is.null(messages)) {
        warn(
          "`client` was provided and has initial messages, `messages` will be ignored."
        )
      }
      messages <- client_msgs
    }
  }

  shinychat::chat_ui(
    shiny::NS(id, "chat"),
    messages = messages,
    ...
  )
}

#' @describeIn chat_app A simple chat app module server.
#' @export
chat_mod_server <- function(id, client) {
  check_ellmer_chat(client)

  append_stream_task <- shiny::ExtendedTask$new(
    function(client, ui_id, user_input) {
      promises::future_promise({
        stream <- client$stream_async(user_input)
        chat_append(ui_id, stream)
      })
    }
  )

  shiny::moduleServer(id, function(input, output, session) {
    shiny::observeEvent(input$chat_user_input, {
      append_stream_task$invoke(
        client,
        session$ns("chat"),
        input$chat_user_input
      )
    })

    shiny::observe({
      if (append_stream_task$status() == "error") {
        tryCatch(
          append_stream_task$result(),
          error = notify_error(session$ns("chat"), session)
        )
      }
    })
  })
}

notify_error <- function(id, session = shiny::getDefaultReactiveDomain()) {
  function(err) {
    needs_sanitized <-
      isTRUE(getOption("shiny.sanitize.errors")) &&
      !inherits(err, "shiny.custom.error")
    if (needs_sanitized) {
      msg <- "**An error occurred.** Please try again or contact the app author."
    } else {
      msg <- sprintf(
        "**An error occurred:**\n\n```\n%s\n```",
        conditionMessage(err)
      )
    }

    chat_append_message(
      id,
      msg = list(role = "assistant", content = msg),
      chunk = TRUE,
      operation = "append",
      session = session
    )
    chat_append_message(
      id,
      list(role = "assistant", content = ""),
      chunk = "end",
      operation = "append",
      session = session
    )
  }
}
