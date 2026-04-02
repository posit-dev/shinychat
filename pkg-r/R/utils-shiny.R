check_active_session <- function(session = shiny::getDefaultReactiveDomain()) {
  if (is.null(session)) {
    rlang::abort(
      "An active Shiny session is required.",
      call = rlang::caller_env()
    )
  }
}

resolve_id <- function(id, session = shiny::getDefaultReactiveDomain()) {
  if (is.null(session)) {
    return(id)
  }
  session$ns(id)
}

send_chat_action <- function(id, action, html_deps = NULL, session) {
  envelope <- list(
    id = resolve_id(id, session),
    action = action
  )
  if (!is.null(html_deps)) {
    envelope$html_deps <- html_deps
  }
  session$sendCustomMessage("shinyChatMessage", envelope)
}
