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
#' For most tool-result customization, use [tool_result_display()] in the
#' result's `extra = list(display = ...)`. It keeps shinychat's compact activity
#' row and drill-down card while letting you set a title, label, result preview,
#' and rich card content. The [Tool Calling UI
#' article](https://posit-dev.github.io/shinychat/r/articles/tool-ui.html)
#' describes that recommended path.
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
#' Finally, define the external generic and implement a method for your custom
#' class:
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
#' Use [S7::super()] when you want to extend shinychat's default card. The
#' resulting output still participates in the normal compact activity row and
#' drill-down card:
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
#'   res$title <- paste("Got weather forecast for", content@location_name)
#'   res$label <- content@location_name
#'   res$value_preview <- paste(nrow(content@value), "hourly readings")
#'
#'   res
#' }
#' ```
#'
#' Alternatively, return arbitrary HTML or Shiny UI directly from the method to
#' replace the default card completely. While the tool runs, shinychat still
#' shows its activity row. When the custom result settles, shinychat renders that
#' UI as standalone output and removes the call from the activity row.
#'
#' This extension point is for fully custom standalone output. To customize the
#' default card, use [tool_result_display()] instead of constructing a generic
#' `display` list yourself.
#'
#' @param content An [`ellmer::Content`] object.
#'
#' @return Returns text, HTML, or web component tags formatted for use in
#'   `chat_ui()`.
#'
#' @export
contents_shinychat <- new_generic(
  "contents_shinychat",
  "content",
  function(content) {
    S7_dispatch()
  }
)

method(contents_shinychat, ellmer::Content) <- function(content) {
  # Fall back to html or markdown
  html <- ellmer::contents_html(content)
  if (!is.null(html)) {
    shiny::HTML(html)
  } else {
    ellmer::contents_markdown(content)
  }
}

method(contents_shinychat, ContentSlashCommand) <- function(content) {
  trimws(paste0("/", content@command, " ", content@user_text))
}

method(contents_shinychat, ellmer::ContentText) <- function(content) {
  content@text
}

method(contents_shinychat, ellmer::ContentThinking) <- function(content) {
  structure(content@thinking, class = "shinychat_thinking")
}

ellmer_web_content_available <- function(
  methods,
  exports = getNamespaceExports("ellmer")
) {
  all(c("WebSource", names(methods)) %in% exports)
}

new_web_block <- function(type, ...) {
  classes <- c(
    paste0("shinychat_web_", sub("^web_", "", type)),
    "shinychat_block"
  )

  dots <- dots_list(
    type = type,
    version = 1L,
    ...
  )
  # Omit NULL optional fields (e.g. a missing provider search id) while
  # keeping empty-but-valid values like `sources = list()`.
  dots <- dots[!vapply(dots, is.null, logical(1))]

  structure(dots, class = classes)
}

contents_shinychat_search_request <- function(content) {
  if (opt_shinychat_tool_display() == "none") {
    return(NULL)
  }

  # Providers that key their search calls (Anthropic, OpenAI) keep the id
  # in the raw block in extra; the client pairs results against it.
  new_web_block("web_search", query = content@query, id = content@extra$id)
}

contents_shinychat_search_response <- function(content) {
  if (opt_shinychat_tool_display() == "none") {
    return(NULL)
  }

  sources <- lapply(content@sources, web_source_record)
  sources <- Filter(Negate(is.null), sources)

  new_web_block(
    "web_search_results",
    sources = sources,
    search_id = content@extra$tool_use_id
  )
}

contents_shinychat_fetch_request <- function(content) {
  NULL
}

contents_shinychat_fetch_response <- function(content) {
  if (opt_shinychat_tool_display() == "none") {
    return(NULL)
  }

  url <- content@url
  if (
    !identical(content@status, "success") ||
      is.null(url) ||
      (is.character(url) && length(url) == 1 && is.na(url))
  ) {
    return(NULL)
  }

  new_web_block("web_fetch", url = url, status = content@status)
}

