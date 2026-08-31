library(htmltools)

# Helper: create a mock session and collect custom messages sent to it.
# Uses an environment so the message list is captured by reference.
# (Mirrors _CaptureSession in py's test_markdown_stream.py.)
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

# The non-streaming-dot messages (content and block carriers).
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

# ---------------------------------------------------------------------------
# markdown_stream() wire emission
# ---------------------------------------------------------------------------

test_that("markdown_stream() emits html_block for trusted island content", {
  # A trusted tag ships as a structured html_block block-message, not as
  # an island-tag string segment.
  mock <- mock_stream_session()
  shiny::withReactiveDomain(mock$session, {
    res <- sync(markdown_stream(
      "stream",
      div("trusted UI"),
      session = mock$session
    ))
  })

  msgs <- message_payloads(mock)
  # Leading empty replace (the clear), then the block message.
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
  # A message carries content XOR block (kata#mhyd).
  expect_false("content" %in% names(block_msg))
  expect_identical(block_msg$operation, "append")
  block <- block_msg$block
  expect_identical(block$type, "html_block")
  expect_identical(block$version, 1L)
  expect_match(block$content, "<div>trusted UI</div>", fixed = TRUE)
  # The island wrapper never appears on the wire anymore.
  expect_no_match(block$content, "<shiny-chat-raw-html>", fixed = TRUE)
})

test_that("markdown_stream() mixed content interleaves blocks and segments", {
  # Untrusted text stays an untrusted string segment; island wrappers
  # become block messages; bare data-shinychat-react elements stay trusted
  # residual string segments (blank-line wrapped).
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

  # Untrusted model text: unchanged string-segment behavior.
  expect_identical(msgs[[1]]$content, "model text ")
  expect_false(msgs[[1]]$trusted)
  expect_false(msgs[[1]]$segment_start)

  # Island wrappers -> html_block envelopes carrying the children HTML.
  expect_identical(msgs[[2]]$block$type, "html_block")
  expect_match(msgs[[2]]$block$content, "<div>before</div>", fixed = TRUE)
  expect_identical(msgs[[4]]$block$type, "html_block")
  expect_match(msgs[[4]]$block$content, "<div>after</div>", fixed = TRUE)

  # Bare React element: trusted residual string segment, surrounded by
  # blank lines (same as ChatMessage's derivation), never island-wrapped.
  residual <- msgs[[3]]
  expect_true(residual$trusted)
  expect_true(residual$segment_start)
  expect_match(residual$content, "shiny-tool-result", fixed = TRUE)
  expect_match(residual$content, "^\n\n")
  expect_match(residual$content, "\n\n$")
  expect_no_match(residual$content, "<shiny-chat-raw-html>", fixed = TRUE)
})

