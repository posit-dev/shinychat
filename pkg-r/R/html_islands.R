# One run of consecutive non-React children: trusted content that becomes a
# single island payload (a structured `html_block` further downstream).
new_island_item <- function(children) {
  structure(
    list(children = children),
    class = "shinychat_island"
  )
}

#' Split tag content around elements with data-shinychat-react
#'
#' Elements WITH the attribute are emitted bare (as tags). Consecutive
#' elements WITHOUT the attribute are grouped into typed `shinychat_island`
#' items (see `new_island_item()`).
#'
#' @param content A tag, tagList, or other HTML content.
#' @return A list of bare tags and `shinychat_island` items, in order.
#' @noRd
split_html_islands <- function(content) {
  # Convert to tags so custom classes resolve their data-shinychat-react
  # attribute.
  content <- htmltools::as.tags(content)

  if (inherits(content, "shiny.tag")) {
    if (has_react_attr(content)) {
      return(list(content))
    }
    return(list(new_island_item(list(content))))
  }

  if (inherits(content, "shiny.tag.list")) {
    children <- as.list(content)
  } else {
    return(list(new_island_item(list(content))))
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
      result <- c(result, list(new_island_item(group)))
    }
  }
  result
}

# One derived piece of trusted content: an island payload (becomes a
# structured `html_block`) or a residual string run. Mirrors Python's
# IslandBlockPart/IslandResidualPart.
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
#' Island items (`shinychat_island`) become block parts (rendered children
#' HTML + dependency objects); bare `data-shinychat-react` elements become
#' residual string runs (rendered bare, surrounded by blank lines so the
#' markdown parser treats block-level custom elements correctly, adjacent
#' runs coalesced).
#'
#' This is the single derivation shared by Chat (message content) and the
#' markdown stream so trusted non-string content becomes `html_block`
#' envelopes identically everywhere. Mirrors Python's `derive_island_parts()`.
#'
#' @param content A tag, tagList, or other HTML content.
#' @return A list of parts (`shinychat_island_block_part` or
#'   `shinychat_island_residual_part`), each with rendered `html` and raw
#'   `html_dependency` objects in `deps`.
#' @noRd
derive_island_parts <- function(content) {
  if (is.character(content) && !inherits(content, "html")) {
    stop(
      "derive_island_parts() requires trusted tag content; plain strings ",
      "are markdown and must be handled by the caller."
    )
  }
  # Wrap in with_current_theme() so theme-aware bslib content compiles
  # against the correct theme.
  with_current_theme({
    parts <- list()
    for (item in split_html_islands(content)) {
      if (inherits(item, "shinychat_island")) {
        rendered <- htmltools::renderTags(htmltools::tagList(!!!item$children))
        parts[[length(parts) + 1]] <- new_island_block_part(
          html = as.character(rendered$html),
          deps = rendered$dependencies
        )
      } else {
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

#' Render trusted content to a single HTML string via the island derivation
#'
#' For wire surfaces that cannot carry structured blocks (the greeting
#' payload, drawer content, static <shiny-chat-message> tags): island parts
#' contribute their rendered HTML directly and bare React elements
#' contribute their blank-line-wrapped residual runs. The whole string is
#' server-authored and travels with content_type "html".
#'
#' The payload is a single string rendered via innerHTML, so bare strings
#' are HTML-escaped. Mixed markdown+UI content needs a segments channel
#' (follow-up: shinychat#2dzc).
#'
#' @param content A tag, tagList, or other HTML content.
#' @return A list with `html` (character string) and `deps` (raw
#'   `html_dependency` objects; session-process or attach as appropriate).
#' @noRd
render_island_string <- function(content) {
  if (is.character(content) && !inherits(content, "html")) {
    rendered <- htmltools::renderTags(htmltools::tagList(content))
    return(list(html = as.character(rendered$html), deps = list()))
  }
  parts <- derive_island_parts(content)
  html <- paste0(
    vapply(parts, function(part) part$html, character(1)),
    collapse = ""
  )
  deps <- unlist(
    lapply(parts, function(part) part$deps),
    recursive = FALSE
  )
  list(html = html, deps = deps %||% list())
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
