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
  res <- htmltools::tag(
    "shinychat-tool-request",
    list(
      `data-tool-call-id` = content@id,
      name = content@name
    )
  )

  # The request element is inline so the streaming dot can appear inline next to it.
  # As a result, if there is text before the request, the request will appears
  # inline with that text, which is not what we want. To work around this, we
  # effectively add a newline before the request element.
  htmltools::tagList(htmltools::p(), res)
}

S7::method(contents_shinychat, ellmer::ContentToolResult) <- function(content) {
  request <- content@request
  if (is.null(request)) {
    # I guess we could display the value, but I'm not sure if this is even possible?
    rlang::abort(c(
      "Unable to display tool result since it does not appear to have a ",
      "corresponding tool request. Please report this issue."
    ))
  }

  if (inherits(content@error, "condition")) {
    error <- sanitized_chat_error(content@error)
  } else {
    error <- as.character(content@error)
  }

  if (!is.null(request@tool)) {
    annotations <- to_json_attr(request@tool@annotations)
  } else {
    annotations <- NULL
  }

  value <- capture.output(print(content@value))

  htmltools::tag(
    "shinychat-tool-result",
    list(
      `data-tool-call-id` = request@id,
      name = request@name,
      arguments = to_json_attr(request@arguments),
      value = paste(value, collapse = "\n"),
      error = error,
      annotations = annotations
    )
  )
}

S7::method(contents_shinychat, ellmer::Turn) <- function(content) {
  lapply(content@contents, contents_shinychat)
}

S7::method(contents_shinychat, S7::new_S3_class(c("Chat", "R6"))) <- function(
  content
) {
  # Workaround the problem that results from ellmer storing tool results in a
  # user turn, but when displayed, they should be part of the surrounding
  # assistant turn (not a separate user turn).
  #
  # This implementation currently assumes that:
  #  * Tool results are stored in a user turn, and when present, no other
  #    content types are present.
  #  * User turns that have at least one proceeding assistant turn.

  turns <- map(content$get_turns(), function(turn) {
    is_result <- map_lgl(
      turn@contents,
      S7::S7_inherits,
      ellmer::ContentToolResult
    )
    if (all(is_result) && sum(is_result) > 0) {
      turn@role <- "assistant"
    }
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

  lapply(turns, function(turn) {
    list(role = turn@role, content = contents_shinychat(turn))
  })
}


to_json_attr <- function(x, pretty = TRUE) {
  if (length(x) == 0) {
    return(NULL)
  }

  jsonlite::toJSON(
    x,
    auto_unbox = TRUE,
    pretty = pretty,
    force = TRUE,
    null = "null",
    dataframe = "rows"
  )
}
