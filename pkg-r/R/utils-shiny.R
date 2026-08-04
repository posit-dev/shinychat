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
    record_sent_html_deps(session, html_deps)
    envelope$html_deps <- html_deps
  }
  session$sendCustomMessage("shinyChatMessage", envelope)
}

# Establishes the trust boundary for dependencies reported back through the
# browser's `<id>_messages` snapshot. Those reports get persisted (bookmark
# state, history store) and replayed with `send_chat_action(html_deps =)`, which
# reaches `Shiny.renderDependenciesAsync()` and injects the dependency's
# script/head content into the page. Since a server bookmark is shareable via
# its `_state_id_` URL, a forged report would otherwise be a stored-script
# vector against whoever opens that URL. So we keep our own copy of every
# dependency we send and treat the client's report as nothing more than a set of
# identities to look up.
#
# The registry is session-wide rather than per-chat: dependencies render into
# `document.head`, so one already loaded for any chat is loaded for the page.
HTML_DEPS_SENT_KEY <- "shinychat_html_deps_sent"

record_sent_html_deps <- function(session, deps) {
  if (is.null(session) || !is.list(deps)) {
    return(invisible())
  }
  sent <- session$userData[[HTML_DEPS_SENT_KEY]] %||% list()
  for (dep in deps) {
    key <- html_dep_key(dep)
    if (!is.na(key)) {
      sent[[key]] <- dep
    }
  }
  session$userData[[HTML_DEPS_SENT_KEY]] <- sent
  invisible()
}

trusted_html_deps <- function(session, deps) {
  if (is.null(session) || !is.list(deps) || length(deps) == 0) {
    return(NULL)
  }
  sent <- session$userData[[HTML_DEPS_SENT_KEY]]
  if (!is.list(sent) || length(sent) == 0) {
    return(NULL)
  }
  keys <- unique(vapply(deps, html_dep_key, character(1)))
  keys <- keys[!is.na(keys) & keys %in% names(sent)]
  if (length(keys) == 0) {
    return(NULL)
  }
  unname(sent[keys])
}

html_dep_key <- function(dep) {
  if (!is.list(dep) || !is_string(dep$name) || !is_string(dep$version)) {
    return(NA_character_)
  }
  paste0(dep$name, "@", dep$version)
}
