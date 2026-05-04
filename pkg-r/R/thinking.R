new_thinking_state <- function() {
  e <- new.env(parent = emptyenv())
  e$active <- FALSE
  e$start_time <- NULL
  e$buffer <- ""
  e$current_topic <- NULL
  e
}

handle_thinking_chunk <- function(id, text, thinking_state, session) {
  if (!thinking_state$active) {
    send_chat_action(
      id,
      action = list(type = "thinking_start"),
      session = session
    )
    thinking_state$active <- TRUE
    thinking_state$start_time <- proc.time()["elapsed"]
  }

  result <- extract_topics(text, thinking_state)

  action <- list(type = "thinking", content = result$text)
  if (!is.null(result$topic)) {
    action$topic <- result$topic
  }

  send_chat_action(id, action = action, session = session)
}

end_thinking <- function(id, thinking_state, session) {
  duration_ms <- round(
    (proc.time()["elapsed"] - thinking_state$start_time) * 1000
  )

  send_chat_action(
    id,
    action = list(type = "thinking_end", duration_ms = duration_ms),
    session = session
  )

  thinking_state$active <- FALSE
  thinking_state$start_time <- NULL
  thinking_state$buffer <- ""
  thinking_state$current_topic <- NULL

  invisible(NULL)
}

extract_topics <- function(text, thinking_state) {
  text <- paste0(thinking_state$buffer, text)
  thinking_state$buffer <- ""

  topic <- NULL

  # Replace complete <topic>...</topic> tags, capturing their content
  repeat {
    m <- regexpr("<topic>(.*?)</topic>", text, perl = TRUE)
    if (m == -1L) break

    match_start <- as.integer(m)
    match_len <- attr(m, "match.length")
    capture_start <- attr(m, "capture.start")
    capture_len <- attr(m, "capture.length")

    topic <- substr(text, capture_start, capture_start + capture_len - 1L)
    text <- paste0(
      substr(text, 1L, match_start - 1L),
      substr(text, match_start + match_len, nchar(text))
    )
  }

  # Check for a partial opening tag at the end of text that may be split
  # across chunks. Buffer patterns: "<", "<t", "<to", "<top", "<topi", "<topic",
  # "<topic>", "<topic>content" (without closing tag).
  partial_open <- "(<t(?:o(?:p(?:i(?:c(?:>[^<]*)?)?)?)?)?)?$"
  pm <- regexpr(partial_open, text, perl = TRUE)
  if (pm != -1L && attr(pm, "match.length") > 0L) {
    partial <- substr(text, as.integer(pm), nchar(text))
    if (nzchar(partial)) {
      thinking_state$buffer <- partial
      text <- substr(text, 1L, as.integer(pm) - 1L)
    }
  }

  if (!is.null(topic)) {
    thinking_state$current_topic <- topic
  }

  list(text = text, topic = topic)
}