contents_shinychat_citation <- function(content) {
  if (opt_shinychat_tool_display() == "none") {
    return(NULL)
  }

  source <- content@source
  if (!S7::S7_inherits(source, getExportedValue("ellmer", "WebSource"))) {
    return(NULL)
  }
  if (is.null(source@url)) {
    return(NULL)
  }

  # Keep citation asides in markdown so grounded-text processing can match them.
  aside <- as.character(
    htmltools::tag(
      "shiny-aside",
      list(
        `data-citation` = NA,
        url = source@url,
        `grounded-span` = content@grounded_span,
        `cited-quote` = content@cited_quote,
        htmltools::tag(
          "a",
          list(
            href = source@url,
            source@title %||% source@url
          )
        )
      )
    )
  )

  # Citations also ride their own block so the client can pair them with
  # the search on both the stream and replay paths.
  citations <- new_web_block(
    "web_search_citations",
    sources = list(web_source_record(source))
  )

  structure(list(aside, citations), class = "shinychat_content_splice")
}

# Splice multi-item method results into a flat content list (a citation
# yields an aside string plus a web_search_citations block).
flatten_content_splices <- function(content) {
  out <- list()
  for (item in content) {
    if (inherits(item, "shinychat_content_splice")) {
      out <- c(out, unclass(item))
    } else {
      out[[length(out) + 1]] <- item
    }
  }
  out
}

ellmer_web_content_methods <- function() {
  list(
    ContentToolRequestSearch = contents_shinychat_search_request,
    ContentToolResponseSearch = contents_shinychat_search_response,
    ContentToolRequestFetch = contents_shinychat_fetch_request,
    ContentToolResponseFetch = contents_shinychat_fetch_response,
    ContentCitation = contents_shinychat_citation
  )
}

register_ellmer_web_content_methods <- function() {
  methods <- ellmer_web_content_methods()

  if (!ellmer_web_content_available(methods)) {
    return(invisible())
  }

  for (class_name in names(methods)) {
    class <- getExportedValue("ellmer", class_name)
    S7::method(contents_shinychat, class) <- methods[[class_name]]
  }

  invisible()
}

web_source_record <- function(source) {
  url <- source@url
  if (is.null(url) || (is.character(url) && length(url) == 1 && is.na(url))) {
    return(NULL)
  }

  record <- list(url = url)
  title <- source@title
  if (
    !is.null(title) &&
      !(is.character(title) && length(title) == 1 && is.na(title))
  ) {
    record$title <- title
  }
  record
}

rlang::on_load(register_ellmer_web_content_methods())

new_tool_card <- function(type, request_id, tool_name, ...) {
  type <- arg_match(type, c("tool_request", "tool_result"))

  classes <- c(
    paste0("shinychat_tool_", sub("^tool_", "", type)),
    # Retained for console/Rmd display method dispatch; the chat wire
    # path keys off `shinychat_block`.
    "shinychat_tool_card",
    "shinychat_block"
  )

  dots <- dots_list(
    type = type,
    version = 1L,
    request_id = request_id,
    tool_name = tool_name,
    ...
  )

  structure(dots, class = classes)
}

# Resolve definition-level tool annotations once, at the boundary between
# ellmer content and shinychat's tool cards. Result display metadata is
# intentionally handled separately because it can override title and icon.
shinychat_tool_annotations <- function(tool) {
  if (is.null(tool)) {
    return(list(title = NULL, icon = NULL, grouping = NULL))
  }

  annotations <- tool@annotations %||% list()
  list(
    title = annotations$title,
    icon = annotations$icon,
    grouping = as_grouping(annotations$grouping)
  )
}

