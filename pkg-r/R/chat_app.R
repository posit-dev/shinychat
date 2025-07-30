#' Open a live chat application in the browser
#'
#' @description
#' Create a simple Shiny app for live chatting using an [ellmer::Chat] object.
#' Note that these functions will mutate the input `client` object as
#' you chat because your turns will be appended to the history.
#'
#' The app created by `chat_app()` is suitable for interactive use by a single
#' user. For multi-user Shiny apps, use the Shiny module chat functions --
#' `chat_mod_ui()` and `chat_mod_server()` -- and be sure to create a new chat
#' client for each user session.
#'
#' @examples
#' \dontrun{
#' # Interactive in the console ----
#' client <- ellmer::chat_anthropic()
#' chat_app(client)
#'
#' # Inside a Shiny app ----
#' library(shiny)
#' library(bslib)
#' library(shinychat)
#'
#' ui <- page_fillable(
#'   titlePanel("shinychat example"),
#'
#'   layout_columns(
#'     card(
#'       card_header("Chat with Claude"),
#'       chat_mod_ui(
#'         "claude",
#'         messages = list(
#'           "Hi! Use this chat interface to chat with Anthropic's `claude-3-5-sonnet`."
#'         )
#'       )
#'     ),
#'     card(
#'       card_header("Chat with ChatGPT"),
#'       chat_mod_ui(
#'         "openai",
#'         messages = list(
#'           "Hi! Use this chat interface to chat with OpenAI's `gpt-4o`."
#'         )
#'       )
#'     )
#'   )
#' )
#'
#' server <- function(input, output, session) {
#'   claude <- ellmer::chat_anthropic(model = "claude-3-5-sonnet-latest") # Requires ANTHROPIC_API_KEY
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
#' @returns
#'   * `chat_app()` returns a [shiny::shinyApp()] object.
#'   * `chat_mod_ui()` returns the UI for a shinychat module.
#'   * `chat_mod_server()` includes the shinychat module server logic, and
#'     and returns the last turn upon successful chat completion.
#'
#' @describeIn chat_app A simple Shiny app for live chatting. Note that this
#'   app is suitable for interactive use by a single user; do not use
#'   `chat_app()` in a multi-user Shiny app context.
#' @export
chat_app <- function(client, ...) {
  check_ellmer_chat(client)

  ui <- function(req) {
    bslib::page_fillable(
      chat_mod_ui("chat", client = client, height = "100%"),
      shiny::actionButton(
        "close_btn",
        label = "",
        class = "btn-close",
        style = "position: fixed; top: 6px; right: 6px;"
      )
    )
  }

  shiny::enableBookmarking("url")

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
chat_mod_ui <- function(
  id,
  ...,
  client = lifecycle::deprecated(),
  messages = NULL
) {
  chat_ui(
    shiny::NS(id, "chat"),
    messages = messages,
    ...
  )
}

#' @describeIn chat_app A simple chat app module server.
#' @export
chat_mod_server <- function(
  id,
  client,
  bookmark_on_input = TRUE,
  bookmark_on_response = TRUE
) {
  check_ellmer_chat(client)

  append_stream_task <- shiny::ExtendedTask$new(
    function(client, ui_id, user_input) {
      promises::then(
        promises::promise_resolve(client$stream_async(user_input)),
        function(stream) {
          chat_append(ui_id, stream)
        }
      )
    }
  )

  shiny::moduleServer(id, function(input, output, session) {
    chat_restore(
      "chat",
      client,
      session = session,
      bookmark_on_input = bookmark_on_input,
      bookmark_on_response = bookmark_on_response
    )

    shiny::observeEvent(input$chat_user_input, {
      append_stream_task$invoke(
        client,
        "chat",
        input$chat_user_input
      )
    })

    shiny::reactive({
      if (append_stream_task$status() == "success") {
        client$last_turn()
      }
    })
  })
}
