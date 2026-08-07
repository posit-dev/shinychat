message_fixture <- function(
  role = "assistant",
  content = "Hello",
  content_type = "markdown",
  attachments = NULL,
  html_deps = NULL
) {
  message <- list(
    role = role,
    segments = list(list(content = content, content_type = content_type))
  )
  if (!is.null(attachments)) {
    message$attachments <- attachments
  }
  if (!is.null(html_deps)) {
    message$htmlDeps <- html_deps
  }
  message
}

failing_send <- function() {
  rlang::abort("send failed")
}

test_that("get_chat_transcript returns NULL when nothing is registered", {
  session <- shiny::MockShinySession$new()
  expect_null(get_chat_transcript(session, "chat"))
})

test_that("register_chat_transcript scopes owners to a session and chat id", {
  session <- shiny::MockShinySession$new()
  x <- register_chat_transcript(session, "chat")

  expect_identical(x, register_chat_transcript(session, "chat"))
  expect_identical(x, get_chat_transcript(session, "chat"))
  expect_false(identical(x, register_chat_transcript(session, "other")))
  expect_false(
    identical(
      x,
      register_chat_transcript(shiny::MockShinySession$new(), "chat")
    )
  )
})

test_that("append normalizes messages and read returns copies", {
  transcript <- ChatTranscript$new()
  attachments <- list(
    list(
      mime = "text/plain",
      data_url = "data:text/plain;base64,SGk=",
      name = "hi.txt",
      size = 2
    )
  )
  dependencies <- list(list(name = "widget", version = "1.0.0"))

  transcript$append(
    message_fixture(
      role = "user",
      attachments = attachments,
      html_deps = dependencies
    )
  )

  messages <- transcript$read()
  expect_identical(
    messages,
    list(
      list(
        role = "user",
        segments = list(list(content = "Hello", content_type = "markdown")),
        attachments = attachments,
        htmlDeps = dependencies
      )
    )
  )

  messages[[1]]$segments[[1]]$content <- "Changed"
  expect_identical(transcript$read()[[1]]$segments[[1]]$content, "Hello")
})

test_that("stream chunks coalesce content and retain mixed segments and dependencies", {
  transcript <- ChatTranscript$new()
  stream <- new.env(parent = emptyenv())
  dependencies <- list(list(name = "widget", version = "1.0.0"))

  transcript$start(
    list(role = "assistant", segments = list()),
    stream_id = stream
  )
  transcript$chunk("one", "markdown", stream_id = stream)
  transcript$chunk(" two", "markdown", stream_id = stream)
  transcript$chunk("reasoning", "thinking", stream_id = stream)
  transcript$chunk(
    "answer",
    "markdown",
    stream_id = stream,
    html_deps = dependencies
  )
  transcript$settle(stream_id = stream)

  expect_identical(
    transcript$read(),
    list(
      list(
        role = "assistant",
        segments = list(
          list(content = "one two", content_type = "markdown"),
          list(content = "reasoning", content_type = "thinking"),
          list(content = "answer", content_type = "markdown")
        ),
        htmlDeps = dependencies
      )
    )
  )
})

test_that("replace chunks discard dependencies from the active stream", {
  transcript <- ChatTranscript$new()
  stream <- new.env(parent = emptyenv())
  dependencies <- list(list(name = "widget", version = "1.0.0"))

  transcript$start(
    list(role = "assistant", segments = list()),
    stream_id = stream
  )
  transcript$chunk(
    "draft",
    "markdown",
    stream_id = stream,
    html_deps = dependencies
  )
  transcript$chunk(
    "final",
    "markdown",
    stream_id = stream,
    operation = "replace"
  )
  transcript$settle(stream_id = stream)

  expect_identical(
    transcript$read(),
    list(
      list(
        role = "assistant",
        segments = list(list(content = "final", content_type = "markdown"))
      )
    )
  )
})

test_that("replace resets active state and clear discards settled and active state", {
  transcript <- ChatTranscript$new()
  stream <- new.env(parent = emptyenv())

  transcript$append(message_fixture(role = "user", content = "old"))
  transcript$start(
    list(role = "assistant", segments = list()),
    stream_id = stream
  )
  transcript$chunk("draft", "markdown", stream_id = stream)
  transcript$replace(
    list(message_fixture(role = "assistant", content = "restored"))
  )

  expect_identical(
    transcript$read(),
    list(message_fixture(role = "assistant", content = "restored"))
  )
  expect_error(
    transcript$chunk("stale", "markdown", stream_id = stream),
    "Cannot apply a stream chunk without an active stream",
    fixed = TRUE
  )

  transcript$start(
    list(role = "assistant", segments = list()),
    stream_id = stream
  )
  transcript$chunk("draft", "markdown", stream_id = stream)
  transcript$clear()
  expect_identical(transcript$read(), list())
  expect_error(
    transcript$settle(stream_id = stream),
    "Cannot end a stream without an active stream",
    fixed = TRUE
  )
})

test_that("stream lifecycle rejects chunks before start and overlapping starts", {
  transcript <- ChatTranscript$new()
  stream <- new.env(parent = emptyenv())
  other <- new.env(parent = emptyenv())

  expect_error(
    transcript$chunk("bad", "markdown", stream_id = stream),
    "Cannot apply a stream chunk without an active stream",
    fixed = TRUE
  )
  expect_error(
    transcript$settle(stream_id = stream),
    "Cannot end a stream without an active stream",
    fixed = TRUE
  )

  transcript$start(
    list(role = "assistant", segments = list()),
    stream_id = stream
  )
  expect_error(
    transcript$start(
      list(role = "assistant", segments = list()),
      stream_id = other
    ),
    "Cannot start a stream while another stream is active",
    fixed = TRUE
  )
})

