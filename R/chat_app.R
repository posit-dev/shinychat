#' Open a live chat application in the browser
#'
#' @description
#' Create a simple Shiny app for live chatting using an [ellmer::Chat] object.
#' Note that these functions will mutate the input `chat` object as
#' you chat because your turns will be appended to the history.
#'
#' @examples
#' \dontrun{
#' chat <- ellmer::chat_claude()
#' chat_app(chat)
#' }
#'
#' @param chat A chat object created by \pkg{ellmer}, e.g.
#'   [ellmer::chat_openai()] and friends.
#' @inheritDotParams shiny::shinyApp -ui -server
#'
#' @returns A [shiny::shinyApp()] object.
#'
#' @export
chat_app <- function(chat, ...) {
  if (!inherits(chat, "Chat")) {
    abort("`chat` must be an `ellmer::Chat` object.")
  }

  messages <- map(chat$get_turns(), function(turn) {
    content <- ellmer::contents_markdown(turn)
    if (is.null(content) || identical(content, "")) {
      return(NULL)
    }
    list(role = turn@role, content = content)
  })
  messages <- compact(messages)

  ui <- bslib::page_fillable(
    shinychat::chat_ui(
      "chat",
      height = "100%",
      messages = messages
    ),
    shiny::actionButton(
      "close_btn",
      label = "",
      class = "btn-close",
      style = "position: fixed; top: 6px; right: 6px;"
    )
  )

  server <- function(input, output, session) {
    shiny::observeEvent(input$chat_user_input, {
      stream <- chat$stream_async(input$chat_user_input)
      shinychat::chat_append("chat", stream)
    })

    shiny::observeEvent(input$close_btn, {
      shiny::stopApp()
    })

    shiny::observeEvent(input$close_btn, {
      shiny::stopApp()
    })
  }

  shiny::shinyApp(ui, server, ...)
}
