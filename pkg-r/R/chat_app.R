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
#'   [ellmer::chat_openai()] and friends. This argument is deprecated in
#'   `chat_mod_ui()` because the client state is now managed by
#'   `chat_mod_server()`.
#' @param ... In `chat_app()`, additional arguments are passed to
#'   [shiny::shinyApp()]. In `chat_mod_ui()`, additional arguments are passed to
#'   [chat_ui()].
#' @param bookmark_store The bookmarking store to use for the app. Passed to
#'   `enable_bookmarking` in [shiny::shinyApp()]. Defaults to `"url"`, which
#'   uses the URL to store the chat state. URL-based bookmarking is limited in
#'   size; use `"server"` to store the state on the server side without size
#'   limitations; or disable bookmarking by setting this to `"disable"`.
#'
#' @returns
#'   * `chat_app()` returns a [shiny::shinyApp()] object.
#'   * `chat_mod_ui()` returns the UI for a shinychat module.
#'   * `chat_mod_server()` includes the shinychat module server logic, and
#'     returns an environment containing:
#'
#'     * `last_input`: A reactive value containing the last user input.
#'     * `last_turn`: A reactive value containing the last assistant turn.
#'     * `update_user_input()`: A function to update the chat input or submit a
#'       new user input. Takes the same arguments as [update_chat_user_input()],
#'       except for `id` and `session`, which are supplied automatically.
#'     * `append()`: A function to append a new message to the chat UI. Takes
#'       the same arguments as [chat_append()], except for `id` and `session`,
#'       which are supplied automatically.
#'     * `clear()`: A function to clear the chat history and the chat UI.
#'       `clear()` takes an optional list of `messages` used to initialize the
#'       chat after clearing. `messages` should be a list of messages, where
#'       each message is a list with `role` and `content` fields. The
#'       `client_history` argument controls how the chat client's history is
#'       updated after clearing. It can be one of: `"clear"` the chat history;
#'       `"set"` the chat history to `messages`; `"append"` `messages` to the
#'       existing chat history; or `"keep"` the existing chat history.
#'     * `status`: A reactive value indicating the current chat interaction
#'       state. Returns `"idle"` when no response is in progress, or
#'       `"streaming"` while a response is actively being received.
#'     * `client`: The current chat client object (an active binding that
#'       always reflects the latest client, even after `set_client()`
#'       is called).
#'     * `set_client(new_client, sync = TRUE)`: Replace the chat client used by
#'       the module. When `sync` is `TRUE` (the default), the new client
#'       inherits conversation turns, system prompt, and tools from the previous
#'       client so the conversation continues seamlessly. Set `sync = FALSE` to
#'       use the new client as-is. If a response is currently streaming, the
#'       swap is deferred until the stream completes. If called multiple times
#'       while streaming, only the most recent new client is used.
#'
#' @describeIn chat_app A simple Shiny app for live chatting. Note that this
#'   app is suitable for interactive use by a single user; do not use
#'   `chat_app()` in a multi-user Shiny app context.
#' @export
chat_app <- function(client, ..., bookmark_store = "url") {
  check_ellmer_chat(client)

  ui <- function(req) {
    bslib::page_fillable(
      chat_mod_ui("chat", height = "100%"),
      shiny::actionButton(
        "close_btn",
        label = "",
        class = "btn-close",
        style = "position: fixed; top: 6px; right: 6px;"
      )
    )
  }

  server <- function(input, output, session) {
    chat_mod_server("chat", client)

    shiny::observeEvent(input$close_btn, label = "on_close_btn", {
      shiny::stopApp()
    })
  }

  shiny::shinyApp(ui, server, ..., enableBookmarking = bookmark_store)
}

check_ellmer_chat <- function(client) {
  if (!inherits(client, "Chat")) {
    abort("`client` must be an `ellmer::Chat` object.")
  }
}

#' @describeIn chat_app A simple chat app module UI.
#' @param id The chat module ID.
#' @param messages Initial messages shown in the chat, used only when `client`
#'   (in `chat_mod_ui()`) doesn't already contain turns. Passed to `messages`
#'   in [chat_ui()].
#' @export
chat_mod_ui <- function(
  id,
  ...,
  client = deprecated(),
  messages = NULL
) {
  if (lifecycle::is_present(client)) {
    lifecycle::deprecate_warn(
      "0.3.0",
      "chat_mod_ui(client = )",
      "chat_mod_server(client = )"
    )
  }

  chat_ui(
    shiny::NS(id, "chat"),
    messages = messages,
    enable_cancel = TRUE,
    ...
  )
}

