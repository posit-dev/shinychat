#' Format ellmer content for shinychat
#'
#' @param content An [`ellmer::Content`] object.
#'
#' @return Returns text or HTML formatted for use in `chat_ui()`.
#'
#' @export
contents_shinychat <- S7::new_generic("contents_shinychat", "content")

S7::method(contents_shinychat, ellmer::Content) <- function(content) {
  # Fall back to html or markdown
  html <- ellmer::contents_html(content)
  if (!is.null(html)) shiny::HTML(html) else ellmer::contents_markdown(content)
}

S7::method(contents_shinychat, ellmer::ContentText) <- function(content) {
  content@text
}

S7::method(contents_shinychat, ellmer::ContentToolRequest) <- function(
  content
) {
  call <- format(content, show = "call")
  if (length(call) > 1) {
    call <- sprintf("%s()", content@name)
  }
  shiny::HTML(sprintf(
    '\n\n<p class="shiny-tool-request" data-tool-call-id="%s">Running <code>%s</code></p>\n\n',
    content@id,
    call
  ))
}

S7::method(contents_shinychat, ellmer::ContentToolResult) <- function(
  content
) {
  deps <- NULL

  tool_result_display <- function(content) {
    display <- content@extra$display
    if (is.null(display)) {
      return(pre_code(content@value))
    }

    html <- NULL
    md <- NULL
    text <- NULL

    has_display_list <- is.list(display) &&
      !inherits(display, c("shiny.tag.list", "shiny.tag"))

    if (has_display_list) {
      has_display_list_name <- some(c("text", "markdown", "html"), \(x) {
        x %in% names(display)
      })

      if (has_display_list) {
        html <- display$html
        md <- display$markdown
        text <- display$text
      }
    } else {
      if (inherits(display, c("html", "shiny.tag.list", "shiny.tag"))) {
        html <- display
      } else if (is.character(display)) {
        md <- display
      }
    }

    if (!is.null(html)) {
      deps <<- htmltools::findDependencies(html)
      return(format(html))
    }

    if (!is.null(markdown)) {
      md <- paste(md, collapse = "\n")
      md <- paste0("\n\n", md, "\n\n")
      return(md)
    }

    if (!nzchar(text)) {
      text <- NULL
    }

    return(text %||% pre_code(contents$value))
  }

  if (isFALSE(content@extra$display_tool_request)) {
    res <- tool_result_display(content)
    if (!is.null(deps)) {
      res <- htmltools::attachDependencies(res, deps)
    }
    return(res)
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
      tool_result_display(content)
    )
  }

  tool_name <- "unknown tool"
  tool <- content@request@tool
  if (!is.null(tool)) {
    tool_name <- tool@name
    if (!is.null(tool@annotations$title)) {
      tool_name <- tool@annotations$title
      summary_text <- ""
    }
  }

  intent <- ""
  if (!is.null(content@request@arguments$intent)) {
    intent <- sprintf(
      ' | <span class="intent">%s</span>',
      content@request@arguments$intent
    )
  }

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

  res <- shiny::HTML(paste0(details_open, summary, body))
  if (!is.null(deps)) {
    res <- htmltools::attachDependencies(res, deps)
  }
  return(res)
}

S7::method(contents_shinychat, ellmer::Turn) <- function(content) {
  lapply(content@contents, contents_shinychat)
}

S7::method(contents_shinychat, S7::new_S3_class(c("Chat", "R6"))) <- function(
  content
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
      content <- paste(unlist(content), collapse = "\n\n")
    }
    list(role = turn@role, content = content)
  })

  compact(messages)
}

pre_code <- function(x) {
  x <- gsub("`", "&#96;", x, fixed = TRUE)
  x <- gsub("<", "&lt;", x, fixed = TRUE)
  x <- gsub(">", "&gt;", x, fixed = TRUE)
  sprintf("<pre><code>%s</code></pre>", paste(x, collapse = "\n"))
}
