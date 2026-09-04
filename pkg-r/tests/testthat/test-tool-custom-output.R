# A `contents_shinychat()` method on a `ContentToolResult` subclass may return
# arbitrary tags instead of shinychat's own tool card. These tests drive that
# content through `chat_append_stream()` so the live path exercises the same
# conversion-plus-wrap boundary as Turn and restore conversion.

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

test_that("custom contents_shinychat() output for a successful tool result is wrapped in a tool_result block", {
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

  block <- captured[[1]]
  expect_s3_class(block, "shinychat_block")
  expect_equal(block$type, "tool_result")
  expect_equal(block$version, 1L)
  expect_equal(block$request_id, "req-1")
  expect_equal(block$tool_name, "get_weather")
  expect_equal(block$value_type, "html")
  expect_true(block$custom_display)
  expect_false(block$show_request)
  expect_match(block$value, "my-custom", fixed = TRUE)
  expect_match(block$value, "Sunny, 72F", fixed = TRUE)
  expect_equal(block$status, "success")

  # Fields deliberately absent from the custom-display wrap.
  expect_null(block$title)
  expect_null(block$request_call)
})

test_that("a character custom result stays markdown rather than becoming raw HTML", {
  # The wrap must reproduce whatever rendering the message would have had
  # unwrapped. A bare character return was appended as markdown, and
  # re-labelling it "html" would both drop the formatting and move it onto the
  # client's `RawHTML` path, where event-handler attributes fire.
  local_shinychat_tool_display(opt = "rich")

  StringCustomToolResult <- S7::new_class(
    "StringCustomToolResult",
    parent = ellmer::ContentToolResult
  )
  S7::method(contents_shinychat, StringCustomToolResult) <- function(content) {
    "**Sunny**, 72F"
  }

  result <- StringCustomToolResult(
    value = "Sunny, 72F",
    request = new_tool_request(id = "req-str", name = "get_weather")
  )

  captured <- run_stream_capture(result)
  expect_length(captured, 1)

  block <- captured[[1]]
  expect_s3_class(block, "shinychat_block")
  expect_equal(block$value_type, "markdown")
  expect_equal(block$value, "**Sunny**, 72F")
  expect_true(block$custom_display)
})

test_that("an HTML() custom result is still marked as html", {
  # `shiny::HTML()` is character *and* HTML, so the markdown branch must key
  # off the class rather than `is.character()` alone.
  local_shinychat_tool_display(opt = "rich")

  HtmlStringCustomToolResult <- S7::new_class(
    "HtmlStringCustomToolResult",
    parent = ellmer::ContentToolResult
  )
  S7::method(contents_shinychat, HtmlStringCustomToolResult) <- function(
    content
  ) {
    htmltools::HTML("<div class='my-custom'>Sunny, 72F</div>")
  }

  result <- HtmlStringCustomToolResult(
    value = "Sunny, 72F",
    request = new_tool_request(id = "req-html", name = "get_weather")
  )

  captured <- run_stream_capture(result)
  expect_length(captured, 1)

  block <- captured[[1]]
  expect_s3_class(block, "shinychat_block")
  expect_equal(block$value_type, "html")
  expect_match(block$value, "my-custom", fixed = TRUE)
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

  block <- captured[[1]]
  expect_s3_class(block, "shinychat_block")
  expect_equal(block$status, "error")
  expect_true(block$custom_display)
  expect_match(block$value, "my-custom", fixed = TRUE)
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

  block <- captured[[1]]
  expect_s3_class(block, "shinychat_block")
  expect_true(block$custom_display)
  expect_equal(block$grouping, "all")
})

test_that("shinychat's own tool result card is not misread as custom", {
  local_shinychat_tool_display(opt = "rich")

  result <- new_tool_result(value = "Success!")

  captured <- run_stream_capture(result)
  expect_length(captured, 1)

  block <- captured[[1]]
  expect_s3_class(block, "shinychat_block")
  expect_equal(block$type, "tool_result")
  expect_null(block$custom_display)
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

  block <- captured[[1]]
  expect_s3_class(block, "shinychat_block")
  expect_equal(block$type, "tool_result")
  expect_null(block$custom_display)
  expect_equal(block$value, "mutated value")
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

  block <- captured[[1]]
  expect_s3_class(block, "shinychat_block")
  expect_true(block$custom_display)
  block_deps <- attr(block, "shinychat_html_deps")
  dep_names <- vapply(block_deps, function(d) d$name, character(1))
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

  expect_false(inherits(captured[[1]], "shinychat_block"))
  html <- as.character(htmltools::as.tags(captured[[1]]))
  expect_match(html, "my-custom", fixed = TRUE)
})

