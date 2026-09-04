#' Split tag content around elements with data-shinychat-react
#'
#' Elements WITH the attribute are emitted bare.
#' Consecutive elements WITHOUT the attribute are grouped into
#' <shiny-chat-raw-html> wrappers.
#'
#' @param content A tag, tagList, or other HTML content.
#' @return A list of tag children ready to be serialized.
#' @noRd
split_html_islands <- function(content) {
  # Convert to tags so custom classes (e.g., shinychat_tool_card)
  # resolve their data-shinychat-react attribute
  content <- htmltools::as.tags(content)

  if (inherits(content, "shiny.tag")) {
    if (has_react_attr(content)) {
      return(list(content))
    }
    return(list(htmltools::tag("shiny-chat-raw-html", list(content))))
  }

  if (inherits(content, "shiny.tag.list")) {
    children <- as.list(content)
  } else {
    return(list(htmltools::tag("shiny-chat-raw-html", list(content))))
  }

  if (length(children) == 0) {
    return(list())
  }

  is_react <- vapply(children, has_react_attr, logical(1))
  group_id <- cumsum(c(TRUE, diff(is_react) != 0))
  groups <- split(children, group_id)

  result <- list()
  for (group in groups) {
    if (has_react_attr(group[[1]])) {
      result <- c(result, group)
    } else {
      result <- c(result, list(htmltools::tag("shiny-chat-raw-html", group)))
    }
  }
  result
}

#' Split mixed content into ordered provenance runs
#'
#' Plain character values may contain model output and are untrusted.
#' HTML()-marked strings and tags are server-authored UI and trusted.
#'
#' @param content Content accepted by htmltools.
#' @return A list of lists containing `trusted` and `content`.
#' @noRd
split_content_by_trust <- function(content) {
  if (inherits(content, "shiny.tag.list")) {
    children <- as.list(content)
  } else {
    children <- list(content)
  }

  is_trusted <- vapply(
    children,
    function(child) !(is.character(child) && !inherits(child, "html")),
    logical(1)
  )
  if (length(children) == 0) {
    return(list(list(trusted = FALSE, content = "")))
  }

  group_id <- cumsum(c(TRUE, diff(is_trusted) != 0))
  groups <- split(children, group_id)
  unname(lapply(groups, function(group) {
    trusted <- !(is.character(group[[1]]) && !inherits(group[[1]], "html"))
    list(
      trusted = trusted,
      content = if (trusted) {
        do.call(htmltools::tagList, group)
      } else {
        paste0(unlist(group, use.names = FALSE), collapse = "")
      }
    )
  }))
}

has_react_attr <- function(child) {
  if (!inherits(child, "shiny.tag")) {
    return(FALSE)
  }
  !is.null(htmltools::tagGetAttribute(child, "data-shinychat-react"))
}
