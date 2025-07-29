#' Format ellmer content for shinychat
#'
#' @param content An [`ellmer::Content`] object.
#'
#' @return Returns text, HTML, or web component tags formatted for use in `chat_ui()`.
#'
#' @export
contents_shinychat <- S7::new_generic("contents_shinychat", "content")

S7::method(contents_shinychat, ellmer::Content) <- function(content) {
  # Fall back to html or markdown
  html <- ellmer::contents_html(content)
  if (!is.null(html)) {
    shiny::HTML(html)
  } else {
    ellmer::contents_markdown(content)
  }
}

S7::method(contents_shinychat, ellmer::ContentText) <- function(content) {
  content@text
}

S7::method(contents_shinychat, ellmer::ContentToolRequest) <- function(
  content
) {
  props <- list(
    "request-id" = content@id,
    name = content@name,
    arguments = jsonlite::toJSON(content@arguments, auto_unbox = TRUE)
  )

  # Add optional title if present in tool annotations
  if (!is.null(content@tool@annotations$title)) {
    props$title <- content@tool@annotations$title
  }

  # Add optional intent if present in request arguments
  if (!is.null(content@arguments$.intent)) {
    props$intent <- content@arguments$.intent
  }

  # Return structured tag
  htmltools::tag("shiny-tool-request", props)
}

S7::method(contents_shinychat, ellmer::ContentToolResult) <- function(content) {
  # Prepare base props
  props <- list(
    request_id = content@request@id,
    request_call = format(content@request, show = "call"),
    name = content@request@name,
    status = if (!is.null(content@error)) "error" else "success",
    show_request = tolower(!isFALSE(content@extra$display_tool_request))
  )

  # Add optional title if present
  if (!is.null(content@request@tool@annotations$title)) {
    props$title <- content@request@tool@annotations$title
  }

  # Add optional intent if present
  if (!is.null(content@request@arguments$.intent)) {
    props$intent <- content@request@arguments$.intent
  }

  display_props <- tool_result_display(content)
  props$value <- display_props$value
  props$value_type <- display_props$value_type

  names(props) <- gsub("_", "-", names(props))

  htmltools::tag(
    "shiny-tool-result",
    rlang::list2(!!!props, if (!is.null(display_props$deps)) display_props$deps)
  )
}

tool_result_display <- function(content) {
  # Default fallback
  res <- list(
    value = content@value,
    value_type = "code",
    deps = NULL
  )

  if (!is.null(content@error)) {
    res$value <- strip_ansi(content@error)
    return(res)
  }

  # Get display from extra data attached to the result
  display <- content@extra$display

  # If no display, return code value
  if (is.null(display)) {
    return(res)
  }

  is_html <-
    inherits(display, c("html", "shiny.tag", "shiny.tag.list")) ||
    (is.list(display) && !is.null(display$html))

  if (is_html) {
    html <- list(
      value = format(display),
      value_type = "html",
      deps = htmltools::findDependencies(display)
    )
    return(html)
  }

  is_md <-
    is.character(display) ||
    (is.list(display) && !is.null(display$markdown))

  if (is_md) {
    md <- list(
      value = paste(display, collapse = "\n"),
      value_type = "markdown",
      deps = NULL
    )
    return(md)
  }

  if (is.list(display) && !is.null(display$text)) {
    res$value <- display$text
    res$value_type <- "text"
  }

  res
}


S7::method(contents_shinychat, ellmer::Turn) <- function(content) {
  # Process all contents in the turn, filtering out empty results
  compact(map(content@contents, contents_shinychat))
}

S7::method(contents_shinychat, S7::new_S3_class(c("Chat", "R6"))) <- function(
  content
) {
  # Process turns with tool request/result consolidation
  turns <- map(content$get_turns(), function(turn) {
    # Turns containing only tool results are converted into assistant turns
    if (every(turn@contents, S7::S7_inherits, ellmer::ContentToolResult)) {
      turn@role <- "assistant"
      return(turn)
    }

    # Filter out tool requests as they'll be shown in results
    is_tool_request <- map_lgl(
      turn@contents,
      S7::S7_inherits,
      ellmer::ContentToolRequest
    )
    turn@contents <- turn@contents[!is_tool_request]
    turn
  })

  # Consolidate adjacent turns with the same role
  turns <- reduce(
    turns,
    .init = list(),
    function(acc, turn) {
      if (length(acc) == 0) {
        return(list(turn))
      }

      last_turn <- acc[[length(acc)]]
      if (identical(last_turn@role, turn@role)) {
        acc[[length(acc)]]@contents <- c(last_turn@contents, turn@contents)
        return(acc)
      }

      c(acc, list(turn))
    }
  )

  # Convert turns to messages
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
