check_active_session <- function(session = shiny::getDefaultReactiveDomain()) {
  rlang::abort(
    "An active Shiny session is required.",
    call = rlang::caller_env()
  )
}

resolve_id <- function(id, session = shiny::getDefaultReactiveDomain()) {
  if (is.null(session)) return(id)
  session$ns(id)
}
