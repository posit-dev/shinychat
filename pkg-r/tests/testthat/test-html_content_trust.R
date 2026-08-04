send_message <- function(session, ..., id = "chat") {
  send_chat_action(
    id,
    action = list(
      type = "message",
      message = list(role = "assistant", segments = list(...))
    ),
    session = session
  )
}

send_chunk_start <- function(session, ..., id = "chat") {
  send_chat_action(
    id,
    action = list(
      type = "chunk_start",
      message = list(role = "assistant", segments = list(...))
    ),
    session = session
  )
}

send_chunk <- function(
  session,
  content,
  content_type = "html",
  operation = "append",
  id = "chat"
) {
  send_chat_action(
    id,
    action = list(
      type = "chunk",
      content = content,
      content_type = content_type,
      operation = operation
    ),
    session = session
  )
}

send_chunk_end <- function(session, id = "chat") {
  send_chat_action(id, action = list(type = "chunk_end"), session = session)
}

seg <- function(content, content_type = "html") {
  list(content = content, content_type = content_type)
}

test_that("nothing is trusted before the server sends anything", {
  session <- shiny::MockShinySession$new()
  expect_false(is_trusted_html_content(session, "<div>a</div>"))
})

test_that("a one-shot html message is trusted", {
  session <- shiny::MockShinySession$new()
  send_message(session, seg("<div>a</div>"))
  expect_true(is_trusted_html_content(session, "<div>a</div>"))
  expect_false(is_trusted_html_content(session, "<div>b</div>"))
})

test_that("each segment of a multi-segment message is trusted on its own", {
  session <- shiny::MockShinySession$new()
  send_message(session, seg("<div>a</div>"), seg("<div>b</div>"))

  expect_true(is_trusted_html_content(session, "<div>a</div>"))
  expect_true(is_trusted_html_content(session, "<div>b</div>"))
  # The client never merges across segments of one payload, so the
  # concatenation must NOT become trusted.
  expect_false(is_trusted_html_content(session, "<div>a</div><div>b</div>"))
})

test_that("consecutive html chunks are trusted merged and individually", {
  session <- shiny::MockShinySession$new()
  send_chunk_start(session, seg("A"))
  send_chunk(session, "B")
  send_chunk(session, "C")
  send_chunk_end(session)

  expect_true(is_trusted_html_content(session, "A"))
  expect_true(is_trusted_html_content(session, "AB"))
  expect_true(is_trusted_html_content(session, "ABC"))
  expect_false(is_trusted_html_content(session, "AC"))
})

test_that("two consecutive one-shot html messages are both trusted", {
  session <- shiny::MockShinySession$new()
  send_message(session, seg("A"))
  send_message(session, seg("B"))

  expect_true(is_trusted_html_content(session, "A"))
  expect_true(is_trusted_html_content(session, "B"))
  expect_false(is_trusted_html_content(session, "AB"))
})

test_that("a non-html chunk ends the run", {
  session <- shiny::MockShinySession$new()
  send_chunk_start(session, seg("A"))
  send_chunk(session, "text", content_type = "markdown")
  send_chunk(session, "B")

  expect_true(is_trusted_html_content(session, "A"))
  expect_true(is_trusted_html_content(session, "B"))
  expect_false(is_trusted_html_content(session, "AB"))
})

test_that("operation = replace restarts the run", {
  session <- shiny::MockShinySession$new()
  send_chunk_start(session, seg("A"))
  send_chunk(session, "B", operation = "replace")
  send_chunk(session, "C")

  expect_true(is_trusted_html_content(session, "A"))
  expect_true(is_trusted_html_content(session, "B"))
  expect_true(is_trusted_html_content(session, "BC"))
  expect_false(is_trusted_html_content(session, "AB"))
})

test_that("an unrelated action between chunks does not split the run", {
  session <- shiny::MockShinySession$new()
  send_chunk_start(session, seg("A"))
  send_chat_action("chat", action = list(type = "clear"), session = session)
  send_chunk(session, "B")

  expect_true(is_trusted_html_content(session, "AB"))
})

test_that("runs from concurrent chats do not interleave", {
  session <- shiny::MockShinySession$new()
  send_chunk_start(session, seg("A1"), id = "one")
  send_chunk_start(session, seg("B1"), id = "two")
  send_chunk(session, "A2", id = "one")
  send_chunk(session, "B2", id = "two")

  expect_true(is_trusted_html_content(session, "A1A2"))
  expect_true(is_trusted_html_content(session, "B1B2"))
  expect_false(is_trusted_html_content(session, "A1B1"))
  expect_false(is_trusted_html_content(session, "A1B2"))
})

test_that("trust is not consumed by a first lookup", {
  session <- shiny::MockShinySession$new()
  send_message(session, seg("<div>a</div>"))

  expect_true(is_trusted_html_content(session, "<div>a</div>"))
  expect_true(is_trusted_html_content(session, "<div>a</div>"))
})

test_that("non-html and malformed segments never enter the registry", {
  session <- shiny::MockShinySession$new()
  send_message(session, seg("plain", content_type = "markdown"))
  send_message(session, list(content = 42, content_type = "html"))
  send_message(session, list(content_type = "html"))

  expect_false(is_trusted_html_content(session, "plain"))
  expect_false(is_trusted_html_content(session, "42"))
  expect_false(is_trusted_html_content(session, NULL))
  expect_false(is_trusted_html_content(NULL, "plain"))
})