test_that("markdown_stream() sends already-structured blocks", {
  # An already-structured block in the stream content (e.g. a web_search
  # block of the kind ellmer normalization produces for chat) passes
  # through as one complete block message (kata#mhyd).
  mock <- mock_stream_session()
  search_block <- new_web_block("web_search", query = "weather in Duluth")
  results_block <- new_web_block(
    "web_search_results",
    sources = list(list(url = "https://example.com/weather"))
  )
  stream <- coro::gen({
    yield("model text ")
    yield(search_block)
    yield(results_block)
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
  expect_identical(kinds, c("content", "block", "block", "content"))

  # The blocks pass through untouched (the client validates and groups).
  expect_identical(msgs[[2]]$block, search_block)
  expect_identical(msgs[[3]]$block, results_block)
  expect_false("content" %in% names(msgs[[2]]))
  expect_identical(msgs[[2]]$operation, "append")

  # String content keeps its existing behavior around the blocks.
  expect_identical(msgs[[1]]$content, "model text ")
  expect_identical(msgs[[4]]$content, " done")

  # Blocks contribute nothing to the stream's text result.
  expect_identical(result, "model text  done")
})

test_that("markdown_stream() rejects tool blocks", {
  # Tool blocks are type-valid structured blocks, but the stream client
  # intentionally supports only html_block and web_* blocks — it drops tool
  # blocks with a warning. markdown_stream() must reject them server-side
  # with a clear error (fail openly) instead of silently discarding them.
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

  # The rejected blocks never reach the wire as block messages (only the
  # clear and the untrusted text segment were sent).
  expect_false(any(vapply(
    message_payloads(mock),
    function(m) "block" %in% names(m),
    logical(1)
  )))
})

test_that("markdown_stream() rejects unknown and typeless blocks", {
  # A block whose `type` is unknown — or absent — fails openly too.
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
  # Island dependencies are serialized through the session and ride the
  # block (for its mount gate) AND the message envelope (the run's first —
  # here only — envelope, so the client loads them before dispatching the
  # block).
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
  # Session-processed: serialized to plain dep dicts, not raw
  # html_dependency objects.
  expect_false(inherits(envelope_deps[[1]], "html_dependency"))
  expect_false(inherits(block_deps[[1]], "html_dependency"))
})

test_that("markdown_stream() aggregates run deps onto first envelope", {
  # Every dep of a trusted run rides the FIRST outbound envelope of the
  # run (block or string), so all of the run's dependencies load before
  # any of its parts mount — the invariant the pre-block whole-fragment
  # emission had. A dep declared after a React boundary must not load only
  # after earlier HTML of the same run has already mounted. Later parts of
  # the run send empty envelope html_deps; a block still carries its own
  # deps for its mount gate (mirroring ChatMessage's split).
  mock <- mock_stream_session()
  dep <- htmlDependency(
    "latelib",
    "1.0",
    src = c(href = "/late"),
    script = "late.js"
  )
  shiny::withReactiveDomain(mock$session, {
    # The dep is declared after the React boundary, inside the second
    # island wrapper.
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

  # The first envelope of the run carries the whole run's deps...
  expect_identical(
    vapply(msgs[[1]]$html_deps, `[[`, character(1), "name"),
    "latelib"
  )
  expect_identical(msgs[[2]]$html_deps, list())
  expect_identical(msgs[[3]]$html_deps, list())
  # ...while the block that actually owns the dep still carries it for its
  # own mount gate.
  expect_null(msgs[[1]]$block$html_deps)
  expect_identical(
    vapply(msgs[[3]]$block$html_deps, `[[`, character(1), "name"),
    "latelib"
  )
})

test_that("markdown_stream() aggregates run deps onto first string envelope", {
  # When a trusted run starts with a residual string part (bare React
  # elements), the aggregated run deps ride that content envelope.
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
  # The stream result string accumulates untrusted text, island HTML, and
  # residual markup alike.
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
  # Plain string streams keep the exact pre-block wire shape (no block
  # key, content present, append with segment_start=FALSE).
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
  # Uniform replace semantics (kata#0r4g): replace wipes all
  # segments+blocks via a leading empty replace message; append streams
  # (block-carrying ones included) send no wipe.
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

# ---------------------------------------------------------------------------
# output_markdown_stream() initial content-segments
# ---------------------------------------------------------------------------

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
  # Trusted UI ships as a structured html_block entry, not an island-tag
  # string segment (kata#mhyd).
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
  # The fallback content attribute carries the island HTML too, so a
  # client that fails closed on the provenance array (or predates block
  # entries) still shows it — escaped and untrusted.
  expect_match(
    el$attribs$content,
    "<div>This is HTML</div>",
    fixed = TRUE
  )
  expect_identical(el$attribs[["content-trusted"]], "false")
})

test_that("output_markdown_stream() block entry carries serialized deps", {
  # Block-level deps ride the block entry as serialized dicts AND the
  # element's dependencies (page-level, registered at render).
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
  # Bare data-shinychat-react elements remain trusted residual string
  # segments (blank-line wrapped); surrounding UI becomes block entries.
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
  # A lone residual text segment (no blocks) keeps content-trusted=true:
  # the fallback content is exactly the trusted server-authored HTML.
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
  # roborev job 1098: chat_update_bookmark() must not replace the
  # accumulated-content result with doBookmark()'s return value.
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
