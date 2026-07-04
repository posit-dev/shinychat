#' Register a slash command
#'
#' @description
#' Register a command for shinychat's slash-command typeahead palette. This is a
#' standalone counterpart to [chat_server()]'s `$slash_command()` method: it can
#' be called from anywhere in your server function -- you don't have to thread
#' the value returned by `chat_server()` through your code. It also works
#' **without** `chat_server()` at all, so you can add the official palette to a
#' [chat_ui()] that you drive with your own server logic (custom streaming, an
#' external agent loop, etc.).
#'
#' The first time it is called for a given chat `id`, it wires up the two
#' observers that back the palette (a dispatcher for the submitted command and a
#' syncer that pushes command definitions to the client); subsequent calls just
#' register more commands. `chat_server()` uses this same machinery internally,
#' so both paths share a single implementation.
#'
#' @details
#' `handler` behaves exactly as in `chat_server()`'s `$slash_command()`:
#'
#' * `NULL`: the command is handled entirely on the client via the cancelable
#'   `shiny:chat-slash-command` DOM event.
#' * a zero-argument function: run for its side effects when the command is
#'   invoked.
#' * a one-argument function: receives a [ContentSlashCommand] object (not a
#'   plain string) whose `text` you can mutate before passing it to
#'   `client$stream()`.
#'
#' @param id The `chat_ui()` output id whose palette the command belongs to.
#' @param name The command name, without the leading `/`. Only alphanumeric
#'   characters, underscores, and hyphens are allowed.
#' @param description Text shown for the command in the palette.
#' @param handler A function taking 0 or 1 argument, or `NULL`. See Details.
#' @param ... These dots are for future extensions and must be empty.
#' @param echo Whether invoking the command adds a user message and shows the
#'   loading state. Defaults to `TRUE` when a `handler` is supplied and `FALSE`
#'   otherwise.
#' @param force Overwrite an existing command with the same `name`.
#' @param session The Shiny session. Defaults to the current reactive domain.
#'
#' @returns A function that unregisters the command when called (invisibly).
#'
#' @seealso [chat_ui()], [chat_server()], [ContentSlashCommand]
#'
#' @examplesIf rlang::is_interactive()
#' library(shiny)
#' library(bslib)
#' library(shinychat)
#'
#' ui <- page_fillable(chat_ui("chat"))
#'
#' server <- function(input, output, session) {
#'   # No chat_server(), no threaded return value -- just register.
#'   register_slash_command("chat", "clear", "Clear the conversation", function() {
#'     chat_clear("chat")
#'   })
#'
#'   register_slash_command("chat", "greet", "Greet someone", function(content) {
#'     chat_append("chat", paste("Hello,", content@user_text))
#'   })
#' }
#'
#' shinyApp(ui, server)
#'
#' @export
register_slash_command <- function(
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

  slash_commands <- slash_commands_registry(id, session = session)
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

# Get-or-create the per-(session, id) slash-command registry, wiring up the
# dispatch + sync observers exactly once. Returns the reactiveVal holding the
# registered commands. State lives in session$userData$shinychat, keyed by the
# namespaced id -- the same idiom used for bookmark info in chat_restore.R --
# so that register_slash_command() (and chat_server()) can reach it without
# threading any value through user code.
#
# Each registry entry is list(handler, takes_args, definition). The reactiveVal
# starts as NULL so the sync observer skips the redundant initial send (the
# client already initializes to []); an empty list is sent once the last
# command is removed.
slash_commands_registry <- function(
  id,
  session = getDefaultReactiveDomain()
) {
  if (is.null(session)) {
    cli::cli_abort("A Shiny {.cls session} is required to register slash commands.")
  }
  if (is.null(session$userData$shinychat)) {
    session$userData$shinychat <- list()
  }
  key <- session$ns(id)
  state <- session$userData$shinychat[[key]] %||% list()

  if (!is.null(state$slash_commands)) {
    return(state$slash_commands)
  }

  slash_commands <- shiny::reactiveVal(NULL, label = "slash_commands")

  shiny::observeEvent(
    session$input[[paste0(id, "_slash_command")]],
    label = "on_chat_slash_command",
    domain = session,
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

  state$slash_commands <- slash_commands
  session$userData$shinychat[[key]] <- state
  slash_commands
}
