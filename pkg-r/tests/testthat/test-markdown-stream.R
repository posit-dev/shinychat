library(htmltools)

mock_stream_session <- function() {
  sess <- shiny::MockShinySession$new()
  spy <- new.env(parent = emptyenv())
  spy$messages <- list()
  sess$sendCustomMessage <- function(type, msg) {
    spy$messages[[length(spy$messages) + 1]] <- list(
      type = type,
      message = msg
    )
  }
  list(session = sess, spy = spy)
}

content_messages <- function(messages) {
  Filter(
    function(m) !"isStreaming" %in% names(m$message),
    messages
  )
}

message_payloads <- function(mock) {
  lapply(content_messages(mock$spy$messages), `[[`, "message")
}

react_tag <- function(...) {
  htmltools::tag(
    "shiny-tool-result",
    list(..., `data-shinychat-react` = NA, `request-id` = "abc")
  )
}

test_that("Chat component markup", {
  expect_snapshot(output_markdown_stream("stream"))

  expect_snapshot({
    output_markdown_stream("stream", content = "Foo\nBar")
  })

  expect_snapshot({
    render_tags(
      output_markdown_stream(
        "stream",
        content = div("Hello", htmlDependency("foo", "1.0.0", ""))
      )
    )
  })
})


test_that("markdown_stream() emits html_block for trusted island content", {
  mock <- mock_stream_session()
  shiny::withReactiveDomain(mock$session, {
    res <- sync(markdown_stream(
      "stream",
      div("trusted UI"),
      session = mock$session
    ))
  })

  msgs <- message_payloads(mock)
  expect_identical(
    msgs[[1]],
    list(
      id = "stream",
      content = "",
      operation = "replace",
      html_deps = list(),
      trusted = FALSE,
      segment_start = TRUE
    )
  )
  expect_length(msgs, 2)
  block_msg <- msgs[[2]]
  expect_false("content" %in% names(block_msg))
  expect_identical(block_msg$operation, "append")
  block <- block_msg$block
  expect_identical(block$type, "html_block")
  expect_identical(block$version, 1L)
  expect_match(block$content, "<div>trusted UI</div>", fixed = TRUE)
  expect_no_match(block$content, "<shiny-chat-raw-html>", fixed = TRUE)
})

test_that("markdown_stream() mixed content interleaves blocks and segments", {
  mock <- mock_stream_session()
  stream <- coro::gen({
    yield("model text ")
    yield(tagList(div("before"), react_tag(), div("after")))
  })
  shiny::withReactiveDomain(mock$session, {
    sync(markdown_stream("stream", stream, session = mock$session))
  })

  msgs <- message_payloads(mock)[-1] # drop the leading clear

  kinds <- vapply(
    msgs,
    function(m) if ("block" %in% names(m)) "block" else "content",
    character(1)
  )
  expect_identical(kinds, c("content", "block", "content", "block"))

  expect_identical(msgs[[1]]$content, "model text ")
  expect_false(msgs[[1]]$trusted)
  expect_false(msgs[[1]]$segment_start)

  expect_identical(msgs[[2]]$block$type, "html_block")
  expect_match(msgs[[2]]$block$content, "<div>before</div>", fixed = TRUE)
  expect_identical(msgs[[4]]$block$type, "html_block")
  expect_match(msgs[[4]]$block$content, "<div>after</div>", fixed = TRUE)

  residual <- msgs[[3]]
  expect_true(residual$trusted)
  expect_true(residual$segment_start)
  expect_match(residual$content, "shiny-tool-result", fixed = TRUE)
  expect_match(residual$content, "^\n\n")
  expect_match(residual$content, "\n\n$")
  expect_no_match(residual$content, "<shiny-chat-raw-html>", fixed = TRUE)
})

