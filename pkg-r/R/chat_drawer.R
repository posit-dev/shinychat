#' Show a chat drawer
#'
#' @description
#' Shows a chat's drawer. Supplying `content` or `title` updates that
#' field before the panel is shown. Omitted fields preserve their current value.
#'
#' @family chat drawers
#' @seealso [chat_drawer()] to configure a drawer, and [chat_ui()] or
#'   [page_chat()] to display one.
#'
#' @param id The ID of the chat element.
#' @param content Optional UI content for the drawer. Use an empty
#'   [htmltools::tagList()] to clear the content.
#' @param title Optional drawer title. Use `""` to clear the title.
#' @param session The Shiny session object.
#'
#' @returns Invisibly, `NULL`.
#' @export
chat_drawer_show <- function(
  id,
  content = NULL,
  title = NULL,
  session = shiny::getDefaultReactiveDomain()
) {
  chat_drawer_action(
    id = id,
    type = "drawer_show",
    content = content,
    title = title,
    session = session
  )
}

#' Hide a chat drawer
#'
#' @family chat drawers
#' @seealso [chat_drawer()] to configure a drawer, and [chat_ui()] or
#'   [page_chat()] to display one.
#'
#' @param id The ID of the chat element.
#' @param session The Shiny session object.
#'
#' @returns Invisibly, `NULL`.
#' @export
chat_drawer_hide <- function(
  id,
  session = shiny::getDefaultReactiveDomain()
) {
  chat_drawer_action(id, type = "drawer_hide", session = session)
}

#' Toggle a chat drawer
#'
#' @family chat drawers
#' @seealso [chat_drawer()] to configure a drawer, and [chat_ui()] or
#'   [page_chat()] to display one.
#'
#' @param id The ID of the chat element.
#' @param session The Shiny session object.
#'
#' @returns Invisibly, `NULL`.
#' @export
chat_drawer_toggle <- function(
  id,
  session = shiny::getDefaultReactiveDomain()
) {
  chat_drawer_action(id, type = "drawer_toggle", session = session)
}

#' Update a chat drawer
#'
#' @description
#' Updates a chat's drawer content or title without changing its visibility.
#' Omitted fields preserve their current value. Use an empty
#' [htmltools::tagList()] to clear content or `""` to clear the title.
#'
#' @family chat drawers
#' @seealso [chat_drawer()] to configure a drawer, and [chat_ui()] or
#'   [page_chat()] to display one.
#'
#' @param id The ID of the chat element.
#' @param content Optional UI content for the drawer.
#' @param title Optional drawer title.
#' @param session The Shiny session object.
#'
#' @returns Invisibly, `NULL`.
#' @export
chat_drawer_update <- function(
  id,
  content = NULL,
  title = NULL,
  session = shiny::getDefaultReactiveDomain()
) {
  chat_drawer_action(
    id = id,
    type = "drawer_update",
    content = content,
    title = title,
    session = session
  )
}

chat_drawer_action <- function(
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
    chat_validate_drawer_content(content)
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

chat_validate_drawer_content <- function(content) {
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

#' Create a chat drawer configuration
#'
#' @description
#' An drawer displays UI content adjacent to a chat interface, such as
#' a preview, a generated report, or a detail view. Use
#' `chat_drawer()` to supply its initial content and layout to the
#' `drawer` argument of [chat_ui()] or [page_chat()]. Update the panel
#' later with the other drawer functions.
#'
#' @family chat drawers
#' @seealso [chat_ui()] and [page_chat()] accept this configuration through
#'   their `drawer` argument.
#'
#' @param ... UI content to display in the drawer.
#' @param title An optional drawer title.
#' @param width The initial drawer width. Positive numbers are converted to
#'   pixels; character values must be valid CSS lengths.
#' @param open Whether the drawer is initially visible.
#' @param resizable Whether the drawer can be resized on desktop.
#'
#' @returns A configuration object for use with [chat_ui()] or [page_chat()].
#' @export
chat_drawer <- function(
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
    class = "chat_drawer"
  )
}

chat_drawer_tag <- function(panel) {
  htmltools::tag(
    "shiny-chat-drawer",
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
