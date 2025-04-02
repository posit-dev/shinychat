#' Open a live chat application in the browser
#'
#' @description
#' Create a simple Shiny app for live chatting using an [ellmer::Chat] object.
#' Note that these functions will mutate the input `client` object as
#' you chat because your turns will be appended to the history.
#'
#' @examples
#' \dontrun{
#' client <- ellmer::chat_claude()
#' chat_app(client)
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
    chat_mod_ui("chat", client, height = "100%"),
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
#' @export
chat_mod_ui <- function(id, client, ...) {
  check_ellmer_chat(client)

  messages <- map(client$get_turns(), function(turn) {
    content <- ellmer::contents_markdown(turn)
    if (is.null(content) || identical(content, "")) {
      return(NULL)
    }
    list(role = turn@role, content = content)
  })
  messages <- compact(messages)

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
      stream <- client$stream_async(user_input)
      chat_append(ui_id, stream)
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
  })
}