#' @describeIn chat_app A simple chat app module server.
#' @inheritParams chat_restore
#' @export
chat_mod_server <- function(
  id,
  client,
  bookmark_on_input = TRUE,
  bookmark_on_response = TRUE
) {
  check_ellmer_chat(client)

  append_stream_task <- shiny::ExtendedTask$new(
    function(client, ui_id, user_input, controller = NULL) {
      stream <- client$stream_async(
        user_input,
        stream = "content",
        controller = controller
      )

      p <- promises::promise_resolve(stream)
      promises::then(p, function(stream) {
        chat_append(ui_id, stream)
      })
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

    last_turn <- shiny::reactiveVal(NULL, label = "last_turn")
    last_input <- shiny::reactiveVal(NULL, label = "last_input")
    pending_swap <- shiny::reactiveVal(NULL, label = "pending_swap")
    ctrl <- ellmer::stream_controller()

    swap_client <- function(new_client, sync) {
      if (sync) {
        new_client$set_turns(client$get_turns())
        new_client$set_system_prompt(client$get_system_prompt())
        new_client$set_tools(client$get_tools())
      }
      client <<- new_client
      invisible()
    }

    set_client <- function(new_client, sync = TRUE) {
      check_ellmer_chat(new_client)

      if (append_stream_task$status() == "running") {
        pending_swap(list(client = new_client, sync = sync))
        return(invisible())
      }

      swap_client(new_client, sync)
    }

    shiny::observeEvent(input$chat_user_input, label = "on_chat_user_input", {
      last_input(input$chat_user_input)
      append_stream_task$invoke(
        client,
        "chat",
        input$chat_user_input,
        controller = ctrl
      )
    })

    shiny::observeEvent(input$chat_cancel, label = "on_chat_cancel", {
      ctrl$cancel()
    })

    shiny::observe(label = "on_stream_complete", {
      status <- append_stream_task$status()
      swap <- pending_swap()

      if (status == "success") {
        last_turn(client$last_turn())
      }

      if (!is.null(swap) && status != "running") {
        pending_swap(NULL)
        swap_client(swap$client, swap$sync)
      }
    })

    chat_update_user_input <- function(
      value = NULL,
      ...,
      placeholder = NULL,
      submit = FALSE,
      focus = FALSE
    ) {
      update_chat_user_input(
        "chat",
        value = value,
        placeholder = placeholder,
        submit = submit,
        focus = focus,
        ...,
        session = session
      )
    }

    chat_append_mod <- function(response, role = "assistant", icon = NULL) {
      chat_append("chat", response, role = role, icon = icon, session = session)
    }

    client_clear <- function(
      messages = NULL,
      client_history = c("clear", "set", "append", "keep")
    ) {
      client_history <- arg_match(client_history)

      if (!is.null(messages)) {
        if (rlang::is_string(messages)) {
          # Promote strings to single assistant message
          messages <- list(list(role = "assistant", content = messages))
        }
        if (!rlang::is_list(messages)) {
          cli::cli_abort(
            "{.var messages} must be a list of messages, and each message must be a list with {.field role} and {.field content}."
          )
        }
        if (length(intersect(c("role", "content"), names(messages))) == 2) {
          # Catch the single-message case and promote it to a list of messages
          messages <- list(messages)
        }
      }

      chat_clear("chat", session = session)
      if (!is.null(messages)) {
        for (msg in messages) {
          chat_append("chat", msg$content, role = msg$role, session = session)
        }
      }

      if (client_history == "clear") {
        client$set_turns(list())
      } else if (client_history == "set") {
        client$set_turns(as_ellmer_turns(messages))
      } else if (client_history == "append") {
        turns <- client$get_turns()
        turns <- c(turns, as_ellmer_turns(messages))
        client$set_turns(turns)
      }

      last_turn(NULL)
      last_input(NULL)
    }

    ret <- new.env(parent = emptyenv())
    ret$last_turn <- shiny::reactive(last_turn(), label = "mod_last_turn")
    ret$last_input <- shiny::reactive(last_input(), label = "mod_last_input")
    ret$status <- shiny::reactive(label = "mod_status", {
      if (append_stream_task$status() == "running") "streaming" else "idle"
    })
    makeActiveBinding("client", function() client, ret)
    ret$append <- chat_append_mod
    ret$update_user_input <- chat_update_user_input
    ret$clear <- client_clear
    ret$set_client <- set_client
    lockEnvironment(ret)
    ret
  })
}
