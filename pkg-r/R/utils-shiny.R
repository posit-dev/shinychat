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
# vector against whoever opens that URL. So we keep a ledger of the html we send
# and treat a reported segment as trustworthy only if it matches one.
#
# The browser only reports *settled* messages (buildMessagesSnapshot() drops
# anything still streaming), so the single string we ever have to recognize is
# the finished segment -- with consecutive same-type chunks already concatenated
# by the client. Rather than guessing where the client closes a segment, the
# ledger performs the same merge and records the result when the message closes.
#
# Hashes, not content: unlike html dependencies (which we substitute wholesale,
# see trusted_html_deps()), validation here is string equality, so storing the
# string would only make the ledger grow with the size of every payload.
#
# Session-wide rather than per chat: messages_input_value() has no chat id to key
# on, and content the server sent to one chat is still server-authored html.
HTML_CONTENT_SENT_KEY <- "shinychat_html_content_sent"

# Segments of the message currently streaming, per chat id, merged the way the
# client merges them.
HTML_CONTENT_OPEN_KEY <- "shinychat_html_content_open"

record_sent_html_content <- function(session, id, action) {
  if (is.null(session) || !is.list(action) || !is_string(action[["type"]])) {
    return(invisible())
  }
  type <- action[["type"]]
  if (!type %in% c("message", "chunk_start", "chunk", "chunk_end")) {
    # Anything else (greeting*, clear, update_input, ...) carries no message
    # content. Leaving the open segments untouched matters: dropping them would
    # let an unrelated action sent mid-stream break the merge in flight.
    return(invisible())
  }

  if (identical(type, "message")) {
    # A one-shot message is already what the browser will report back.
    trust_html_segments(session, action[["message"]][["segments"]])
    return(invisible())
  }

  open <- session$userData[[HTML_CONTENT_OPEN_KEY]] %||% list()
  if (identical(type, "chunk_start")) {
    open[[id]] <- as.list(action[["message"]][["segments"]] %||% list())
  } else if (identical(type, "chunk")) {
    # The client drops a chunk that isn't extending a streaming message, so a
    # chunk we never saw a chunk_start for displays nothing to trust.
    if (!is.null(open[[id]])) {
      open[[id]] <- merge_sent_chunk(open[[id]], action)
    }
  } else {
    # chunk_end: the message has settled, so this is the report to expect.
    trust_html_segments(session, open[[id]])
    open[[id]] <- NULL
  }
  session$userData[[HTML_CONTENT_OPEN_KEY]] <- open
  invisible()
}

is_trusted_html_content <- function(session, content) {
  if (is.null(session) || !is_string(content)) {
    return(FALSE)
  }
  sent <- session$userData[[HTML_CONTENT_SENT_KEY]]
  is.character(sent) && rlang::hash(content) %in% sent
}

# Mirrors the client's `chunk` reducer: a chunk extends the last segment when it
# shares its content type, `operation = "replace"` restarts the accumulation, and
# an absent content type inherits the type already in progress.
merge_sent_chunk <- function(segments, action) {
  content <- action[["content"]]
  if (!is_string(content)) {
    return(segments)
  }
  last <- if (length(segments) > 0) segments[[length(segments)]] else NULL
  content_type <- action[["content_type"]]
  if (!is_string(content_type)) {
    content_type <- last[["content_type"]] %||% "markdown"
  }

  if (identical(action[["operation"]], "replace")) {
    return(list(list(content = content, content_type = content_type)))
  }
  if (!is.null(last) && identical(last[["content_type"]], content_type)) {
    segments[[length(segments)]]$content <- paste0(last[["content"]], content)
    return(segments)
  }
  c(segments, list(list(content = content, content_type = content_type)))
}

trust_html_segments <- function(session, segments) {
  if (!is.list(segments) || length(segments) == 0) {
    return(invisible())
  }
  hashes <- character()
  for (s in segments) {
    if (is_html_content(s[["content_type"]], s[["content"]])) {
      hashes <- c(hashes, rlang::hash(s[["content"]]))
    }
  }
  if (length(hashes) == 0) {
    return(invisible())
  }
  sent <- session$userData[[HTML_CONTENT_SENT_KEY]] %||% character()
  session$userData[[HTML_CONTENT_SENT_KEY]] <- unique(c(sent, hashes))
  invisible()
}

is_html_content <- function(content_type, content) {
  identical(content_type, "html") && is_string(content)
}
