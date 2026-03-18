#' Split tag content around elements with data-shinychat-react
#'
#' Elements WITH the attribute are emitted bare.
#' Consecutive elements WITHOUT the attribute are grouped into
#' <shinychat-html> wrappers.
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
    return(list(htmltools::tag("shinychat-raw-html", list(content))))
  }

  if (inherits(content, "shiny.tag.list")) {
    children <- as.list(content)
  } else {
    return(list(htmltools::tag("shinychat-raw-html", list(content))))
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
      result <- c(result, list(htmltools::tag("shinychat-raw-html", group)))
    }
  }
  result
}

has_react_attr <- function(child) {
  if (!inherits(child, "shiny.tag")) {
    return(FALSE)
  }
  !is.null(htmltools::tagGetAttribute(child, "data-shinychat-react"))
}
