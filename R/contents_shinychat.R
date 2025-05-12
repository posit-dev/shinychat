#' Format ellmer content for shinychat
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
  if (length(content@arguments) == 0) {
    call <- call2(content@name)
  } else {
    call <- call2(content@name, !!!content@arguments)
  }

  shiny::HTML(sprintf(
    '\n\n<p class="shiny-tool-request" data-tool-call-id="%s">Running <code>%s</code></p>\n\n',
    content@id,
    format(call)
  ))
}

S7::method(contents_shinychat, ellmer::ContentToolResult) <- function(
  content,
  ...
) {
  pre_code <- function(x) {
    sprintf("<pre><code>%s</code></pre>", paste(x, collapse = "\n"))
  }

  if (!is.null(content@error)) {
    tool_args <- pre_code(
      jsonlite::toJSON(content@request@arguments, auto_unbox = TRUE)
    )
    err <- sprintf(
      '<details class="shiny-tool-result failed" id="%s"><summary>Failed to call <span class="function-name">%s</span></summary>%s\n\nError:\n\n%s\n\n</details>',
      content@request@id,
      if (!is.null(content@request@tool)) content@request@tool@name else
        "unknown tool",
      tool_args,
      pre_code(content@error)
    )
    return(shiny::HTML(paste0("\n\n", err, "\n\n")))
  }

  result <- paste(content@value, collapse = "\n")

  if (!grepl("```", result)) {
    result <- pre_code(result)
  }
  result <- paste0("<strong>Tool Result</strong>\n", result)

  if (length(content@request@arguments) == 0) {
    call <- call2(content@request@name)
  } else {
    call <- call2(content@request@name, !!!content@request@arguments)
  }

  tool_call <- paste0("<strong>Tool Call</strong>", pre_code(format(call)))

  x <- sprintf(
    '<details class="shiny-tool-result" id="%s"><summary>View result from <span class="function-name">%s</span></summary>%s\n\n%s\n\n</details>',
    content@request@id,
    content@request@name,
    tool_call,
    result
  )

  shiny::HTML(paste0("\n\n", x, "\n\n"))
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
    list(role = turn@role, content = content)
  })

  compact(messages)
}