# The restore/preload path (`chat_restore()` -> `client_set_ui()` ->
# `contents_shinychat(Chat)` -> `merge_ellmer_turn_group()`) converts a whole
# turn at once, so it never sees the original `ContentToolResult` the way the
# stream's wrap site does. Without its own wrap, a restored transcript's custom
# tool result arrives with no `<shiny-tool-result>` and its request row spins
# forever -- the same defect the live stream had.

test_that("merge_ellmer_turn_group() wraps custom tool output on restore", {
  local_shinychat_tool_display(opt = "rich")

  RestoredCustomToolResult <- S7::new_class(
    "RestoredCustomToolResult",
    parent = ellmer::ContentToolResult
  )
  S7::method(contents_shinychat, RestoredCustomToolResult) <- function(
    content
  ) {
    htmltools::div(class = "my-custom", "Sunny, 72F")
  }

  request <- new_tool_request(id = "req-restore", name = "get_weather")
  turn <- ellmer::Turn(
    "assistant",
    contents = list(
      request,
      RestoredCustomToolResult(value = "Sunny, 72F", request = request)
    )
  )

  message <- merge_ellmer_turn_group(list(turn), tools = list())
  content <- message$content
  expect_true(is.list(content))

  result_blocks <- Filter(
    function(x) {
      inherits(x, "shinychat_block") && identical(x$type, "tool_result")
    },
    content
  )
  expect_length(result_blocks, 1)
  block <- result_blocks[[1]]
  expect_s3_class(block, "shinychat_block")
  expect_true(block$custom_display)
  expect_equal(block$request_id, "req-restore")
  expect_match(block$value, "my-custom", fixed = TRUE)
})

test_that("contents_shinychat(Turn) wraps custom tool output", {
  local_shinychat_tool_display(opt = "rich")

  TurnCustomToolResult <- S7::new_class(
    "TurnCustomToolResult",
    parent = ellmer::ContentToolResult
  )
  S7::method(contents_shinychat, TurnCustomToolResult) <- function(content) {
    htmltools::div(class = "my-custom", "Sunny, 72F")
  }

  request <- new_tool_request(id = "req-turn", name = "get_weather")
  turn <- ellmer::Turn(
    "assistant",
    contents = list(
      request,
      TurnCustomToolResult(value = "Sunny, 72F", request = request)
    )
  )

  content <- contents_shinychat(turn)
  expect_true(is.list(content))

  result_blocks <- Filter(
    function(x) {
      inherits(x, "shinychat_block") && identical(x$type, "tool_result")
    },
    content
  )
  expect_length(result_blocks, 1)
  block <- result_blocks[[1]]
  expect_s3_class(block, "shinychat_block")
  expect_true(block$custom_display)
  expect_equal(block$request_id, "req-turn")
})

test_that("the wrap is idempotent, so a normal tool card is not double-wrapped", {
  # `contents_shinychat_wrapped()` is mapped over every content object on the
  # turn paths, including plain `ContentToolResult`s that already convert to
  # shinychat's own card. Those must pass through untouched.
  local_shinychat_tool_display(opt = "rich")

  request <- new_tool_request(id = "req-plain", name = "get_weather")
  result <- ellmer::ContentToolResult(value = "Sunny, 72F", request = request)

  once <- contents_shinychat_wrapped(result)
  twice <- wrap_custom_tool_result(result, once)

  expect_identical(once, twice)
  expect_s3_class(once, "shinychat_block")
  expect_null(once$custom_display)
})

test_that("the wrapped conversion boundary passes ordinary stream values through", {
  expect_identical(contents_shinychat_wrapped("plain text"), "plain text")
  expect_null(contents_shinychat_wrapped(NULL))
})