test_that("stream identity determines active ownership", {
  transcript <- ChatTranscript$new()
  active <- new.env(parent = emptyenv())
  other <- new.env(parent = emptyenv())
  transcript$start(
    list(role = "assistant", segments = list()),
    stream_id = active
  )

  expect_error(
    transcript$start(
      list(role = "assistant", segments = list()),
      stream_id = other
    ),
    "Cannot start a stream while another stream is active",
    fixed = TRUE
  )
  expect_true(transcript$is_active(active))
  expect_false(transcript$is_active(other))
})

test_that("a complete append is rejected while a stream is active", {
  transcript <- ChatTranscript$new()
  stream <- new.env(parent = emptyenv())

  transcript$start(
    list(role = "assistant", segments = list()),
    stream_id = stream
  )
  expect_error(
    transcript$append(message_fixture(role = "user", content = "late")),
    "Cannot append a complete message while a stream is active",
    fixed = TRUE
  )
})

test_that("chunk and settle reject a foreign stream identity", {
  transcript <- ChatTranscript$new()
  active <- new.env(parent = emptyenv())
  other <- new.env(parent = emptyenv())

  transcript$start(
    list(role = "assistant", segments = list()),
    stream_id = active
  )
  expect_error(
    transcript$chunk("bad", "markdown", stream_id = other),
    "Cannot write to a stream that is not active",
    fixed = TRUE
  )
  expect_error(
    transcript$settle(stream_id = other),
    "Cannot write to a stream that is not active",
    fixed = TRUE
  )
  expect_true(transcript$is_active(active))
})

test_that("abort discards active content without disturbing settled messages or newer streams", {
  transcript <- ChatTranscript$new()
  active <- new.env(parent = emptyenv())

  transcript$append(message_fixture(role = "user", content = "kept"))
  transcript$start(
    list(role = "assistant", segments = list()),
    stream_id = active
  )
  transcript$chunk("discarded", "markdown", stream_id = active)
  transcript$abort(active)

  expect_identical(
    transcript$read(),
    list(message_fixture(role = "user", content = "kept"))
  )
  expect_false(transcript$is_active(active))

  transcript$append(message_fixture(role = "assistant", content = "after"))
  expect_identical(
    transcript$read(),
    list(
      message_fixture(role = "user", content = "kept"),
      message_fixture(role = "assistant", content = "after")
    )
  )

  newer <- new.env(parent = emptyenv())
  transcript$start(
    list(role = "assistant", segments = list()),
    stream_id = newer
  )
  transcript$abort(active)
  expect_true(transcript$is_active(newer))
})

test_that("mutations call send before committing state", {
  transcript <- ChatTranscript$new()
  send_states <- list()
  capture_send <- function() {
    send_states[[length(send_states) + 1L]] <<- transcript$read()
  }
  stream <- new.env(parent = emptyenv())

  transcript$append(
    message_fixture(role = "user", content = "one"),
    capture_send
  )
  expect_identical(send_states, list(list()))
  expect_identical(transcript$read()[[1]]$segments[[1]]$content, "one")

  expect_error(
    transcript$append(
      message_fixture(role = "user", content = "failed"),
      failing_send
    ),
    "send failed",
    fixed = TRUE
  )
  expect_identical(transcript$read()[[1]]$segments[[1]]$content, "one")

  expect_error(
    transcript$start(
      list(role = "assistant", segments = list()),
      stream_id = stream,
      send = failing_send
    ),
    "send failed",
    fixed = TRUE
  )
  expect_error(
    transcript$chunk("bad", "markdown", stream_id = stream),
    "Cannot apply a stream chunk without an active stream",
    fixed = TRUE
  )

  transcript$start(
    list(role = "assistant", segments = list()),
    stream_id = stream
  )
  expect_error(
    transcript$chunk(
      "draft",
      "markdown",
      stream_id = stream,
      send = failing_send
    ),
    "send failed",
    fixed = TRUE
  )
  transcript$chunk("draft", "markdown", stream_id = stream)
  expect_error(
    transcript$settle(stream_id = stream, send = failing_send),
    "send failed",
    fixed = TRUE
  )
  expect_identical(transcript$read()[[1]]$segments[[1]]$content, "one")
  transcript$settle(stream_id = stream)

  transcript$start(
    list(role = "assistant", segments = list()),
    stream_id = stream
  )
  transcript$chunk("clear draft", "markdown", stream_id = stream)
  before_clear <- transcript$read()
  expect_error(
    transcript$clear(send = failing_send),
    "send failed",
    fixed = TRUE
  )
  expect_identical(transcript$read(), before_clear)
  transcript$settle(stream_id = stream)
  expect_identical(
    transcript$read()[[3]]$segments[[1]]$content,
    "clear draft"
  )

  transcript$start(
    list(role = "assistant", segments = list()),
    stream_id = stream
  )
  transcript$chunk("replace draft", "markdown", stream_id = stream)
  before_replace <- transcript$read()
  replacement <- list(
    message_fixture(role = "assistant", content = "replacement")
  )
  expect_error(
    transcript$replace(replacement, send = failing_send),
    "send failed",
    fixed = TRUE
  )
  expect_identical(transcript$read(), before_replace)
  transcript$settle(stream_id = stream)
  expect_identical(
    transcript$read()[[4]]$segments[[1]]$content,
    "replace draft"
  )
  transcript$replace(replacement)
  expect_identical(transcript$read(), replacement)
})
