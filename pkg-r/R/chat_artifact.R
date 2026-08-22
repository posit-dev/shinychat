#' Show a chat artifact panel
#'
#' @description
#' Shows a chat's artifact panel. Supplying `content` or `title` updates that
#' field before the panel is shown. Omitted fields preserve their current value.
#'
#' @family chat artifact panels
#' @seealso [chat_artifact_panel()] to configure an artifact panel, and [chat_ui()] or
#'   [page_chat()] to display one.
#'
#' @param id The ID of the chat element.
#' @param content Optional UI content for the artifact. Use an empty
#'   [htmltools::tagList()] to clear the content.
#' @param title Optional artifact title. Use `""` to clear the title.
#' @param session The Shiny session object.
#'
#' @returns Invisibly, `NULL`.
#' @export
chat_artifact_panel_show <- function(
  id,
  content = NULL,
  title = NULL,
  session = shiny::getDefaultReactiveDomain()
) {
  chat_artifact_panel_action(
    id = id,
    type = "artifact_show",
    content = content,
    title = title,
    session = session
  )
}

#' Hide a chat artifact panel
#'
#' @family chat artifact panels
#' @seealso [chat_artifact_panel()] to configure an artifact panel, and [chat_ui()] or
#'   [page_chat()] to display one.
#'
#' @param id The ID of the chat element.
#' @param session The Shiny session object.
#'
#' @returns Invisibly, `NULL`.
#' @export
chat_artifact_panel_hide <- function(
  id,
  session = shiny::getDefaultReactiveDomain()
) {
  chat_artifact_panel_action(id, type = "artifact_hide", session = session)
}

#' Toggle a chat artifact panel
#'
#' @family chat artifact panels
#' @seealso [chat_artifact_panel()] to configure an artifact panel, and [chat_ui()] or
#'   [page_chat()] to display one.
#'
#' @param id The ID of the chat element.
#' @param session The Shiny session object.
#'
#' @returns Invisibly, `NULL`.
#' @export
chat_artifact_panel_toggle <- function(
  id,
  session = shiny::getDefaultReactiveDomain()
) {
  chat_artifact_panel_action(id, type = "artifact_toggle", session = session)
}

#' Update a chat artifact panel
#'
#' @description
#' Updates a chat's artifact panel content or title without changing its visibility.
#' Omitted fields preserve their current value. Use an empty
#' [htmltools::tagList()] to clear content or `""` to clear the title.
#'
#' @family chat artifact panels
#' @seealso [chat_artifact_panel()] to configure an artifact panel, and [chat_ui()] or
#'   [page_chat()] to display one.
#'
#' @param id The ID of the chat element.
#' @param content Optional UI content for the artifact.
#' @param title Optional artifact title.
#' @param session The Shiny session object.
#'
#' @returns Invisibly, `NULL`.
#' @export
chat_artifact_panel_update <- function(
  id,
  content = NULL,
  title = NULL,
  session = shiny::getDefaultReactiveDomain()
) {
  chat_artifact_panel_action(
    id = id,
    type = "artifact_update",
    content = content,
    title = title,
    session = session
  )
}

chat_artifact_panel_action <- function(
  id,
  type,
  content = NULL,
  title = NULL,
  session
) {
  chat_validate_string(id, "id")
  check_active_session(session)
  if (!is.null(title)) {
    chat_validate_string(title, "title", allow_empty = TRUE)
  }

  action <- list(type = type)
  html_deps <- NULL
  if (!is.null(content)) {
    chat_validate_artifact_panel_content(content)
    ui <- process_ui(pre_process_ui(content), session)
    action$content <- as.character(ui[["html"]])
    html_deps <- ui[["deps"]]
  }
  if (!is.null(title)) {
    action$title <- title
  }

  send_chat_action(
    id,
    action = action,
    html_deps = html_deps,
    session = session
  )
  invisible(NULL)
}

chat_validate_artifact_panel_content <- function(content) {
  if (
    is.function(content) ||
      inherits(content, "coro_generator_instance") ||
      promises::is.promising(content)
  ) {
    cli::cli_abort(
      "{.arg content} must be static UI content, not a function, generator, or promise."
    )
  }

  tryCatch(
    htmltools::tagList(content),
    error = function(cnd) {
      cli::cli_abort(
        "{.arg content} must be valid UI content.",
        parent = cnd
      )
    }
  )
}

#' Create a chat artifact panel configuration
#'
#' @description
#' An artifact panel displays UI content adjacent to a chat interface, such as
#' a preview, a generated report, or a detail view. Use
#' `chat_artifact_panel()` to supply its initial content and layout to the
#' `artifact_panel` argument of [chat_ui()] or [page_chat()]. Update the panel
#' later with the other artifact panel functions.
#'
#' @family chat artifact panels
#' @seealso [chat_ui()] and [page_chat()] accept this configuration through
#'   their `artifact_panel` argument.
#'
#' @param ... UI content to display in the artifact panel.
#' @param title An optional artifact title.
#' @param width The initial artifact width. Positive numbers are converted to
#'   pixels; character values must be valid CSS lengths.
#' @param open Whether the artifact is initially visible.
#' @param resizable Whether the artifact can be resized on desktop.
#'
#' @returns A configuration object for use with [chat_ui()] or [page_chat()].
#' @export
chat_artifact_panel <- function(
  ...,
  title = NULL,
  width = 400,
  open = TRUE,
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
    class = "chat_artifact_panel"
  )
}

chat_artifact_panel_tag <- function(panel) {
  htmltools::tag(
    "shiny-chat-artifact",
    rlang::list2(
      title = panel$title,
      width = panel$width,
      open = if (panel$open) NA,
      resizable = if (!panel$resizable) "false",
      !!!panel$content,
      htmltools::findDependencies(panel$content)
    )
  )
}