# A `contents_shinychat()` method on a `ContentToolResult` subclass may
# return arbitrary tags instead of shinychat's own tool card (see the
# `method(contents_shinychat, ...)` examples above). That leaves no
# structured `tool_result` block in the transcript at all, so the client
# — which derives "this call finished" from that block's presence — has
# nothing to key off of and the request row spins forever. Wrap the
# author's tags in a real block carrying only the fields needed to pair
# a result with its request; everything else about the row (title, icon,
# footer, ...) is the author's own UI to manage.
#
# Detection is by artifact, not dispatch: `new_tool_card()` marks its output
# with the `shinychat_block` class, and that class survives the
# documented `S7::super()` extend pattern (the author gets shinychat's own
# card back and only mutates fields on it), so that pattern correctly reads
# as *not* custom. Anything else returned for a `ContentToolResult` is
# custom UI and gets wrapped.
wrap_custom_tool_result <- function(content, msg) {
  if (
    !S7_inherits(content, ellmer::ContentToolResult) ||
      inherits(msg, "shinychat_block") ||
      is.null(msg)
  ) {
    return(msg)
  }

  # A custom `contents_shinychat()` method bypasses the base method's check
  # that `@request` is present, so it can reach this point with nothing to
  # pair a result against. With no request there is no wrap to make; emit
  # the author's tags as-is, same as before this feature existed.
  if (is.null(content@request)) {
    return(msg)
  }

  annotations <- shinychat_tool_annotations(content@request@tool)

  if (is.character(msg) && !inherits(msg, "html")) {
    value_str <- as.character(msg)
    deps <- list()
  } else {
    rendered <- render_html_field(msg)
    value_str <- rendered$html
    deps <- rendered$deps
  }

  block <- new_tool_card(
    "tool_result",
    request_id = content@request@id,
    tool_name = content@request@name,
    # Locked: the author is assumed to present the error state inside their
    # own UI, so a failed custom call is wrapped exactly like a successful
    # one; only the request-pairing signal matters here.
    status = if (tool_errored(content)) "error" else "success",
    grouping = annotations$grouping,
    value = value_str,
    # Mirror the content mode the message would have been appended with had
    # it not been wrapped, so wrapping never changes how the author's output
    # renders. A bare character vector is markdown (`chat_append_message()`
    # treats anything outside its `is_html` class list that way), and
    # re-labelling it `"html"` would both drop markdown formatting and move
    # the string from the client's markdown pipeline -- inert React elements
    # -- onto `RawHTML`'s live `innerHTML`, where event-handler attributes
    # fire. `shiny::HTML()` is character *and* HTML, hence the class check.
    value_type = if (is.character(msg) && !inherits(msg, "html")) {
      "markdown"
    } else {
      "html"
    },
    show_request = FALSE,
    # Internal provenance marker only ("shinychat wrapped an author's custom
    # output"), not part of any author-facing API and not surfaced by
    # `tool_result_display()`. What the client does with this fact is the
    # client's own decision and stays free to change independently of this
    # wrap.
    custom_display = TRUE
  )
  if (length(deps) > 0) {
    attr(block, "shinychat_html_deps") <- deps
  }
  block
}

# `contents_shinychat()` plus the custom-result wrap. Every internal caller that
# needs routable shinychat content goes through this boundary, so a caller
# cannot accidentally convert a custom result without its pairing element.
#
# Safe to map over any content object: `wrap_custom_tool_result()` returns its
# input untouched for everything except a `ContentToolResult` whose method
# returned something other than shinychat's own tool card. It is also
# idempotent, since a wrapped result *is* a `shinychat_block` and so fails
# the wrap's own guard on a second pass.
contents_shinychat_wrapped <- function(content) {
  if (!S7_inherits(content, ellmer::Content)) {
    return(content)
  }

  wrap_custom_tool_result(content, contents_shinychat(content))
}

# Render a tag-like or HTML() value to an HTML string, collecting deps.
# Mirrors Python's `TagList(...).render()`.
render_html_field <- function(x) {
  if (is.null(x)) {
    return(list(html = NULL, deps = list()))
  }
  if (is.character(x) && !inherits(x, "html")) {
    return(list(html = as.character(x), deps = list()))
  }
  rendered <- htmltools::renderTags(x)
  list(
    html = as.character(rendered$html),
    deps = rendered$dependencies
  )
}