test_that("markdown_stream() sends already-structured blocks", {
  mock <- mock_stream_session()
  search_block <- new_web_block("web_search", query = "weather in Duluth")
  results_block <- new_web_block(
    "web_search_results",
    sources = list(list(url = "https://example.com/weather"))
  )
  citations_block <- new_web_block(
    "web_search_citations",
    sources = list(list(url = "https://example.com/cited"))
  )
  stream <- coro::gen({
    yield("model text ")
    yield(search_block)
    yield(results_block)
    yield(citations_block)
    yield(" done")
  })
  shiny::withReactiveDomain(mock$session, {
    result <- sync(markdown_stream("stream", stream, session = mock$session))
  })

  msgs <- message_payloads(mock)[-1] # drop the leading clear
  kinds <- vapply(
    msgs,
    function(m) if ("block" %in% names(m)) "block" else "content",
    character(1)
  )
  expect_identical(kinds, c("content", "block", "block", "block", "content"))

  expect_identical(msgs[[2]]$block, search_block)
  expect_identical(msgs[[3]]$block, results_block)
  expect_identical(msgs[[4]]$block, citations_block)
  expect_false("content" %in% names(msgs[[2]]))
  expect_identical(msgs[[2]]$operation, "append")

  expect_identical(msgs[[1]]$content, "model text ")
  expect_identical(msgs[[5]]$content, " done")

  expect_identical(result, "model text  done")
})

test_that("markdown_stream() rejects tool blocks", {
  mock <- mock_stream_session()
  tool_request <- new_tool_card(
    "tool_request",
    request_id = "r1",
    tool_name = "some_tool"
  )
  tool_result <- new_tool_card(
    "tool_result",
    request_id = "r1",
    tool_name = "some_tool",
    status = "success"
  )
  shiny::withReactiveDomain(mock$session, {
    for (block in list(tool_request, tool_result)) {
      stream <- coro::gen({
        yield("before ")
        yield(block)
      })
      expect_error(
        sync(markdown_stream("stream", stream, session = mock$session)),
        "Unsupported structured block"
      )
    }
  })

  expect_false(any(vapply(
    message_payloads(mock),
    function(m) "block" %in% names(m),
    logical(1)
  )))
})

test_that("markdown_stream() rejects unknown and typeless blocks", {
  mock <- mock_stream_session()
  unknown_block <- structure(
    list(type = "made_up", version = 1L),
    class = "shinychat_block"
  )
  typeless_block <- structure(list(version = 1L), class = "shinychat_block")
  shiny::withReactiveDomain(mock$session, {
    for (block in list(unknown_block, typeless_block)) {
      expect_error(
        sync(markdown_stream(
          "stream",
          coro::gen(yield(block)),
          session = mock$session
        )),
        "Unsupported structured block"
      )
    }
  })

  expect_false(any(vapply(
    message_payloads(mock),
    function(m) "block" %in% names(m),
    logical(1)
  )))
})

test_that("markdown_stream() block message carries session-processed deps", {
  mock <- mock_stream_session()
  dep <- htmlDependency(
    "testlib",
    "1.0",
    src = c(href = "/test"),
    script = "test.js"
  )
  shiny::withReactiveDomain(mock$session, {
    sync(markdown_stream(
      "stream",
      tagList(div("x"), dep),
      session = mock$session
    ))
  })

  msgs <- message_payloads(mock)
  block_msg <- msgs[[2]]
  envelope_deps <- block_msg$html_deps
  expect_identical(
    vapply(envelope_deps, `[[`, character(1), "name"),
    "testlib"
  )
  block_deps <- block_msg$block$html_deps
  expect_false(is.null(block_deps))
  expect_identical(block_deps[[1]]$name, "testlib")
  expect_false(inherits(envelope_deps[[1]], "html_dependency"))
  expect_false(inherits(block_deps[[1]], "html_dependency"))
})

