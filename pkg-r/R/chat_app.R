#' Open a live chat application in the browser
#'
#' @description
#' Create a simple Shiny app for live chatting using an [ellmer::Chat] object.
#' Note that these functions will mutate the input `client` object as
#' you chat because your turns will be appended to the history.
#'
#' The app created by `chat_app()` is suitable for interactive use by a single
#' user. For multi-user Shiny apps, use [chat_ui()] and `chat_server()` and be
#' sure to create a new chat client for each user session.
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
#'       chat_ui(
#'         "claude",
#'         messages = list(
#'           "Hi! Use this chat interface to chat with Anthropic's `claude-3-5-sonnet`."
#'         )
#'       )
#'     ),
#'     card(
#'       card_header("Chat with ChatGPT"),
#'       chat_ui(
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
#'   chat_server("claude", claude)
#'   chat_server("openai", openai)
#' }
#'
#' shinyApp(ui, server)
#' }
#'
#' @param client A chat object created by \pkg{ellmer}, e.g.
#'   [ellmer::chat_openai()] and friends. This argument is deprecated in
#'   `chat_mod_ui()` because the client state is now managed by
#'   `chat_server()`.
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
#'   * `chat_server()` includes the shinychat server logic, and
#'     returns an environment containing:
#'
#'     * `last_input`: A reactive value containing the last user input (a string
#'       when attachments are disabled, a list of ellmer `Content` objects when
#'       enabled).
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
#'     * `set_greeting()`: A function to set, stream, or clear the chat
#'       greeting. Pass a [chat_greeting()] object, a plain string, or
#'       `NULL` to clear. Streaming greetings run inside an
#'       [shiny::ExtendedTask] so the session stays responsive; if called
#'       while a greeting is already streaming, the new greeting is queued.
#'       If the greeting has already been dismissed, calling `set_greeting()`
#'       updates the content but does not make it visible again; call
#'       `clear(greeting = TRUE)` first to show a new greeting after dismissal.
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
#'     * `slash_command(name, description, handler, ..., echo, force)`: Register
#'       a slash command. `handler` is required: pass a function (taking 0 or 1
#'       argument), or `NULL` for a client-side command handled in JavaScript via
#'       the `shiny:chat-slash-command` DOM event. A handler that takes one
#'       argument receives a [ContentSlashCommand] object (not a plain string).
#'       See [ContentSlashCommand] for details on how to use this object to
#'       preserve the original command text across bookmarks. `echo` controls
#'       whether invoking the command is echoed as a user message and awaits a
#'       response; it defaults to `TRUE` when a handler is given and `FALSE`
#'       otherwise (set `echo = FALSE` for a handler that only performs side
#'       effects). Returns a function that removes the command. Errors if a
#'       command with the same name is already registered unless
#'       `force = TRUE`.
#'
#' @describeIn chat_app A simple Shiny app for live chatting. Note that this
#'   app is suitable for interactive use by a single user; do not use
#'   `chat_app()` in a multi-user Shiny app context.
#' @inheritParams chat_ui
#' @export
chat_app <- function(
  client,
  ...,
  bookmark_store = "url",
  allow_attachments = TRUE
) {
  check_ellmer_chat(client)

  ui <- function(req) {
    bslib::page_fillable(
      chat_ui(
        "chat",
        height = "100%",
        enable_cancel = TRUE,
        allow_attachments = allow_attachments
      ),
      if (rlang::is_interactive()) {
        shiny::actionButton(
          "close_btn",
          label = "",
          class = "btn-close",
          style = "position: fixed; top: 6px; right: 6px;"
        )
      }
    )
  }

  server <- function(input, output, session) {
    if (rlang::is_interactive()) {
      shiny::setBookmarkExclude("close_btn")
      shiny::observeEvent(input$close_btn, label = "on_close_btn", {
        shiny::stopApp()
      })
    }
    chat_server("chat", client)
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
#' @inheritParams chat_ui
#' @export
chat_mod_ui <- function(
  id,
  ...,
  client = deprecated(),
  messages = NULL,
  allow_attachments = TRUE
) {
  lifecycle::deprecate_soft(
    "0.5.0",
    "chat_mod_ui()",
    details = "Use `chat_ui(NS(id, \"chat\"), ...)` in your module UI instead."
  )

  if (lifecycle::is_present(client)) {
    lifecycle::deprecate_warn(
      "0.3.0",
      "chat_mod_ui(client = )",
      "chat_server(client = )"
    )
  }

  chat_ui(
    shiny::NS(id, "chat"),
    messages = messages,
    enable_cancel = TRUE,
    `effective-id` = id,
    allow_attachments = allow_attachments,
    ...
  )
}

#' @describeIn chat_app Wire up batteries-included chat server logic in a Shiny session.
#' @inheritParams chat_restore
#' @param session The Shiny session. Defaults to the current reactive domain.
#' @param greeting Optional greeting to set when the module initializes.
#'   Accepts a static value (string, [htmltools::HTML()], [htmltools::tagList()],
#'   or [chat_greeting()]) or a **function** that generates the greeting
#'   dynamically. See the **Greeting** section below for details.
#'
#' @section Greeting:
#'
#' When `greeting` is a **function**, it is called each time the
#' `greeting_requested` event fires — on first view when the chat is empty,
#' and again after `clear(greeting = TRUE)`. The function should return a
#' [chat_greeting()] (typically wrapping a stream). Static values (strings,
#' [chat_greeting()] objects) are set once at init and do not regenerate.
#'
#' The function signature determines what is passed. Currently the only
#' recognized argument is `client`.
#'
#' **`function(client)`** (recommended). A clone of the `client` with its turn
#' history wiped is passed as `client`. This avoids manually creating and
#' configuring a separate client:
#'
#' ```r
#' chat_server("chat", client, greeting = function(client) {
#'   stream <- client$stream_async("Generate a short welcome message.")
#'   chat_greeting(stream)
#' })
#' ```
#'
#' **`function()`** (zero arguments). You create and manage your own client:
#'
#' ```r
#' chat_server("chat", client, greeting = function() {
#'   greeter <- ellmer::chat_openai(model = "gpt-4o")
#'   stream <- greeter$stream_async("Generate a short welcome message.")
#'   chat_greeting(stream)
#' })
#' ```
#'
#' **Static value.** Set once; does not regenerate after `clear()`:
#'
#' ```r
#' chat_server("chat", client, greeting = "## Welcome!\n\nHow can I help?")
#' ```
#'
#' The returned `set_greeting()` helper is available for cases where you need
#' to set a greeting outside the greeting lifecycle.
#'
#' @importFrom shiny isolate
#' @export
chat_server <- function(
  id,
  client,
  greeting = NULL,
  bookmark_on_input = TRUE,
  bookmark_on_response = TRUE,
  session = shiny::getDefaultReactiveDomain()
) {
  check_ellmer_chat(client)

  append_stream_task <- shiny::ExtendedTask$new(
    function(client, ui_id, user_input, controller = NULL) {
      stream <- client$stream_async(
        !!!user_input,
        stream = "content",
        controller = controller
      )

      p <- promises::promise_resolve(stream)
      promises::then(p, function(stream) {
        chat_append(ui_id, stream)
      })
    }
  )

  greeting_stream_task <- shiny::ExtendedTask$new(
    function(ui_id, greeting, session) {
      result <- chat_set_greeting(ui_id, greeting, session = session)
      if (is.null(result)) {
        promises::promise_resolve(NULL)
      } else {
        result
      }
    }
  )

  cancel_bookmarks <- chat_restore(
    id,
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
    cancel_bookmarks()
    cancel_bookmarks <<- chat_restore(
      id,
      client,
      session = session,
      bookmark_on_input = bookmark_on_input,
      bookmark_on_response = bookmark_on_response,
      restore_ui = FALSE
    )
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

  shiny::observeEvent(
    session$input[[paste0(id, "_user_input")]],
    label = "on_chat_user_input",
    {
      last_input(session$input[[paste0(id, "_user_input")]])
      append_stream_task$invoke(
        client,
        id,
        session$input[[paste0(id, "_user_input")]],
        controller = ctrl
      )
    }
  )

  shiny::observeEvent(
    session$input[[paste0(id, "_cancel")]],
    label = "on_chat_cancel",
    {
      ctrl$cancel()
    }
  )

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
    focus = FALSE,
    attachments = NULL,
    attachment_mode = c("append", "set")
  ) {
    update_chat_user_input(
      id,
      value = value,
      placeholder = placeholder,
      submit = submit,
      focus = focus,
      attachments = attachments,
      attachment_mode = attachment_mode,
      ...,
      session = session
    )
  }

  chat_append_mod <- function(response, role = "assistant", icon = NULL) {
    chat_append(id, response, role = role, icon = icon, session = session)
  }

  set_greeting_mod <- function(greeting) {
    greeting_stream_task$invoke(id, greeting, session)
  }

  if (is.function(greeting)) {
    greeting_fmls <- names(formals(greeting))

    shiny::observeEvent(
      session$input[[paste0(id, "_greeting_requested")]],
      label = "on_greeting_requested",
      {
        args <- list()
        if ("client" %in% greeting_fmls) {
          greeter <- client$clone()
          greeter$set_turns(list())
          args$client <- greeter
        }
        greeting_stream_task$invoke(
          id,
          do.call(greeting, args),
          session
        )
      }
    )
  } else if (!is.null(greeting)) {
    set_greeting_mod(greeting)
  }

  send_chat_action(
    id,
    list(type = "update_cancel", enable_cancel = TRUE),
    session = session
  )
  send_chat_action(
    id,
    list(type = "update_upload", enable_upload = TRUE),
    session = session
  )

  # Registered slash commands. Each entry: list(handler, takes_args, definition).
  # Using a reactiveVal lets multiple registrations during app startup coalesce
  # into a single client sync on the next flush. Starts as NULL so the sync
  # observer skips the redundant initial send (the client already initializes
  # to []); an empty list is sent when the last command is removed.
  slash_commands <- shiny::reactiveVal(NULL, label = "slash_commands")

  shiny::observeEvent(
    session$input[[paste0(id, "_slash_command")]],
    label = "on_chat_slash_command",
    {
      data <- session$input[[paste0(id, "_slash_command")]]
      reg <- isolate(slash_commands())[[data$command]]
      if (!is.null(reg) && is.function(reg$handler)) {
        tryCatch(
          {
            if (isTRUE(reg$takes_args)) {
              user_text <- data$userText %||% ""
              content <- ContentSlashCommand(
                command = data$command,
                user_text = user_text,
                text = paste0(
                  sprintf(
                    "The user entered the /%s slash command",
                    data$command
                  ),
                  if (nzchar(user_text)) {
                    paste0(" with arguments: ", user_text)
                  } else {
                    "."
                  }
                )
              )
              reg$handler(content)
            } else {
              reg$handler()
            }
          },
          error = function(e) {
            shiny::showNotification(
              sanitized_error_message(e),
              type = "error",
              duration = NULL
            )
            rlang::warn(
              sprintf("Error in slash command '/%s'", data$command),
              parent = e
            )
          }
        )
      }
      send_chat_action(
        id,
        list(type = "remove_loading"),
        session = session
      )
    }
  )

  shiny::observe(label = "sync_slash_commands", {
    cmds <- slash_commands()
    if (!is.null(cmds)) {
      defs <- lapply(cmds, `[[`, "definition")
      send_chat_action(
        id,
        list(type = "update_slash_commands", commands = unname(defs)),
        session = session
      )
    }
  })

  # TODO: Support a standalone register_slash_command() that works outside the
  # returned environment (e.g., so callers don't have to thread the return value)
  slash_command_method <- function(
    name,
    description,
    handler,
    ...,
    echo = NULL,
    force = FALSE
  ) {
    rlang::check_dots_empty()
    if (!is.character(name) || length(name) != 1) {
      cli::cli_abort("{.arg name} must be a single string.")
    }
    if (!grepl("^[a-zA-Z0-9_-]+$", name)) {
      cli::cli_abort(
        "{.arg name} must contain only alphanumeric characters, underscores, or hyphens, got {.val {name}}."
      )
    }
    if (!is.character(description) || length(description) != 1) {
      cli::cli_abort("{.arg description} must be a single string.")
    }
    if (!is.null(handler) && !is.function(handler)) {
      cli::cli_abort("{.arg handler} must be a function or {.code NULL}.")
    }

    takes_args <- FALSE
    if (is.function(handler)) {
      handler_args <- names(formals(handler))
      if (length(handler_args) > 1 || identical(handler_args, "...")) {
        cli::cli_abort("{.arg handler} must take 0 or 1 argument.")
      }
      takes_args <- length(handler_args) > 0
    }

    cmds <- isolate(slash_commands()) %||% list()

    if (!force && name %in% names(cmds)) {
      cli::cli_abort(
        "Slash command {.val {name}} is already registered. Use {.code force = TRUE} to overwrite it."
      )
    }

    resolved_echo <- if (is.null(echo)) !is.null(handler) else isTRUE(echo)

    cmds[[name]] <- list(
      handler = handler,
      takes_args = takes_args,
      definition = list(
        name = name,
        description = description,
        echo = resolved_echo
      )
    )
    slash_commands(cmds)

    function() {
      cmds <- isolate(slash_commands())
      cmds[[name]] <- NULL
      slash_commands(cmds)
    }
  }

  client_clear <- function(
    messages = NULL,
    greeting = FALSE,
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

    chat_clear(id, greeting = greeting, session = session)
    if (!is.null(messages)) {
      for (msg in messages) {
        chat_append(id, msg$content, role = msg$role, session = session)
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
  ret$set_greeting <- set_greeting_mod
  ret$set_client <- set_client
  ret$slash_command <- slash_command_method
  lockEnvironment(ret)
  ret
}

#' @describeIn chat_app A Shiny module server for chat (deprecated).
#' @export
chat_mod_server <- function(
  id,
  client,
  greeting = NULL,
  bookmark_on_input = TRUE,
  bookmark_on_response = TRUE
) {
  lifecycle::deprecate_soft("0.5.0", "chat_mod_server()", "chat_server()")
  check_ellmer_chat(client)
  shiny::moduleServer(id, function(input, output, session) {
    chat_server(
      "chat",
      client,
      greeting = greeting,
      bookmark_on_input = bookmark_on_input,
      bookmark_on_response = bookmark_on_response,
      session = session
    )
  })
}
