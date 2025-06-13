#' Format ellmer content for shinychat
#'
#' @param content An [`ellmer::Content`] object.
#' @param ... Additional arguments passed to underlying methods.
#'
#' @return Returns text or HTML formatted for use in `chat_ui()`.
#'
#' @export
contents_shinychat <- S7::new_generic("contents_shinychat", "content")

S7::method(contents_shinychat, ellmer::Content) <- function(content, ...) {
  # Fall back to html or markdown
  html <- ellmer::contents_html(content)
  if (!is.null(html)) shiny::HTML(html) else ellmer::contents_markdown(content)
}

S7::method(contents_shinychat, ellmer::ContentText) <- function(content) {
  content@text
}

S7::method(contents_shinychat, ellmer::ContentToolRequest) <- function(
  content,
  ...
) {
  shiny::HTML(sprintf(
    '\n\n<p class="shiny-tool-request" data-tool-call-id="%s">Running <code>%s</code></p>\n\n',
    content@id,
    paste(format(content, show = "call"), collapse = " ")
  ))
}

S7::method(contents_shinychat, ellmer::ContentToolResult) <- function(
  content,
  ...
) {
  pre_code <- function(x) {
    x <- gsub("`", "&#96;", x, fixed = TRUE)
    x <- gsub("<", "&lt;", x, fixed = TRUE)
    x <- gsub(">", "&gt;", x, fixed = TRUE)
    sprintf("<pre><code>%s</code></pre>", paste(x, collapse = "\n"))
  }

  if (!is.null(content@error)) {
    class <- "shiny-tool-result failed"
    summary_text <- "Failed to call"
    tool_result <- sprintf(
      "<strong>Error</strong>%s",
      pre_code(strip_ansi(content@error))
    )
  } else {
    class <- "shiny-tool-result"
    summary_text <- "Result from"
    tool_result <- sprintf(
      '<strong>Tool Result</strong>%s',
      pre_code(content@value)
    )
  }

  if (!is.null(content@request@tool)) {
    if (!is.null(content@request@tool@annotations$title)) {
      # Use the tool title if available
      tool_name <- content@request@tool@annotations$title
      summary_text <- ""
    } else {
      # Fallback to tool name
      tool_name <- content@request@tool@name
    }
  } else {
    tool_name <- "unknown tool"
  }

  intent <- ""
  if (!is.null(content@request@arguments$intent)) {
    intent <- sprintf(
      ' | <span class="intent">%s</span>',
      content@request@arguments$intent
    )
  }

  tool_call <-
    details_open <- sprintf(
      '<details class="%s" id="%s">',
      class,
      content@request@id
    )

  summary <- sprintf(
    '<summary>%s <span class="function-name">%s</span>%s</summary>',
    summary_text,
    tool_name,
    intent
  )

  tool_call <- sprintf(
    '<strong>Tool Call</strong>%s',
    pre_code(format(content@request, show = "call"))
  )

  body <- sprintf(
    '<p>%s</p><p>%s</p></details>\n\n',
    tool_call,
    tool_result
  )

  return(shiny::HTML(paste0(details_open, summary, body)))
}

S7::method(contents_shinychat, ellmer::Turn) <- function(content) {
  lapply(content@contents, contents_shinychat)
}

S7::method(contents_shinychat, S7::new_S3_class(c("Chat", "R6"))) <- function(
  content,
  ...
) {
  # Consolidate tool calls into assistant turns. This currently assumes that
  # tool calls are always returned in user turns that have at least one
  # proceeding assistant turn.
  turns <- map(content$get_turns(), function(turn) {
    if (
      all(map_lgl(turn@contents, S7::S7_inherits, ellmer::ContentToolResult))
    ) {
      turn@role <- "assistant"
    }
    is_tool_request <- map_lgl(
      turn@contents,
      S7::S7_inherits,
      ellmer::ContentToolRequest
    )
    turn@contents <- turn@contents[!is_tool_request]
    turn
  })
  turns <- reduce(turns, .init = list(), function(turns, turn) {
    if (length(turns) == 0) {
      return(list(turn))
    }

    # consolidate turns with adjacent roles
    last_turn <- turns[[length(turns)]]
    if (identical(last_turn@role, turn@role)) {
      turns[[length(turns)]]@contents <- c(last_turn@contents, turn@contents)
      return(turns)
    }

    c(turns, list(turn))
  })

  messages <- map(turns, function(turn) {
    content <- compact(contents_shinychat(turn))
    if (is.null(content) || identical(content, "")) {
      return(NULL)
    }
    if (every(content, is.character)) {
      # TODO: Fix chat_ui() to handle lists of strings
      content <- paste(unlist(content), collapse = "\n\n")
    }
    list(role = turn@role, content = content)
  })

  compact(messages)
}