# Build the old `<shiny-tool-request>`/`<shiny-tool-result>` tags for
# console/Rmd display only (format/print/knit_print).
tool_card_as_tags <- function(x) {
  tag_name <- switch(
    x$type,
    tool_request = "shiny-tool-request",
    tool_result = "shiny-tool-result",
    cli::cli_abort(
      "shinychat tool card must have type {.val tool_request} or {.val tool_result}, not {.val {x$type}}."
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
  # The wire field is `title`; the static markup attribute is `tool-title`.
  names(x)[names(x) == "title"] <- "tool-title"

  deps <- list(
    htmltools::findDependencies(x$value),
    htmltools::findDependencies(x$icon),
    htmltools::findDependencies(x$footer),
    shinychat_deps()
  )

  tag <- htmltools::tag(
    tag_name,
    dots_list(type = NULL, version = NULL, !!!x, !!!deps, .homonyms = "first")
  )
  htmltools::tagAppendAttributes(tag, `data-shinychat-react` = NA)
}

#' @export
format.shinychat_tool_card <- function(x, ...) {
  format(tool_card_as_tags(x), ...)
}

#' @export
print.shinychat_tool_card <- function(x, ...) {
  tags <- tool_card_as_tags(x)
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
  knitr::knit_print(tool_card_as_tags(x))
}

method(contents_shinychat, ellmer::ContentToolRequest) <- function(
  content
) {
  if (opt_shinychat_tool_display() == "none") {
    return(NULL)
  }

  tool <- content@tool
  annotations <- shinychat_tool_annotations(tool)

  icon_rendered <- render_html_field(annotations$icon)

  block <- new_tool_card(
    "tool_request",
    request_id = content@id,
    tool_name = content@name,
    arguments = as.character(jsonlite::toJSON(
      content@arguments,
      auto_unbox = TRUE
    )),
    intent = content@arguments[["_intent"]],
    title = if (!is.null(annotations$title)) as.character(annotations$title),
    # The tool *definition* icon. The result element sends the result's own
    # icon (falling back to this one), so the client needs both to tell a
    # result-specific icon from the tool's shared identity.
    icon = icon_rendered$html,
    grouping = annotations$grouping
  )
  if (length(icon_rendered$deps) > 0) {
    attr(block, "shinychat_html_deps") <- icon_rendered$deps
  }
  block
}

method(contents_shinychat, ellmer::ContentToolResult) <- function(content) {
  if (opt_shinychat_tool_display() == "none") {
    return(NULL)
  }

  if (is.null(content@request)) {
    cli::cli_abort(
      "`ContentToolResult` objects must have an associated `@request` property."
    )
  }

  display <- get_tool_result_display(content)
  annotations <- shinychat_tool_annotations(content@request@tool)

  if (!is.null(content@request@tool)) {
    # format() line-wraps long calls into multiple elements; collapse so the
    # wire value is always a single string (the client calls .split() on it).
    request_call <- paste(
      format(content@request, show = "call"),
      collapse = "\n"
    )
  } else {
    # formatting the request fails if tool is not present
    # (ellmer v0.3.0, tidyverse/ellmer#691)
    request_call <- as.character(jsonlite::toJSON(
      list(
        id = content@request@id,
        name = content@request@name,
        arguments = content@request@arguments
      ),
      auto_unbox = TRUE,
      pretty = 2
    ))
  }

  icon_rendered <- render_html_field(display$icon %||% annotations$icon)
  footer_rendered <- render_html_field(display$footer)

  value_parts <- tool_result_value(content, display)
  if (identical(value_parts$value_type, "html")) {
    value_rendered <- render_html_field(value_parts$value)
    value_str <- value_rendered$html
    value_deps <- value_rendered$deps
  } else {
    value_str <- as.character(value_parts$value)
    value_deps <- list()
  }

  all_deps <- c(icon_rendered$deps, value_deps, footer_rendered$deps)

  block <- new_tool_card(
    "tool_result",
    request_id = content@request@id,
    request_call = request_call,
    status = if (tool_errored(content)) "error" else "success",
    tool_name = content@request@name,
    title = {
      block_title <- display$title %||% annotations$title
      if (!is.null(block_title)) as.character(block_title)
    },
    icon = icon_rendered$html,
    intent = content@request@arguments[["_intent"]],
    show_request = isTRUE(display$show_request %||% TRUE),
    expanded = isTRUE(display$open),
    full_screen = isTRUE(display$full_screen),
    open_style = if (identical(display$open_style, "framed")) {
      "framed"
    } else {
      NULL
    },
    footer = footer_rendered$html,
    grouping = annotations$grouping,
    label = display$label,
    value_preview = display$value_preview,
    value = value_str,
    value_type = value_parts$value_type
  )
  if (length(all_deps) > 0) {
    attr(block, "shinychat_html_deps") <- all_deps
  }
  block
}

#' Customize how a tool result is displayed
#'
#' `tool_result_display()` creates an object you can assign to the
#' `display` item of the `extra` argument of an [`ellmer::ContentToolResult`]
#' to customize how shinychat displays the tool result to the user, while
#' keeping the underlying `value` sent to the model unchanged.
#'
#' It preserves shinychat's compact activity row and drill-down card. Use it for
#' result titles, per-call labels and previews, or rich card content. To replace
#' the settled card with fully custom standalone UI, extend
#' [contents_shinychat()] instead. See the [Tool Calling UI
#' article](https://posit-dev.github.io/shinychat/r/articles/tool-ui.html) for a
#' complete guide.
#'
#' @param title The title to use for the settled call and drill-down card. It
#'   replaces the definition-level title from `ellmer::tool_annotations()` in a
#'   single-call row. In a multi-call group, a distinct result title can identify
#'   the call in the expanded call list. Write the definition title in the
#'   present tense (for example, `"Getting weather"`) and this result title in
#'   the past tense (for example, `"Got weather"`).
#' @param icon An icon to display with the settled call and drill-down card. Can
#'   be a character string or HTML content (e.g. from [htmltools::tags]).
#' @param html Custom HTML content (to use in place of the default result
#'   content in the drill-down card).
#' @param markdown Custom Markdown string (to use in place of the default
#'   result content in the drill-down card).
#' @param text Custom plain text string (to use in place of the default
#'   result content in the drill-down card).
#' @param show_request Whether to show the tool request inside the drill-down
#'   card.
#' @param open Whether to open the drill-down card by default when the result
#'   settles.
#' @param full_screen Whether or not to display a fullscreen toggle button on
#'   the drill-down card.
#' @param footer Optional HTML content to display below the drill-down card
#'   body.
#' @param label A short, per-call identifying value shown in the activity row
#'   (e.g. a filename or query). Distinguishes this call from other calls to the
#'   same tool. Without one, shinychat falls back to the call's own `title`
#'   (when it differs from the group's), then a short preview of the call's
#'   arguments, then the tool name.
#' @param value_preview A terse, per-call preview of the tool result, shown
#'   in the activity row before its drill-down card is opened.
#' @param open_style Whether the result uses the minimal drill-down style or a
#'   framed style when open.
#'
#' @return An object of class `shinychat_tool_result_display`, for use as
#'   `extra = list(display = tool_result_display(...))` when creating an
#'   [`ellmer::ContentToolResult`].
#'
#' @examplesIf rlang::is_installed("ellmer")
#' library(ellmer)
#'
#' get_current_weather <- function(location) {
#'   ContentToolResult(
#'     value = "72 degrees and sunny",
#'     extra = list(
#'       display = tool_result_display(
#'         title = paste("Got weather for", location),
#'         label = location,
#'         value_preview = "72°F and sunny",
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
  value_preview = NULL,
  open_style = "minimal"
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
      value_preview = value_preview,
      open_style = open_style
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
  "value_preview",
  "open_style"
)

# Fields that are rendered as HTML and therefore accept a string *or* tag-like
# content (see `render_html_field()`).
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
  } else if (identical(field, "open_style")) {
    is_string(value) && value %in% c("minimal", "framed")
  } else if (field %in% tool_result_display_html_fields) {
    is_string(value) || is_tag_like(value)
  } else {
    is_string(value)
  }
}

