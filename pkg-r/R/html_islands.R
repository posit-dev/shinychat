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
  if (inherits(content, "shiny.tag")) {
    if (has_react_attr(content)) {
      return(list(content))
    }
    return(list(htmltools::tag("shinychat-html", list(content))))
  }

  if (inherits(content, "shiny.tag.list")) {
    children <- as.list(content)
  } else {
    return(list(htmltools::tag("shinychat-html", list(content))))
  }

  result <- list()
  html_accum <- list()

  flush_html <- function() {
    if (length(html_accum) > 0) {
      result[[length(result) + 1]] <<-
        htmltools::tag("shinychat-html", html_accum)
      html_accum <<- list()
    }
  }

  for (child in children) {
    if (has_react_attr(child)) {
      flush_html()
      result[[length(result) + 1]] <- child
    } else {
      html_accum[[length(html_accum) + 1]] <- child
    }
  }

  flush_html()
  result
}

has_react_attr <- function(child) {
  if (!inherits(child, "shiny.tag")) {
    return(FALSE)
  }
  !is.null(child$attribs[["data-shinychat-react"]])
}
