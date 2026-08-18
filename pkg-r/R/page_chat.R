#' Create a chat sidebar configuration
#'
#' @param ... UI content to display in the sidebar.
#' @param history Whether to display the chat history selector in the sidebar.
#' @param width The initial sidebar width. Positive numbers are converted to
#'   pixels; character values must be valid CSS lengths.
#' @param open The initial sidebar state. One of `"auto"`, `"open"`, `"closed"`,
#'   or `"always"`. Logical values are aliases for `"open"` and `"closed"`.
#' @param resizable Whether the sidebar can be resized on desktop.
#'
#' @returns A configuration object for use with [chat_nav_panel()].
#' @export
chat_sidebar <- function(
  ...,
  history = FALSE,
  width = 280,
  open = "auto",
  resizable = TRUE
) {
  content <- chat_config_content(...)
  chat_validate_boolean(history, "history")
  width <- chat_validate_width(width, "width")
  open <- chat_normalize_sidebar_open(open)
  chat_validate_boolean(resizable, "resizable")

  structure(
    list(
      content = content,
      history = history,
      width = width,
      open = open,
      resizable = resizable
    ),
    class = "chat_sidebar"
  )
}

#' Create a chat artifact configuration
#'
#' @param ... UI content to display in the artifact panel.
#' @param title An optional artifact title.
#' @param width The initial artifact width. Positive numbers are converted to
#'   pixels; character values must be valid CSS lengths.
#' @param open Whether the artifact is initially visible.
#' @param resizable Whether the artifact can be resized on desktop.
#'
#' @returns A configuration object for use with [chat_ui()].
#' @export
chat_artifact <- function(
  ...,
  title = NULL,
  width = 400,
  open = FALSE,
  resizable = TRUE
) {
  content <- chat_config_content(...)
  if (!is.null(title)) {
    chat_validate_string(title, "title", allow_empty = TRUE)
  }
  width <- chat_validate_width(width, "width")
  chat_validate_boolean(open, "open")
  chat_validate_boolean(resizable, "resizable")

  structure(
    list(
      content = content,
      title = title,
      width = width,
      open = open,
      resizable = resizable
    ),
    class = "chat_artifact"
  )
}

#' Create a page-chat navigation panel
#'
#' @param title The panel title.
#' @param ... UI content to display when the panel is active.
#' @param value An optional unique navigation value.
#' @param icon An optional icon to display with the title.
#' @param sidebar Whether to use the default sidebar (`TRUE`), no
#'   page-specific sidebar (`FALSE`), or a [chat_sidebar()] configuration.
#'
#' @returns A configuration object for use with `page_chat()`.
#' @export
chat_nav_panel <- function(
  title,
  ...,
  value = NULL,
  icon = NULL,
  sidebar = FALSE
) {
  chat_validate_string(title, "title")
  content <- chat_config_content(...)
  if (!is.null(value)) {
    chat_validate_string(value, "value")
  }
  chat_validate_sidebar(sidebar)

  structure(
    list(
      title = title,
      content = content,
      value = value,
      icon = icon,
      sidebar = sidebar
    ),
    class = "chat_nav_panel"
  )
}

#' Create a chat history selector
#'
#' @param id The ID of the associated chat.
#' @param ... Named HTML attributes to apply to the selector.
#'
#' @returns A Shiny tag object.
#' @export
chat_ui_history <- function(id, ...) {
  attrs <- rlang::list2(...)
  if (!all(nzchar(rlang::names2(attrs)))) {
    rlang::abort("All arguments in ... must be named HTML attributes.")
  }
  if ("for" %in% names(attrs)) {
    rlang::abort(
      "`for` is managed by chat_ui_history(); supply the associated chat ID with `id`."
    )
  }

  htmltools::tag(
    "shiny-chat-history",
    rlang::list2(
      `for` = resolve_id(id),
      ...,
      shinychat_deps()
    )
  )
}

chat_config_content <- function(...) {
  content <- rlang::list2(...)
  if (any(nzchar(rlang::names2(content)))) {
    rlang::abort("Arguments in ... must be unnamed UI content.")
  }
  content
}

chat_validate_boolean <- function(value, arg) {
  if (!is.logical(value) || length(value) != 1 || is.na(value)) {
    cli::cli_abort("{.arg {arg}} must be {.code TRUE} or {.code FALSE}.")
  }
}

chat_validate_width <- function(value, arg) {
  if (
    length(value) != 1 ||
      is.na(value) ||
      (!is.numeric(value) && !is.character(value)) ||
      (is.numeric(value) && (!is.finite(value) || value <= 0))
  ) {
    cli::cli_abort(
      "{.arg {arg}} must be a positive number or a non-empty CSS length."
    )
  }

  tryCatch(
    htmltools::validateCssUnit(value),
    error = function(cnd) {
      cli::cli_abort(
        "{.arg {arg}} must be a valid CSS length.",
        parent = cnd
      )
    }
  )
}

chat_validate_string <- function(value, arg, allow_empty = FALSE) {
  if (!rlang::is_string(value) || (!allow_empty && !nzchar(value))) {
    requirement <- if (allow_empty) "a string" else "a non-empty string"
    cli::cli_abort("{.arg {arg}} must be {requirement}.")
  }
}

chat_normalize_sidebar_open <- function(open) {
  if (isTRUE(open)) {
    return("open")
  }
  if (isFALSE(open)) {
    return("closed")
  }
  if (
    !rlang::is_string(open) || !open %in% c("auto", "open", "closed", "always")
  ) {
    cli::cli_abort(
      "{.arg open} must be one of {.val auto}, {.val open}, {.val closed}, or {.val always}."
    )
  }
  open
}

chat_validate_sidebar <- function(sidebar) {
  if (
    isTRUE(sidebar) || isFALSE(sidebar) || inherits(sidebar, "chat_sidebar")
  ) {
    return(invisible())
  }
  cli::cli_abort(
    "{.arg sidebar} must be {.code TRUE}, {.code FALSE}, or a {.fn chat_sidebar} configuration."
  )
}

normalize_chat_artifact <- function(artifact) {
  if (isTRUE(artifact)) {
    return(chat_artifact())
  }
  if (isFALSE(artifact)) {
    return(NULL)
  }
  if (inherits(artifact, "chat_artifact")) {
    return(artifact)
  }
  cli::cli_abort(
    "{.arg artifact} must be {.code TRUE}, {.code FALSE}, or a {.fn chat_artifact} configuration."
  )
}

chat_artifact_tag <- function(artifact) {
  htmltools::tag(
    "shiny-chat-artifact",
    rlang::list2(
      title = artifact$title,
      width = artifact$width,
      open = if (artifact$open) NA,
      resizable = if (!artifact$resizable) "false",
      !!!artifact$content,
      htmltools::findDependencies(artifact$content)
    )
  )
}