test_that("markdown_stream() aggregates run deps onto first envelope", {
  mock <- mock_stream_session()
  dep <- htmlDependency(
    "latelib",
    "1.0",
    src = c(href = "/late"),
    script = "late.js"
  )
  shiny::withReactiveDomain(mock$session, {
    sync(markdown_stream(
      "stream",
      tagList(div("before"), react_tag(), div("after"), dep),
      session = mock$session
    ))
  })

  msgs <- message_payloads(mock)[-1] # drop the leading clear
  kinds <- vapply(
    msgs,
    function(m) if ("block" %in% names(m)) "block" else "content",
    character(1)
  )
  expect_identical(kinds, c("block", "content", "block"))

  expect_identical(
    vapply(msgs[[1]]$html_deps, `[[`, character(1), "name"),
    "latelib"
  )
  expect_identical(msgs[[2]]$html_deps, list())
  expect_identical(msgs[[3]]$html_deps, list())
  expect_null(msgs[[1]]$block$html_deps)
  expect_identical(
    vapply(msgs[[3]]$block$html_deps, `[[`, character(1), "name"),
    "latelib"
  )
})

test_that("markdown_stream() aggregates run deps onto first string envelope", {
  mock <- mock_stream_session()
  dep_first <- htmlDependency(
    "firstlib",
    "1.0",
    src = c(href = "/first"),
    script = "first.js"
  )
  dep_second <- htmlDependency(
    "secondlib",
    "2.0",
    src = c(href = "/second"),
    script = "second.js"
  )
  shiny::withReactiveDomain(mock$session, {
    sync(markdown_stream(
      "stream",
      tagList(react_tag(dep_first), div("after", dep_second)),
      session = mock$session
    ))
  })

  msgs <- message_payloads(mock)[-1] # drop the leading clear
  kinds <- vapply(
    msgs,
    function(m) if ("block" %in% names(m)) "block" else "content",
    character(1)
  )
  expect_identical(kinds, c("content", "block"))

  expect_identical(
    vapply(msgs[[1]]$html_deps, `[[`, character(1), "name"),
    c("firstlib", "secondlib")
  )
  expect_identical(msgs[[2]]$html_deps, list())
  expect_identical(
    vapply(msgs[[2]]$block$html_deps, `[[`, character(1), "name"),
    "secondlib"
  )
})

test_that("markdown_stream() result includes island html", {
  mock <- mock_stream_session()
  stream <- coro::gen({
    yield("model text ")
    yield(div("trusted UI"))
  })
  shiny::withReactiveDomain(mock$session, {
    result <- sync(markdown_stream("stream", stream, session = mock$session))
  })

  expect_match(result, "model text ", fixed = TRUE)
  expect_match(result, "<div>trusted UI</div>", fixed = TRUE)
})

test_that("markdown_stream() untrusted content unchanged", {
  mock <- mock_stream_session()
  stream <- coro::gen({
    yield("hello ")
    yield("world")
  })
  shiny::withReactiveDomain(mock$session, {
    sync(markdown_stream("stream", stream, session = mock$session))
  })

  msgs <- message_payloads(mock)[-1] # drop the leading clear
  expect_identical(
    msgs,
    list(
      list(
        id = "stream",
        content = "hello ",
        operation = "append",
        html_deps = list(),
        trusted = FALSE,
        segment_start = FALSE
      ),
      list(
        id = "stream",
        content = "world",
        operation = "append",
        html_deps = list(),
        trusted = FALSE,
        segment_start = FALSE
      )
    )
  )
})

test_that("markdown_stream(operation = \"append\") skips the leading clear", {
  mock <- mock_stream_session()
  shiny::withReactiveDomain(mock$session, {
    sync(markdown_stream(
      "stream",
      div("trusted UI"),
      operation = "append",
      session = mock$session
    ))
  })

  msgs <- message_payloads(mock)
  expect_length(msgs, 1)
  expect_false("content" %in% names(msgs[[1]]))
  expect_identical(msgs[[1]]$operation, "append")
  expect_identical(msgs[[1]]$block$type, "html_block")
})


