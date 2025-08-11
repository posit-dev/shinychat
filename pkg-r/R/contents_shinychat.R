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
#' @section Extending `contents_shinychat()`:
#'
#' You can extend `contents_shinychat()` to handle custom content types in your
#' application. `contents_shinychat()` is [an S7 generic][S7::new_generic]. If
#' you haven't worked with S7 before, you can learn more about S7 classes,
#' generics and methods in the [S7
#' documentation](https://rconsortium.github.io/S7/articles/S7.html).
#'
#' We'll work through a short example creating a custom display for the results
#' of a tool that gets local weather forecasts. We first need to create a custom
#' class that extends [ellmer::ContentToolResult].
#'
#' ```r
#' library(ellmer)
#'
#' WeatherToolResult <- S7::new_class(
#'   "WeatherToolResult",
#'   parent = ContentToolResult,
#'   properties = list(
#'     location_name = S7::class_character
#'   )
#' )
#' ```
#'
#' Next, we'll create a simple [ellmer::tool()] that gets the weather forecast
#' for a location and returns our custom `WeatherToolResult` class. The custom
#' class works just like a regular `ContentToolResult`, but it has an additional
#' `location_name` property.
#'
#' ```r
#' get_weather_forecast <- tool(
#'   function(lat, lon, location_name) {
#'     WeatherToolResult(
#'       weathR::point_tomorrow(lat, lon, short = FALSE),
#'       location_name = location_name
#'     )
#'   },
#'   name = "get_weather_forecast",
#'   description = "Get the weather forecast for a location.",
#'   arguments = list(
#'     lat = type_number("Latitude"),
#'     lon = type_number("Longitude"),
#'     location_name = type_string("Name of the location for display to the user")
#'   )
#' )
#' ```
#'
#' Finally, we can extend `contents_shinychat()` to render our custom content
#' class for display in the chat interface. The basic process is to define a
#' `contents_shinychat()` external generic and then implement a method for your
#' custom class.
#'
#' ```r
#' contents_shinychat <- S7::new_external_generic(
#'   package = "shinychat",
#'   name = "contents_shinychat",
#'   dispatch_args = "contents"
#' )
#'
#' S7::method(contents_shinychat, WeatherToolResult) <- function(content) {
#'   # Your custom rendering logic here
#' }
#' ```
#'
#' You can use this pattern to completely customize how the content is displayed
#' inside shinychat by returning HTML objects directly from this method.
#'
#' You can also use this pattern to build upon the default shinychat display for
#' tool requests and results. By using [S7::super()], you can create the
#' object shinychat uses for tool results (or tool requests), and then modify it
#' to suit your needs.
#'
#' ```r
#' S7::method(contents_shinychat, WeatherToolResult) <- function(content) {
#'   # Call the super method for ContentToolResult to get shinychat's defaults
#'   res <- contents_shinychat(S7::super(content, ContentToolResult))
#'
#'   # Then update the result object with more specific content
#'   # In this case, we render the tool result dataframe as a {gt} table...
#'   res$value <- gt::as_raw_html(gt::gt(content@value))
#'   res$value_type <- "html"
#'   # ...and update the tool result title to include the location name
#'   res$title <- paste("Weather Forecast for", content@location_name)
#'
#'   res
#' }
#' ```
#'
#' Note that you do **not** need to create a new class or extend
#' `contents_shinychat()` to customize the tool display. Rather, you can use the
#' strategies discussed in the [Tool Calling UI
#' article](https://posit-dev.github.io/shinychat/r/article/tool-ui.html) to
#' customize the tool request and result display by providing a `display` list
#' in the `extra` argument of the tool result.
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

new_tool_card <- function(type, request_id, tool_name, ...) {
  type <- arg_match(type, c("request", "result"))

  classes <- c(
    paste0("shinychat_tool_", type),
    "shinychat_tool_card"
  )

  dots <- dots_list(
    type = type,
    request_id = request_id,
    tool_name = tool_name,
    ...
  )

  structure(dots, class = classes)
}

#' @export
as.tags.shinychat_tool_card <- function(x, ...) {
  tag_name <- switch(
    x$type,
    request = "shiny-tool-request",
    result = "shiny-tool-result",
    cli::cli_abort(
      "shinychat tool card must have type {.val request} or {.val result}, not {.val {x$type}}."
    )
  )

  if (identical(x$value_type, "html") && !is.character(x$value)) {
    x$value <- as.tags(x$value)
  }
  if (!is.null(x$icon) && !is.character(x$icon)) {
    x$icon <- as.tags(x$icon)
  }

  names(x) <- gsub("_", "-", names(x))

  deps <- list(
    htmltools::findDependencies(x$value),
    htmltools::findDependencies(x$icon),
    chat_deps()
  )

  htmltools::tag(
    tag_name,
    dots_list(type = NULL, !!!x, !!!deps, .homonyms = "first")
  )
}

#' @export
format.shinychat_tool_card <- function(x, ...) {
  format(as.tags(x), ...)
}

#' @export
print.shinychat_tool_card <- function(x, ...) {
  tags <- as.tags(x)
  class(tags) <- c("bslib_fragment", class(tags))
  attr(tags, "bslib_page") <- function(...) {
    bslib::page_fluid(
      htmltools::div(
        class = "m-3",
        ...
      )
    )
  }
  print(tags, ...)
  invisible(x)
}

S7::method(contents_shinychat, ellmer::ContentToolRequest) <- function(
  content
) {
  if (opt_shinychat_tool_display() == "none") {
    return(NULL)
  }

  tool <- content@tool

  new_tool_card(
    "request",
    request_id = content@id,
    tool_name = content@name,
    arguments = jsonlite::toJSON(content@arguments, auto_unbox = TRUE),
    intent = content@arguments$.intent,
    tool_title = if (!is.null(tool)) tool@annotations$title
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

  display <- get_tool_result_display(content)
  annotations <- list()

  if (!is.null(content@request@tool)) {
    annotations <- content@request@tool@annotations
    request_call <- format(content@request, show = "call")
  } else {
    # formatting the request fails if tool is not present
    # (ellmer v0.3.0, tidyverse/ellmer#691)
    request_call <- jsonlite::toJSON(
      list(
        id = content@request@id,
        name = content@request@name,
        arguments = content@request@arguments
      ),
      auto_unbox = TRUE,
      pretty = 2
    )
  }

  new_tool_card(
    "result",
    request_id = content@request@id,
    request_call = request_call,
    status = if (tool_errored(content)) "error" else "success",
    tool_name = content@request@name,
    tool_title = display$title %||% annotations$title,
    icon = display$icon %||% annotations$icon,
    intent = content@request@arguments$.intent,
    show_request = if (!isFALSE(display$show_request)) NA,
    expanded = if (isTRUE(display$open)) NA,
    !!!tool_result_display(content, display)
  )
}

get_tool_result_display <- function(content) {
  display <- content@extra$display
  request <- content@request

  if (is.null(display) || opt_shinychat_tool_display() == "basic") {
    return(list())
  }

  invalid_display_fmt <- "Invalid {.code @extra$display} format for {.code ContentToolResult} from {.fn {request@name}} (call id: {request@id})."

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

  # fmt: skip
  expected_fields <- c(
    "html", "markdown", "text", "show_request", "open", "title", "icon"
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

tool_result_display <- function(content, display = NULL) {
  display <- display %||% content@extra$display

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
