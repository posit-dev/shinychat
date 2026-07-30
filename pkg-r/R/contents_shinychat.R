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
#' article](https://posit-dev.github.io/shinychat/r/articles/tool-ui.html) to
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

S7::method(contents_shinychat, ContentSlashCommand) <- function(content) {
  trimws(paste0("/", content@command, " ", content@user_text))
}

S7::method(contents_shinychat, ellmer::ContentText) <- function(content) {
  content@text
}

S7::method(contents_shinychat, ellmer::ContentThinking) <- function(content) {
  structure(content@thinking, class = "shinychat_thinking")
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
  if (!is.null(x$footer) && !is.character(x$footer)) {
    x$footer <- as.tags(x$footer)
  }

  names(x) <- gsub("_", "-", names(x))

  deps <- list(
    htmltools::findDependencies(x$value),
    htmltools::findDependencies(x$icon),
    htmltools::findDependencies(x$footer),
    shinychat_deps()
  )

  tag <- htmltools::tag(
    tag_name,
    dots_list(type = NULL, !!!x, !!!deps, .homonyms = "first")
  )
  htmltools::tagAppendAttributes(tag, `data-shinychat-react` = NA)
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

#' @exportS3Method knitr::knit_print
knit_print.shinychat_tool_card <- function(x, ...) {
  knitr::knit_print(as.tags(x))
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
    intent = content@arguments[["_intent"]],
    tool_title = if (!is.null(tool)) tool@annotations$title,
    grouping = if (!is.null(tool)) as_grouping(tool@annotations$grouping)
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
  grouping <- NULL

  if (!is.null(content@request@tool)) {
    annotations <- content@request@tool@annotations
    grouping <- as_grouping(annotations$grouping)
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
    intent = content@request@arguments[["_intent"]],
    show_request = if (!isFALSE(display$show_request)) NA,
    expanded = if (isTRUE(display$open)) NA,
    full_screen = if (isTRUE(display$full_screen)) NA,
    footer = display$footer,
    grouping = grouping,
    label = display$label,
    value_preview = display$value_preview,
    !!!tool_result_value(content, display)
  )
}

#' Customize how a tool result is displayed
#'
#' `tool_result_display()` creates an object you can assign to the
#' `display` item of the `extra` argument of an [`ellmer::ContentToolResult`]
#' to customize how shinychat displays the tool result to the user, while
#' keeping the underlying `value` sent to the model unchanged.
#'
#' @param title The title to display in the header of the tool result.
#' @param icon An icon to display in the header (alongside the title). Can be
#'   a character string or HTML content (e.g. from [htmltools::tags]).
#' @param html Custom HTML content (to use in place of the default result
#'   display).
#' @param markdown Custom Markdown string (to use in place of the default
#'   result display).
#' @param text Custom plain text string (to use in place of the default
#'   result display).
#' @param show_request Whether to show the tool request inside the tool
#'   result container.
#' @param open Whether or not the tool result details are expanded by
#'   default.
#' @param full_screen Whether or not to display a fullscreen toggle button on
#'   the card.
#' @param footer Optional HTML content to display in the card footer (below
#'   the card body).
#' @param label A short, per-call identifying value shown alongside the tool
#'   title (e.g. a filename or query). Distinguishes this call from other
#'   calls to the same tool. Without one, shinychat falls back to the call's
#'   own `title` (when it differs from the group's), then a short preview of
#'   the call's arguments, then the tool name.
#' @param value_preview A terse, per-call preview of the tool result, shown
#'   in the condensed view before the full result is expanded.
#'
#' @return An object of class `shinychat_tool_result_display`, for use as
#'   `extra = list(display = tool_result_display(...))` when creating an
#'   [`ellmer::ContentToolResult`].
#'
#' @examplesIf rlang::is_installed("ellmer")
#' library(ellmer)
#'
#' get_current_weather <- function() {
#'   ContentToolResult(
#'     value = "72 degrees and sunny",
#'     extra = list(
#'       display = tool_result_display(
#'         title = "Current weather",
#'         markdown = "It's **72°F** and sunny."
#'       )
#'     )
#'   )
#' }
#'
#' @family tool display
#' @export
tool_result_display <- function(
  title = NULL,
  icon = NULL,
  html = NULL,
  markdown = NULL,
  text = NULL,
  show_request = TRUE,
  open = FALSE,
  full_screen = FALSE,
  footer = NULL,
  label = NULL,
  value_preview = NULL
) {
  as_tool_result_display(
    compact(list(
      title = title,
      icon = icon,
      html = html,
      markdown = markdown,
      text = text,
      show_request = show_request,
      open = open,
      full_screen = full_screen,
      footer = footer,
      label = label,
      value_preview = value_preview
    ))
  )
}

# fmt: skip
tool_result_display_fields <- c(
  "title",
  "icon",
  "html",
  "markdown",
  "text",
  "show_request",
  "open",
  "full_screen",
  "footer",
  "label",
  "value_preview"
)

# Fields that are rendered as HTML and therefore accept a string *or* tag-like
# content (see `as.tags.shinychat_tool_card()`).
tool_result_display_html_fields <- c("title", "icon", "html", "footer")

# Fields that end up as plain-text tag attributes.
tool_result_display_string_fields <- c(
  "markdown",
  "text",
  "label",
  "value_preview"
)

# Fields serialized via `isTRUE()`/`isFALSE()`, where a non-logical value
# silently produces the opposite of the intended behavior.
tool_result_display_flag_fields <- c("show_request", "open", "full_screen")

is_tag_like <- function(x) {
  inherits(x, c("html", "shiny.tag", "shiny.tag.list", "htmlwidget"))
}

tool_result_display_field_is_valid <- function(field, value) {
  if (field %in% tool_result_display_flag_fields) {
    is_bool(value)
  } else if (field %in% tool_result_display_html_fields) {
    is_string(value) || is_tag_like(value)
  } else {
    is_string(value)
  }
}

tool_result_display_field_expects <- function(field) {
  if (field %in% tool_result_display_flag_fields) {
    cli::format_inline("{.code TRUE} or {.code FALSE}")
  } else if (field %in% tool_result_display_html_fields) {
    "a single string or HTML content"
  } else {
    "a single string"
  }
}

# Coerce a bare list (or an existing `shinychat_tool_result_display`) into a
# validated `shinychat_tool_result_display` object. Unknown or invalid fields
# are dropped with a warning; this never aborts, so a badly-formed `display`
# degrades to the default rendering rather than breaking the chat turn.
as_tool_result_display <- function(display, error_context = NULL) {
  if (inherits(display, "shinychat_tool_result_display")) {
    return(display)
  }

  if (!is.list(display)) {
    cli::cli_warn(
      c(
        error_context,
        "x" = "Expected a list with fields {.or {.var {tool_result_display_fields}}}, not {.obj_type_friendly {display}}."
      )
    )
    return(structure(list(), class = "shinychat_tool_result_display"))
  }

  unknown <- setdiff(names(display), tool_result_display_fields)
  if (length(unknown) > 0) {
    cli::cli_warn(
      c(
        error_context,
        "x" = "Unrecognized field{?s} {.field {unknown}} in {.code display}; ignoring.",
        "i" = "Expected fields: {.or {.var {tool_result_display_fields}}}."
      )
    )
    display <- display[setdiff(names(display), unknown)]
  }

  known <- intersect(tool_result_display_fields, names(display))
  invalid <- known[
    !map_lgl(known, function(field) {
      tool_result_display_field_is_valid(field, display[[field]])
    })
  ]
  if (length(invalid) > 0) {
    bullets <- map_chr(invalid, function(field) {
      cli::format_inline(
        "{.field {field}} must be {tool_result_display_field_expects(field)}, not {.obj_type_friendly {display[[field]]}}; ignoring."
      )
    })
    cli::cli_warn(
      c(
        error_context,
        set_names(bullets, rep("x", length(bullets)))
      )
    )
    display <- display[setdiff(names(display), invalid)]
  }

  structure(display, class = "shinychat_tool_result_display")
}

get_tool_result_display <- function(content) {
  display <- content@extra$display
  request <- content@request

  if (is.null(display) || opt_shinychat_tool_display() == "basic") {
    return(as_tool_result_display(list()))
  }

  invalid_display_fmt <- cli::format_inline(
    "Invalid {.code @extra$display} format for {.code ContentToolResult} from {.fn {request@name}} (call id: {request@id})."
  )

  if (
    inherits(display, c("html", "shiny.tag", "shiny.tag.list", "htmlwidgets"))
  ) {
    cli::cli_warn(
      c(
        invalid_display_fmt,
        "i" = "To display HTML content for tool results in {.pkg shinychat}, create a tool result with {.code extra = list(display = list(html = ...))}.",
        "i" = "You can also use {.code markdown} or {.code text} items in {.code display} to show Markdown or plain text, respectively."
      )
    )
    return(as_tool_result_display(list()))
  }

  as_tool_result_display(display, error_context = invalid_display_fmt)
}

# Validate a tool annotation's `grouping` value, ignoring anything unexpected.
as_grouping <- function(x) {
  if (!is.character(x) || length(x) != 1 || !x %in% c("none", "tool", "all")) {
    return(NULL)
  }
  x
}

tool_result_value <- function(content, display = NULL) {
  display <- display %||% content@extra$display

  has_display <- !is.null(display) && is.list(display) && length(display) > 0
  use_basic_display <- opt_shinychat_tool_display() == "basic"

  if (tool_errored(content) || use_basic_display || !has_display) {
    return(tool_default_display(content))
  }

  if (is.list(display)) {
    has_type <- intersect(c("html", "markdown", "text"), names(display))
    if (length(has_type) > 0) {
      value_type <- has_type[1]
      return(list(value = display[[value_type]], value_type = value_type))
    }
  }

  tool_default_display(content)
}

# Copied from
# https://github.com/tidyverse/ellmer/blob/11cf1696/R/content.R#L292-L308
tool_errored <- function(x) !is.null(x@error)
tool_error_string <- function(x) {
  if (inherits(x@error, "condition")) conditionMessage(x@error) else x@error
}
tool_string_value <- function(x) {
  if (inherits(x@value, "AsIs")) {
    x@value
  } else if (inherits(x@value, "json")) {
    x@value
  } else if (is.character(x@value)) {
    paste(x@value, collapse = "\n")
  } else {
    jsonlite::toJSON(x@value, auto_unbox = TRUE, pretty = 2, force = TRUE)
  }
}

is_content_extra <- function(x) {
  is_content_image(x) || S7::S7_inherits(x, ellmer::ContentPDF)
}

is_content_image <- function(x) {
  S7::S7_inherits(x, ellmer::ContentImage)
}

as_content_extra_item <- function(x) {
  if (S7::S7_inherits(x, ellmer::ContentImageRemote)) {
    list(type = "image", src = x@url)
  } else if (S7::S7_inherits(x, ellmer::ContentImageInline)) {
    list(type = "image", src = paste0("data:", x@type, ";base64,", x@data))
  } else if (S7::S7_inherits(x, ellmer::ContentPDF)) {
    list(type = "pdf", filename = x@filename %||% "document.pdf")
  }
}

is_content <- function(x) {
  S7::S7_inherits(x, ellmer::Content)
}

as_content_extra_item_or_text <- function(x) {
  if (is_content_extra(x)) {
    as_content_extra_item(x)
  } else if (S7::S7_inherits(x, ellmer::ContentText)) {
    list(type = "text", value = x@text, value_type = "markdown")
  } else {
    list(type = "text", value = as.character(x), value_type = "markdown")
  }
}

tool_default_display <- function(content) {
  value <- content@value

  if (tool_errored(content)) {
    return(
      list(
        value = strip_ansi(tool_error_string(content)),
        value_type = "code"
      )
    )
  }

  if (is_content_extra(value)) {
    return(
      list(
        value = jsonlite::toJSON(
          list(as_content_extra_item(value)),
          auto_unbox = TRUE
        ),
        value_type = "content_extra"
      )
    )
  }

  if (is.list(value) && some(value, is_content)) {
    items <- map(value, as_content_extra_item_or_text)
    return(
      list(
        value = jsonlite::toJSON(items, auto_unbox = TRUE),
        value_type = "content_extra"
      )
    )
  }

  list(value = tool_string_value(content), value_type = "code")
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
      if (packageVersion("ellmer") >= "0.3.2.9000") {
        turn <- ellmer::AssistantTurn(turn@contents)
      } else {
        turn@role <- "assistant"
      }
      return(turn)
    }

    # Tool requests are kept (not filtered): once adjacent same-role turns are
    # consolidated below, each request lands in the same message as its result,
    # so the client pairs them by request-id and the result inherits the
    # request's arguments. The paired request is then hidden in the condensed
    # view (its result supersedes it).
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