tool_result_display_field_expects <- function(field) {
  if (field %in% tool_result_display_flag_fields) {
    cli::format_inline("{.code TRUE} or {.code FALSE}")
  } else if (identical(field, "open_style")) {
    cli::format_inline("{.code minimal} or {.code framed}")
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
    inherits(display, c("html", "shiny.tag", "shiny.tag.list", "htmlwidget"))
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
  is_content_image(x) || S7_inherits(x, ellmer::ContentPDF)
}

is_content_image <- function(x) {
  S7_inherits(x, ellmer::ContentImage)
}

as_content_extra_item <- function(x) {
  if (S7_inherits(x, ellmer::ContentImageRemote)) {
    list(type = "image", src = x@url)
  } else if (S7_inherits(x, ellmer::ContentImageInline)) {
    list(type = "image", src = paste0("data:", x@type, ";base64,", x@data))
  } else if (S7_inherits(x, ellmer::ContentPDF)) {
    list(type = "pdf", filename = x@filename %||% "document.pdf")
  }
}

is_content <- function(x) {
  S7_inherits(x, ellmer::Content)
}

as_content_extra_item_or_text <- function(x) {
  if (is_content_extra(x)) {
    as_content_extra_item(x)
  } else if (S7_inherits(x, ellmer::ContentText)) {
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

method(contents_shinychat, ellmer::Turn) <- function(content) {
  # Process all contents in the turn, filtering out empty results.
  #
  # Wrapped, for the same reason as `merge_ellmer_turn_group()`: converting a
  # whole turn discards each `ContentToolResult` before any caller could wrap
  # it, so a turn carrying a custom tool result would otherwise emit bare UI
  # with no `<shiny-tool-result>` to pair its request against.
  raw_contents <- content@contents
  content <- compact(map(raw_contents, contents_shinychat_wrapped))
  flatten_content_splices(content)
}

ellmer_turn_effective_role <- function(turn) {
  contents <- turn@contents
  is_tool_result_only <- length(contents) > 0 &&
    every(contents, S7_inherits, ellmer::ContentToolResult)
  if (is_tool_result_only) "assistant" else turn@role
}

group_ellmer_turns <- function(turns) {
  if (length(turns) == 0) {
    return(list())
  }
  roles <- vapply(turns, ellmer_turn_effective_role, character(1))
  groups <- list()
  start <- 1L
  for (i in seq_along(roles)) {
    at_boundary <- i == length(roles) || !identical(roles[i], roles[i + 1L])
    if (at_boundary) {
      groups[[length(groups) + 1L]] <- turns[start:i]
      start <- i + 1L
    }
  }
  groups
}

# Coalesce adjacent character strings in a mixed content list by pasting
# with "\n\n", keeping blocks in position. Mirrors Python's `parts` coalescing.
#
# A `shinychat_thinking` string is treated like a boundary item: it flushes
# the pending markdown buffer and is emitted as its own part with the class
# intact (consecutive thinking strings are merged with each other via
# paste(..., collapse = "\n\n"), but never merged with plain markdown).
coalesce_content_strings <- function(content) {
  result <- list()
  str_buf <- character(0)
  think_buf <- character(0)

  flush_str_buf <- function() {
    if (length(str_buf) > 0) {
      result[[length(result) + 1]] <<- paste(str_buf, collapse = "\n\n")
      str_buf <<- character(0)
    }
  }
  flush_think_buf <- function() {
    if (length(think_buf) > 0) {
      result[[length(result) + 1]] <<- structure(
        paste(think_buf, collapse = "\n\n"),
        class = "shinychat_thinking"
      )
      think_buf <<- character(0)
    }
  }

  for (item in content) {
    if (is.character(item) && inherits(item, "shinychat_thinking")) {
      # A thinking string is a boundary: flush markdown, then accumulate
      # it into the thinking buffer (consecutive thinking strings merge).
      flush_str_buf()
      think_buf <- c(think_buf, item)
    } else if (is.character(item) && !inherits(item, "shinychat_block")) {
      # A plain markdown string is a boundary for thinking strings.
      flush_think_buf()
      str_buf <- c(str_buf, item)
    } else {
      # A block (or other non-character item) flushes both buffers.
      flush_str_buf()
      flush_think_buf()
      result[[length(result) + 1]] <- item
    }
  }
  flush_str_buf()
  flush_think_buf()
  result
}

merge_ellmer_turn_group <- function(group, tools) {
  role <- ellmer_turn_effective_role(group[[1]])

  contents <- unlist(
    lapply(group, function(turn) {
      turn_contents <- map(turn@contents, function(x) {
        if (!S7_inherits(x, ellmer::ContentToolResult)) {
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
      # Tool requests are kept (not filtered): the group's turns are merged into
      # one message below, so each request lands in the same content string as
      # its result. The client pairs them by request-id, the result inherits the
      # request's `arguments` (which the condensed view previews on its call
      # rows), and the paired request is then hidden since its result
      # supersedes it.
      turn_contents
    }),
    recursive = FALSE
  )

  # Wrapped so custom tool results get a `tool_result` block to pair with.
  content <- compact(map(contents, contents_shinychat_wrapped))
  if (is.null(content) || identical(content, "")) {
    return(NULL)
  }
  content <- flatten_content_splices(content)
  has_thinking <- some(content, function(x) {
    is.character(x) && inherits(x, "shinychat_thinking")
  })
  if (every(content, is.character) && !has_thinking) {
    content <- paste(unlist(content), collapse = "\n\n")
  } else if (some(content, inherits, "shinychat_block") || has_thinking) {
    content <- coalesce_content_strings(content)
  }
  list(role = role, content = content)
}

method(contents_shinychat, S7::new_S3_class(c("Chat", "R6"))) <- function(
  content
) {
  tools <- content$get_tools()
  groups <- group_ellmer_turns(content$get_turns())
  messages <- map(groups, merge_ellmer_turn_group, tools = tools)
  compact(messages)
}
