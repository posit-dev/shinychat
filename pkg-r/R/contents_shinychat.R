opt_shinychat_tool_display <- function() {
  choices <- c("none", "basic", "rich")

  opt <- getOption("shinychat.tool_display", default = NULL)
  if (!is.null(opt)) {
    opt <- arg_match(opt, choices, error_arg = "shinychat.tool_display")
    return(opt)
  }

  env <- Sys.getenv("SHINYCHAT_TOOL_DISPLAY", unset = "rich")
  arg_match(env, choices, error_arg = "SHINYCHAT_TOOL_DISPLAY")
}

#' Format ellmer content for shinychat
#'
#' @param content An [`ellmer::Content`] object.
#'
#' @return Returns text, HTML, or web component tags formatted for use in
#'   `chat_ui()`.
#'
#' @export
contents_shinychat <- S7::new_generic(
  "contents_shinychat",
  "content",
  function(content) {
    S7::S7_dispatch()
  }
)

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
  if (opt_shinychat_tool_display() == "none") {
    return(NULL)
  }

  props <- list(
    "request-id" = content@id,
    name = content@name,
    arguments = jsonlite::toJSON(content@arguments, auto_unbox = TRUE),
    intent = content@arguments$.intent
  )

  tool <- content@tool
  if (!is.null(tool)) {
    props$title <- tool@annotations$title
  }

  tagList(
    htmltools::tag("shiny-tool-request", props),
    chat_deps()
  )
}

S7::method(contents_shinychat, ellmer::ContentToolResult) <- function(content) {
  if (opt_shinychat_tool_display() == "none") {
    return(NULL)
  }

  if (is.null(content@request)) {
    cli::cli_abort(
      "`ContentToolResult` objects must have an associated `@request` property."
    )
  }

  content@extra$display <- ensure_content_display(content)

  # Prepare base props
  props <- list(
    request_id = content@request@id,
    request_call = "",
    name = content@request@name,
    status = if (tool_errored(content)) "error" else "success",
    show_request = if (!isFALSE(content@extra$display$show_request)) NA,
    intent = content@request@arguments$.intent,
    expanded = if (isTRUE(content@extra$display$open)) NA
  )

  icon_deps <- NULL
  tool <- content@request@tool

  # Let tool results override global tool properties
  if (!is.null(content@extra$display$title)) {
    props$title <- content@extra$display$title
  }
  if (!is.null(content@extra$display$icon)) {
    props$icon <- content@extra$display$icon
    icon_deps <- htmltools::findDependencies(props$icon)
  }

  if (!is.null(tool)) {
    # Format fails if tool is not present (ellmer v0.3.0, tidyverse/ellmer#691)
    props$request_call <- format(content@request, show = "call")

    props$title <- props$title %||% tool@annotations$title
    props$icon <- props$icon %||% tool@annotations$icon
    icon_deps <- icon_deps %||% htmltools::findDependencies(props$icon)
  } else {
    props$request_call <- jsonlite::toJSON(
      list(
        id = content@request@id,
        name = content@request@name,
        arguments = content@request@arguments
      ),
      auto_unbox = TRUE,
      pretty = 2
    )
  }

  props <- list2(!!!props, !!!tool_result_display(content))
  names(props) <- gsub("_", "-", names(props))

  # Get dependencies for the value because we store its HTML as an attribute
  # where `processDeps()` won't find it.
  deps <- htmltools::findDependencies(props$value)

  htmltools::tagList(
    htmltools::tag("shiny-tool-result", props),
    deps,
    icon_deps,
    chat_deps()
  )
}

ensure_content_display <- function(content) {
  display <- content@extra$display

  if (is.null(display) || opt_shinychat_tool_display() == "basic") {
    return(list())
  }

  invalid_display_fmt <- "Invalid {.code @extra$display} format for {.code ContentToolResult} from {.fn {content@request@name}} (call id: {content@request@id})."

  if (
    inherits(display, c("html", "shiny.tag", "shiny.tag.list", "htmlwidgets"))
  ) {
    cli::cli_warn(c(
      invalid_display_fmt,
      "i" = "To display HTML content for tool results in {.pkg shinychat}, create a tool result with {.code extra = list(display = list(html = ...))}.",
      "i" = "You can also use {.code markdown} or {.code text} items in {.code display} to show Markdown or plain text, respectively."
    ))
    return(list())
  }

  expected_fields <- c(
    "html",
    "markdown",
    "text",
    "show_request",
    "open",
    "title"
  )

  if (!is.list(display)) {
    cli::cli_warn(c(
      invalid_display_fmt,
      "x" = "Expected a list with fields {.or {.var {expected_fields}}}, not {.obj_type_friendly {display}}."
    ))
    return(list())
  }

  display
}

tool_result_display <- function(content) {
  display <- content@extra$display

  has_display <- !is.null(display) && is.list(display) && length(display) > 0
  use_basic_display <- opt_shinychat_tool_display() == "basic"

  if (tool_errored(content) || use_basic_display || !has_display) {
    return(list(value = tool_string(content), value_type = "code"))
  }

  if (is.list(display)) {
    has_type <- intersect(c("html", "markdown", "text"), names(display))
    if (length(has_type) > 0) {
      value_type <- has_type[1]
      return(list(value = display[[value_type]], value_type = value_type))
    }
  }

  list(value = tool_string(content), value_type = "code")
}

# Copied from
# https://github.com/tidyverse/ellmer/blob/11cf1696/R/content.R#L292-L308
tool_errored <- function(x) !is.null(x@error)
tool_error_string <- function(x) {
  if (inherits(x@error, "condition")) conditionMessage(x@error) else x@error
}
tool_string <- function(x) {
  if (tool_errored(x)) {
    # Changed from original: if tool errored, just return the error message
    strip_ansi(tool_error_string(x))
  } else if (inherits(x@value, "AsIs")) {
    x@value
  } else if (inherits(x@value, "json")) {
    x@value
  } else if (is.character(x@value)) {
    paste(x@value, collapse = "\n")
  } else {
    jsonlite::toJSON(x@value, auto_unbox = TRUE, pretty = 2)
  }
}


S7::method(contents_shinychat, ellmer::Turn) <- function(content) {
  # Process all contents in the turn, filtering out empty results
  compact(map(content@contents, contents_shinychat))
}

S7::method(contents_shinychat, S7::new_S3_class(c("Chat", "R6"))) <- function(
  content
) {
  tools <- content$get_tools()

  # Process turns with tool request/result consolidation
  turns <- map(content$get_turns(), function(turn) {
    turn@contents <- map(turn@contents, function(x) {
      if (!S7::S7_inherits(x, ellmer::ContentToolResult)) {
        return(x)
      }
      if (!is.null(x@request@tool)) {
        return(x)
      }
      if (x@request@name %in% names(tools)) {
        x@request@tool <- tools[[x@request@name]]
      }
      x
    })

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
