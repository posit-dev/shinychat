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
  record_sent_html_content(session, envelope$id, action)
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

# Establishes the trust boundary for `content_type: "html"` segment content
# reported back through the browser's `<id>_messages` snapshot. Those reports get
# persisted (bookmark state, history store) and replayed into sinks that assign
# raw HTML: `RawHTML` writes to innerHTML, and the tool cards' icon/footer/value
# attributes reach dangerouslySetInnerHTML. Since a server bookmark is shareable
# via its `_state_id_` URL, a forged report would otherwise be a stored-script
# vector against whoever opens that URL. So we keep hashes of every html string
# we send and treat a reported segment as trustworthy only if it matches one.
#
# Hashes, not content: unlike html dependencies (which we substitute wholesale,
# see trusted_html_deps()), validation here is string equality, so storing the
# string would only make the registry grow with the size of every payload.
#
# Session-wide rather than per chat: messages_input_value() has no chat id to key
# on, and content the server sent to one chat is still server-authored html.
HTML_CONTENT_SENT_KEY <- "shinychat_html_content_sent"

# In-flight html run per chat id. The client concatenates consecutive chunks that
# share a content type into one segment, so we record every prefix of a run
# rather than trying to predict where the client closes the segment.
HTML_CONTENT_RUN_KEY <- "shinychat_html_content_run"

record_sent_html_content <- function(session, id, action) {
  if (is.null(session) || !is.list(action) || !is_string(action[["type"]])) {
    return(invisible())
  }
  if (
    !action[["type"]] %in% c("chunk_start", "chunk", "chunk_end", "message")
  ) {
    # Anything else (greeting*, clear, update_input, ...) carries no message
    # content. Leaving the run untouched matters: resetting it would let an
    # unrelated action sent mid-stream invalidate the concatenation in flight.
    return(invisible())
  }

  sent <- session$userData[[HTML_CONTENT_SENT_KEY]] %||% character()
  runs <- session$userData[[HTML_CONTENT_RUN_KEY]] %||% list()
  run <- runs[[id]] %||% ""

  if (identical(action[["type"]], "chunk_end")) {
    run <- ""
  } else if (identical(action[["type"]], "chunk")) {
    if (is_html_content(action[["content_type"]], action[["content"]])) {
      run <- if (identical(action[["operation"]], "replace")) {
        action[["content"]]
      } else {
        paste0(run, action[["content"]])
      }
      sent <- c(sent, rlang::hash(run))
    } else {
      run <- ""
    }
  } else {
    # message / chunk_start: one client block per segment, so each segment is
    # trusted on its own and the concatenation across them never appears.
    segments <- action[["message"]][["segments"]] %||% list()
    for (s in segments) {
      if (is_html_content(s[["content_type"]], s[["content"]])) {
        sent <- c(sent, rlang::hash(s[["content"]]))
      }
    }
    # Only a chunk_start's final segment can be extended by later chunks; a
    # completed `message` is never appended to.
    last <- if (length(segments) > 0) segments[[length(segments)]] else NULL
    run <- if (
      identical(action[["type"]], "chunk_start") &&
        !is.null(last) &&
        is_html_content(last[["content_type"]], last[["content"]])
    ) {
      last[["content"]]
    } else {
      ""
    }
  }

  session$userData[[HTML_CONTENT_SENT_KEY]] <- unique(sent)
  runs[[id]] <- run
  session$userData[[HTML_CONTENT_RUN_KEY]] <- runs
  invisible()
}

is_trusted_html_content <- function(session, content) {
  if (is.null(session) || !is_string(content)) {
    return(FALSE)
  }
  sent <- session$userData[[HTML_CONTENT_SENT_KEY]]
  is.character(sent) && rlang::hash(content) %in% sent
}

is_html_content <- function(content_type, content) {
  identical(content_type, "html") && is_string(content)
}
