#' Show a chat artifact
#'
#' @description
#' Shows a chat's artifact panel. Supplying `content` or `title` updates that
#' field before the panel is shown. Omitted fields preserve their current value.
#'
#' @param id The ID of the chat element.
#' @param content Optional UI content for the artifact. Use an empty
#'   [htmltools::tagList()] to clear the content.
#' @param title Optional artifact title. Use `""` to clear the title.
#' @param session The Shiny session object.
#'
#' @returns Invisibly, `NULL`.
#' @export
chat_artifact_show <- function(
  id,
  content = NULL,
  title = NULL,
  session = shiny::getDefaultReactiveDomain()
) {
  chat_artifact_action(
    id = id,
    type = "artifact_show",
    content = content,
    title = title,
    session = session
  )
}

#' Hide a chat artifact
#'
#' @param id The ID of the chat element.
#' @param session The Shiny session object.
#'
#' @returns Invisibly, `NULL`.
#' @export
chat_artifact_hide <- function(
  id,
  session = shiny::getDefaultReactiveDomain()
) {
  chat_artifact_action(id, type = "artifact_hide", session = session)
}

#' Toggle a chat artifact
#'
#' @param id The ID of the chat element.
#' @param session The Shiny session object.
#'
#' @returns Invisibly, `NULL`.
#' @export
chat_artifact_toggle <- function(
  id,
  session = shiny::getDefaultReactiveDomain()
) {
  chat_artifact_action(id, type = "artifact_toggle", session = session)
}

#' Update a chat artifact
#'
#' @description
#' Updates a chat's artifact content or title without changing its visibility.
#' Omitted fields preserve their current value. Use an empty
#' [htmltools::tagList()] to clear content or `""` to clear the title.
#'
#' @param id The ID of the chat element.
#' @param content Optional UI content for the artifact.
#' @param title Optional artifact title.
#' @param session The Shiny session object.
#'
#' @returns Invisibly, `NULL`.
#' @export
chat_artifact_update <- function(
  id,
  content = NULL,
  title = NULL,
  session = shiny::getDefaultReactiveDomain()
) {
  chat_artifact_action(
    id = id,
    type = "artifact_update",
    content = content,
    title = title,
    session = session
  )
}

chat_artifact_action <- function(
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
    chat_validate_artifact_content(content)
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

chat_validate_artifact_content <- function(content) {
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
