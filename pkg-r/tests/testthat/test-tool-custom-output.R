# A `contents_shinychat()` method on a `ContentToolResult` subclass may return
# arbitrary tags instead of shinychat's own tool card. These tests drive that
# content through `chat_append_stream()` (the only place the wrap can happen)
# rather than calling `contents_shinychat()` directly, because the wire shape
# is what the client actually consumes.

# Captures the content of the single non-bookend `chat_append_message()` call
# produced by streaming `result` through `chat_append_stream()`.
run_stream_capture <- function(result, env = parent.frame()) {
  captured <- list()
  local_mocked_bindings(
    chat_append_message = coro::async(function(id, msg, chunk = FALSE, ...) {
      if (!identical(chunk, "start") && !identical(chunk, "end")) {
        # `captured[[i]] <<- NULL` would delete rather than append, since a
        # custom result can legitimately carry `content = NULL`.
        captured <<- c(captured, list(msg$content))
      }
      invisible()
    }),
    send_chat_action = function(...) invisible(),
    .env = env
  )

  stream <- coro::async_generator(function() {
    yield(result)
  })

  sync(chat_append_stream("chat", stream()))

  captured
}

test_that("custom contents_shinychat() output for a successful tool result is wrapped in <shiny-tool-result>", {
  local_shinychat_tool_display(opt = "rich")

  SuccessCustomToolResult <- S7::new_class(
    "SuccessCustomToolResult",
    parent = ellmer::ContentToolResult
  )
  S7::method(contents_shinychat, SuccessCustomToolResult) <- function(content) {
    htmltools::div(class = "my-custom", "Sunny, 72F")
  }

  result <- SuccessCustomToolResult(
    value = "Sunny, 72F",
    request = new_tool_request(id = "req-1", name = "get_weather")
  )

  captured <- run_stream_capture(result)
  expect_length(captured, 1)

  html <- as.character(htmltools::as.tags(captured[[1]]))

  expect_match(html, "<shiny-tool-result", fixed = TRUE)
  expect_match(html, "custom-display", fixed = TRUE)
  expect_match(html, 'request-id="req-1"', fixed = TRUE)
  expect_match(html, 'tool-name="get_weather"', fixed = TRUE)
  expect_match(html, 'value-type="html"', fixed = TRUE)
  expect_match(html, "my-custom", fixed = TRUE)
  expect_match(html, "Sunny, 72F", fixed = TRUE)

  # Fields deliberately absent from the custom-display wrap.
  expect_no_match(html, "tool-title", fixed = TRUE)
  expect_no_match(html, "request-call", fixed = TRUE)
  expect_no_match(html, "show-request", fixed = TRUE)
})

test_that("a failed custom tool call renders like a successful one", {
  # The author is assumed to present the error state inside their own UI;
  # shinychat still needs to mark the call as errored for the request row.
  local_shinychat_tool_display(opt = "rich")

  ErrorCustomToolResult <- S7::new_class(
    "ErrorCustomToolResult",
    parent = ellmer::ContentToolResult
  )
  S7::method(contents_shinychat, ErrorCustomToolResult) <- function(content) {
    htmltools::div(class = "my-custom", "Could not reach the forecast API")
  }

  result <- ErrorCustomToolResult(
    value = NULL,
    error = "boom",
    request = new_tool_request(id = "req-2", name = "get_weather")
  )

  captured <- run_stream_capture(result)
  expect_length(captured, 1)

  html <- as.character(htmltools::as.tags(captured[[1]]))

  expect_match(html, "<shiny-tool-result", fixed = TRUE)
  expect_match(html, 'status="error"', fixed = TRUE)
  expect_match(html, "custom-display", fixed = TRUE)
  expect_match(html, "my-custom", fixed = TRUE)
})

test_that("the grouping annotation travels through the custom-display wrap", {
  local_shinychat_tool_display(opt = "rich")

  GroupingCustomToolResult <- S7::new_class(
    "GroupingCustomToolResult",
    parent = ellmer::ContentToolResult
  )
  S7::method(contents_shinychat, GroupingCustomToolResult) <- function(
    content
  ) {
    htmltools::div(class = "my-custom", "Sunny, 72F")
  }

  tool <- new_tool(name = "get_weather", annotations = list(grouping = "all"))
  result <- GroupingCustomToolResult(
    value = "Sunny, 72F",
    request = new_tool_request(name = "get_weather", tool = tool)
  )

  captured <- run_stream_capture(result)
  expect_length(captured, 1)

  html <- as.character(htmltools::as.tags(captured[[1]]))

  expect_match(html, "<shiny-tool-result", fixed = TRUE)
  expect_match(html, "custom-display", fixed = TRUE)
  expect_match(html, 'grouping="all"', fixed = TRUE)
})

