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
  # Convert to tags so custom classes resolve their data-shinychat-react
  # attribute. (Tool blocks no longer go through this path — they are
  # `shinychat_block` objects handled directly by `chat_append_message`.)
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

# One derived piece of trusted content: an island payload (becomes a
# structured `html_block`) or a residual string run (stays a trusted string
# segment). Mirrors Python's IslandBlockPart/IslandResidualPart (kata#mhyd).
new_island_block_part <- function(html, deps) {
  structure(
    list(html = html, deps = deps),
    class = "shinychat_island_block_part"
  )
}

new_island_residual_part <- function(html, deps) {
  structure(
    list(html = html, deps = deps),
    class = "shinychat_island_residual_part"
  )
}

#' Walk split_html_islands() output into rendered parts
#'
#' Island wrappers (`<shiny-chat-raw-html>`) become block parts (rendered
#' children HTML + dependency objects); bare `data-shinychat-react` elements
#' become residual string runs (rendered bare, surrounded by blank lines so
#' the markdown parser treats block-level custom elements correctly, adjacent
#' runs coalesced).
#'
#' This is the single derivation shared by Chat (message content) and the
#' markdown stream (stream/output emission) so trusted non-string content
#' becomes `html_block` envelopes identically everywhere. Mirrors Python's
#' `derive_island_parts()` (kata#mhyd).
#'
#' @param content A tag, tagList, or other HTML content.
#' @return A list of parts (`shinychat_island_block_part` or
#'   `shinychat_island_residual_part`), each with rendered `html` and raw
#'   `html_dependency` objects in `deps`.
#' @noRd
derive_island_parts <- function(content) {
  # Wrap island splitting and tag rendering in with_current_theme() so
  # theme-aware bslib content renders/compiles deps against the correct
  # theme — matching the session-aware send path (process_ui wraps
  # processDeps in with_current_theme()) (roborev 1066, finding 3).
  with_current_theme({
    parts <- list()
    for (item in split_html_islands(content)) {
      if (
        inherits(item, "shiny.tag") &&
          identical(item$name, "shiny-chat-raw-html")
      ) {
        # Island wrapper: render its children (not the wrapper itself) as
        # the block's trusted HTML content.
        children <- as.list(item$children)
        rendered <- htmltools::renderTags(htmltools::tagList(!!!children))
        parts[[length(parts) + 1]] <- new_island_block_part(
          html = as.character(rendered$html),
          deps = rendered$dependencies
        )
      } else {
        # Bare React element: render it bare and keep it as a residual
        # string run, surrounded by blank lines.
        rendered <- htmltools::renderTags(item)
        run <- paste0("\n\n", as.character(rendered$html), "\n\n")
        last <- if (length(parts) > 0) parts[[length(parts)]] else NULL
        if (inherits(last, "shinychat_island_residual_part")) {
          last$html <- paste0(last$html, run)
          last$deps <- c(last$deps, rendered$dependencies)
          parts[[length(parts)]] <- last
        } else {
          parts[[length(parts) + 1]] <- new_island_residual_part(
            html = run,
            deps = rendered$dependencies
          )
        }
      }
    }
    parts
  })
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
