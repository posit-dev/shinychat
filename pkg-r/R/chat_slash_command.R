#' Register a slash command
#'
#' @description
#' Add a command to a [chat_ui()]'s slash-command palette. Typing `/` in the
#' chat input opens the palette; picking a command runs its `handler` on the
#' server.
#'
#' `chat_slash_command()` works with or without [chat_server()]. Use it when you
#' drive [chat_ui()] with your own server logic (for example, a backend that
#' isn't an ellmer client), or when you'd rather not pass the value returned by
#' `chat_server()` around. Commands registered here and through
#' `chat_server()`'s `$slash_command()` method share one palette per chat.
#'
#' @param id The ID of the chat element.
#' @param name The command name, without the leading `/`. May contain only
#'   letters, numbers, underscores, and hyphens.
#' @param description Text shown next to the command in the palette.
#' @param handler What to run when the command is invoked:
#'
#'   * A function with no arguments, called for its side effects.
#'   * A function with one argument, which receives a [ContentSlashCommand]
#'     object describing the invocation.
#'   * `NULL` for a command handled entirely in the browser via the cancelable
#'     `shiny:chat-slash-command` DOM event.
#'
#'   If the handler returns a promise, the chat stays in its loading state
#'   until the promise settles.
#' @param ... These dots are for future extensions and must be empty.
#' @param echo Whether invoking the command shows the user's input as a message
#'   and waits for a response. Defaults to `TRUE` when `handler` is a function
#'   and `FALSE` when it's `NULL`. Use `echo = FALSE` for handlers that only
#'   perform side effects.
#' @param force If `TRUE`, replace an existing command with the same `name`
#'   instead of throwing an error.
#' @param session The Shiny session object.
#'
#' @returns A function that removes the command, invisibly.
#'
#' @examplesIf interactive()
#' library(shiny)
#' library(bslib)
#'
#' ui <- page_fillable(chat_ui("chat"))
#'
#' server <- function(input, output, session) {
#'   observeEvent(input$chat_user_input, {
#'     chat_append("chat", paste("You said:", input$chat_user_input))
#'   })
#'
#'   chat_slash_command(
#'     "chat",
#'     "clear",
#'     "Clear the conversation",
#'     function() chat_clear("chat"),
#'     echo = FALSE
#'   )
#'
#'   chat_slash_command("chat", "shout", "Repeat in capitals", function(content) {
#'     chat_append("chat", toupper(content@user_text))
#'   })
#' }
#'
#' shinyApp(ui, server)
#' @export
chat_slash_command <- function(
  id,
  name,
  description,
  handler,
  ...,
  echo = NULL,
  force = FALSE,
  session = getDefaultReactiveDomain()
) {
  rlang::check_dots_empty()
  check_active_session(session)
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

  slash_commands <- slash_command_registry(id, session)
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

  invisible(function() {
    cmds <- isolate(slash_commands())
    cmds[[name]] <- NULL
    slash_commands(cmds)
  })
}

SLASH_COMMANDS_KEY <- ".slash-commands"

# Returns the reactiveVal holding a chat's registered commands, creating it and
# the dispatch/sync observers on first use. Each entry is
# list(handler, takes_args, definition). A reactiveVal lets registrations made
# during app startup coalesce into a single client sync. It starts as NULL so
# the sync observer skips the redundant initial send (the client already
# initializes to []); an empty list is sent when the last command is removed.
slash_command_registry <- function(id, session) {
  key <- paste0(id, SLASH_COMMANDS_KEY)
  existing <- get_session_chat_bookmark_info(session, key)
  if (!is.null(existing)) {
    return(existing)
  }

  slash_commands <- shiny::reactiveVal(NULL, label = "slash_commands")
  input_id <- paste0(id, "_slash_command")

  shiny::observeEvent(
    session$input[[input_id]],
    label = "on_chat_slash_command",
    domain = session,
    {
      data <- session$input[[input_id]]
      reg <- isolate(slash_commands())[[data$command]]
      result <- NULL
      if (!is.null(reg) && is.function(reg$handler)) {
        result <- tryCatch(
          {
            if (isTRUE(reg$takes_args)) {
              reg$handler(slash_command_content(data))
            } else {
              reg$handler()
            }
          },
          error = function(e) {
            report_slash_command_error(e, data$command, session)
            NULL
          }
        )
      }

      remove_loading <- function() {
        send_chat_action(id, list(type = "remove_loading"), session = session)
      }
      # Don't return the promise from the observer: Shiny holds a session's
      # later inputs until async observers settle.
      if (promises::is.promising(result)) {
        promises::finally(
          promises::catch(result, function(e) {
            report_slash_command_error(e, data$command, session)
          }),
          remove_loading
        )
      } else {
        remove_loading()
      }
      invisible(NULL)
    }
  )

  shiny::observe(label = "sync_slash_commands", domain = session, {
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

  set_session_chat_bookmark_info(session, key, slash_commands)
  slash_commands
}

slash_command_content <- function(data) {
  user_text <- data$userText %||% ""
  ContentSlashCommand(
    command = data$command,
    user_text = user_text,
    text = paste0(
      sprintf("The user entered the /%s slash command", data$command),
      if (nzchar(user_text)) paste0(" with arguments: ", user_text) else "."
    )
  )
}

report_slash_command_error <- function(e, command, session) {
  shiny::showNotification(
    sanitized_error_message(e),
    type = "error",
    duration = NULL,
    session = session
  )
  rlang::warn(sprintf("Error in slash command '/%s'", command), parent = e)
}