test_that("shinychat's own tool result card is not misread as custom", {
  local_shinychat_tool_display(opt = "rich")

  result <- new_tool_result(value = "Success!")

  captured <- run_stream_capture(result)
  expect_length(captured, 1)

  html <- as.character(htmltools::as.tags(captured[[1]]))

  expect_match(html, "<shiny-tool-result", fixed = TRUE)
  expect_no_match(html, "custom-display", fixed = TRUE)
})

test_that("the documented S7::super() extend pattern is not misread as custom", {
  local_shinychat_tool_display(opt = "rich")

  ExtendedToolResult <- S7::new_class(
    "ExtendedToolResult",
    parent = ellmer::ContentToolResult
  )
  S7::method(contents_shinychat, ExtendedToolResult) <- function(content) {
    res <- contents_shinychat(S7::super(content, ellmer::ContentToolResult))
    res$value <- "mutated value"
    res$value_type <- "code"
    res
  }

  result <- ExtendedToolResult(
    value = "original value",
    request = new_tool_request(id = "req-4", name = "get_weather")
  )

  captured <- run_stream_capture(result)
  expect_length(captured, 1)

  html <- as.character(htmltools::as.tags(captured[[1]]))

  expect_match(html, "<shiny-tool-result", fixed = TRUE)
  expect_no_match(html, "custom-display", fixed = TRUE)
  expect_match(html, "mutated value", fixed = TRUE)
})

test_that("no element is emitted for a tool result when tool_display is none", {
  # `contents_shinychat.ContentToolResult` returns `NULL` when display is
  # disabled entirely (see `test-contents_shinychat.R`), so there is nothing
  # for the chat.R wrap logic to wrap into a `<shiny-tool-result>`.
  local_shinychat_tool_display(opt = "none")

  result <- new_tool_result(
    value = "Sunny, 72F",
    request = new_tool_request(id = "req-5", name = "get_weather")
  )

  captured <- run_stream_capture(result)
  expect_length(captured, 1)

  expect_null(captured[[1]])
})

test_that("HTML dependencies on custom tool UI survive the wrap", {
  local_shinychat_tool_display(opt = "rich")

  dep <- htmltools::htmlDependency(
    name = "custom-tool-dep",
    version = "1.0",
    src = "."
  )

  DepToolResult <- S7::new_class(
    "DepToolResult",
    parent = ellmer::ContentToolResult
  )
  S7::method(contents_shinychat, DepToolResult) <- function(content) {
    htmltools::attachDependencies(
      htmltools::div(class = "my-custom", "Sunny, 72F"),
      dep
    )
  }

  result <- DepToolResult(
    value = "Sunny, 72F",
    request = new_tool_request(id = "req-6", name = "get_weather")
  )

  captured <- run_stream_capture(result)
  expect_length(captured, 1)

  tags <- htmltools::as.tags(captured[[1]])
  html <- as.character(tags)

  expect_match(html, "<shiny-tool-result", fixed = TRUE)
  dep_names <- vapply(
    htmltools::findDependencies(tags),
    function(d) d$name,
    character(1)
  )
  expect_true("custom-tool-dep" %in% dep_names)
})

test_that("a custom result with no @request emits bare tags, no wrap", {
  # A custom `contents_shinychat()` method bypasses the base method's check
  # that `@request` is present (that check only lives in the base method for
  # `ContentToolResult`), so it can reach the wrap site with nothing to pair
  # a result against. There is no wrap to make in that case.
  local_shinychat_tool_display(opt = "rich")

  NoRequestCustomToolResult <- S7::new_class(
    "NoRequestCustomToolResult",
    parent = ellmer::ContentToolResult
  )
  S7::method(contents_shinychat, NoRequestCustomToolResult) <- function(
    content
  ) {
    htmltools::div(class = "my-custom", "Sunny, 72F")
  }

  result <- NoRequestCustomToolResult(value = "Sunny, 72F")

  captured <- run_stream_capture(result)
  expect_length(captured, 1)

  html <- as.character(htmltools::as.tags(captured[[1]]))

  expect_no_match(html, "<shiny-tool-result", fixed = TRUE)
  expect_no_match(html, "custom-display", fixed = TRUE)
  expect_match(html, "my-custom", fixed = TRUE)
})