test_that("output_markdown_stream() emits block entries for island content", {
  el <- output_markdown_stream(
    "stream",
    content = tagList(
      "## This is markdown",
      div("This is HTML")
    )
  )
  segments <- jsonlite::fromJSON(
    el$attribs[["content-segments"]],
    simplifyVector = FALSE
  )

  expect_identical(
    segments[[1]],
    list(text = "## This is markdown", trusted = FALSE)
  )
  expect_identical(
    segments[[2]],
    list(
      block = list(
        type = "html_block",
        version = 1L,
        content = "<div>This is HTML</div>"
      )
    )
  )
  expect_match(
    el$attribs$content,
    "<div>This is HTML</div>",
    fixed = TRUE
  )
  expect_identical(el$attribs[["content-trusted"]], "false")
})

test_that("output_markdown_stream() block entry carries serialized deps", {
  dep <- htmlDependency(
    "testlib",
    "1.0",
    src = c(href = "/test"),
    script = "test.js"
  )
  el <- output_markdown_stream("stream", content = tagList(div("x"), dep))
  segments <- jsonlite::fromJSON(
    el$attribs[["content-segments"]],
    simplifyVector = FALSE
  )

  block_deps <- segments[[1]]$block$html_deps
  expect_false(is.null(block_deps))
  expect_identical(block_deps[[1]]$name, "testlib")
  rendered <- renderTags(tagList(el))
  expect_true(
    "testlib" %in%
      vapply(
        rendered$dependencies,
        function(d) d$name,
        character(1)
      )
  )
})

test_that("output_markdown_stream() react element stays trusted text segment", {
  el <- output_markdown_stream(
    "stream",
    content = tagList(div("before"), react_tag(), div("after"))
  )
  segments <- jsonlite::fromJSON(
    el$attribs[["content-segments"]],
    simplifyVector = FALSE
  )

  expect_length(segments, 3)
  expect_identical(segments[[1]]$block$type, "html_block")
  expect_match(segments[[1]]$block$content, "<div>before</div>", fixed = TRUE)
  expect_true(segments[[2]]$trusted)
  expect_match(segments[[2]]$text, "shiny-tool-result", fixed = TRUE)
  expect_match(segments[[2]]$text, "^\n\n")
  expect_identical(segments[[3]]$block$type, "html_block")
  expect_match(segments[[3]]$block$content, "<div>after</div>", fixed = TRUE)
})

test_that("output_markdown_stream() single react element keeps trusted fallback", {
  el <- output_markdown_stream("stream", content = react_tag())
  segments <- jsonlite::fromJSON(
    el$attribs[["content-segments"]],
    simplifyVector = FALSE
  )

  expect_length(segments, 1)
  expect_true(segments[[1]]$trusted)
  expect_identical(el$attribs[["content-trusted"]], "true")
})

test_that("bookmark-on-response preserves the stream result value", {
  mock <- mock_stream_session()
  bookmarked <- FALSE
  mock$session$doBookmark <- function() {
    bookmarked <<- TRUE
    "bookmark-url"
  }
  set_session_bookmark_on_response(mock$session, "stream", TRUE)

  value <- shiny::withReactiveDomain(mock$session, {
    sync(markdown_stream("stream", "hello", session = mock$session))
  })

  expect_true(bookmarked)
  expect_match(value, "hello", fixed = TRUE)
})

# Pin the exact set of structured block types accepted in a markdown stream.
# If you are adding a block type, you MUST update all three allowlists in sync:
#   1. `STREAM_BLOCK_TYPES` in pkg-r/R/markdown-stream.R
#   2. `_STREAM_BLOCK_TYPES` in pkg-py/src/shinychat/_markdown_stream.py
#   3. `asStreamBlock` in js/src/markdown-stream/markdown-stream-entry.ts
test_that("stream block type allowlist matches the pinned set", {
  expect_setequal(
    STREAM_BLOCK_TYPES,
    c(
      "html_block",
      "web_search",
      "web_search_results",
      "web_search_citations",
      "web_fetch"
    )
  )
  expect_length(STREAM_BLOCK_TYPES, 5)
})
