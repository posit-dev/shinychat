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

test_that("a streamed html message is trusted as the client merges it", {
  session <- shiny::MockShinySession$new()
  send_chunk_start(session, seg("A"))
  send_chunk(session, "B")
  send_chunk(session, "C")
  send_chunk_end(session)

  expect_true(is_trusted_html_content(session, "ABC"))
  expect_false(is_trusted_html_content(session, "AC"))
})

test_that("a stream in flight has nothing to trust yet", {
  # The browser reports only settled messages -- buildMessagesSnapshot() drops
  # anything still streaming -- so the intermediate prefixes of a stream are
  # never reported back and must not be trusted just because we sent them.
  session <- shiny::MockShinySession$new()
  send_chunk_start(session, seg("A"))
  send_chunk(session, "B")

  expect_false(is_trusted_html_content(session, "A"))
  expect_false(is_trusted_html_content(session, "AB"))

  send_chunk_end(session)
  expect_true(is_trusted_html_content(session, "AB"))
})

test_that("two consecutive one-shot html messages are both trusted", {
  session <- shiny::MockShinySession$new()
  send_message(session, seg("A"))
  send_message(session, seg("B"))

  expect_true(is_trusted_html_content(session, "A"))
  expect_true(is_trusted_html_content(session, "B"))
  expect_false(is_trusted_html_content(session, "AB"))
})

test_that("a chunk of another content type starts a new segment", {
  session <- shiny::MockShinySession$new()
  send_chunk_start(session, seg("A"))
  send_chunk(session, "text", content_type = "markdown")
  send_chunk(session, "B")
  send_chunk_end(session)

  expect_true(is_trusted_html_content(session, "A"))
  expect_true(is_trusted_html_content(session, "B"))
  expect_false(is_trusted_html_content(session, "AB"))
})

test_that("a chunk without a content type continues the one in progress", {
  session <- shiny::MockShinySession$new()
  send_chunk_start(session, seg("A"))
  send_chat_action(
    "chat",
    action = list(type = "chunk", content = "B", operation = "append"),
    session = session
  )
  send_chunk_end(session)

  expect_true(is_trusted_html_content(session, "AB"))
})

test_that("operation = replace restarts the accumulation", {
  session <- shiny::MockShinySession$new()
  send_chunk_start(session, seg("A"))
  send_chunk(session, "B", operation = "replace")
  send_chunk(session, "C")
  send_chunk_end(session)

  expect_true(is_trusted_html_content(session, "BC"))
  expect_false(is_trusted_html_content(session, "A"))
  expect_false(is_trusted_html_content(session, "ABC"))
})

test_that("an unrelated action between chunks does not split the merge", {
  session <- shiny::MockShinySession$new()
  send_chunk_start(session, seg("A"))
  send_chat_action("chat", action = list(type = "clear"), session = session)
  send_chunk(session, "B")
  send_chunk_end(session)

  expect_true(is_trusted_html_content(session, "AB"))
})

test_that("a chunk with no stream open displays nothing to trust", {
  # The client's `chunk` reducer bails when there is no streaming message, so
  # neither should the ledger invent one.
  session <- shiny::MockShinySession$new()
  send_chunk(session, "orphan")
  send_chunk_end(session)

  expect_false(is_trusted_html_content(session, "orphan"))
})

test_that("streams from concurrent chats do not interleave", {
  session <- shiny::MockShinySession$new()
  send_chunk_start(session, seg("A1"), id = "one")
  send_chunk_start(session, seg("B1"), id = "two")
  send_chunk(session, "A2", id = "one")
  send_chunk(session, "B2", id = "two")
  send_chunk_end(session, id = "one")
  send_chunk_end(session, id = "two")

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
  # `$` partial-matches "content" to "content_type" on a segment missing
  # `content`; guard against that regressing back in.
  expect_false(is_trusted_html_content(session, "html"))
})

reported_html <- function(...) {
  list(list(role = "assistant", segments = list(...)))
}

test_that("html content the server never sent degrades to markdown", {
  session <- shiny::MockShinySession$new()

  expect_warning(
    out <- messages_input_value(
      reported_html(seg("<img src=x onerror=alert(1)>")),
      session
    ),
    "did not send"
  )

  expect_equal(out[[1]]$segments[[1]]$content_type, "markdown")
  # Content is preserved: the client escapes reserved element names on the
  # markdown branch, so it renders as literal text.
  expect_equal(out[[1]]$segments[[1]]$content, "<img src=x onerror=alert(1)>")
})

test_that("html content the server sent survives unchanged", {
  session <- shiny::MockShinySession$new()
  send_message(session, seg("<div>widget</div>"))

  out <- messages_input_value(reported_html(seg("<div>widget</div>")), session)

  expect_equal(out[[1]]$segments[[1]]$content_type, "html")
  expect_equal(out[[1]]$segments[[1]]$content, "<div>widget</div>")
})

test_that("only the untrusted segment degrades", {
  session <- shiny::MockShinySession$new()
  send_message(session, seg("<div>ok</div>"))

  expect_warning(
    out <- messages_input_value(
      list(
        list(
          role = "assistant",
          segments = list(
            seg("<div>ok</div>"),
            seg("<div>forged</div>"),
            seg("some *markdown*", content_type = "markdown")
          )
        ),
        list(role = "user", segments = list(seg("hi", "markdown")))
      ),
      session
    ),
    "did not send"
  )

  types <- vapply(out[[1]]$segments, function(s) s$content_type, character(1))
  expect_equal(types, c("html", "markdown", "markdown"))
  expect_equal(out[[2]]$segments[[1]]$content, "hi")
})

test_that("a merged streamed html segment survives", {
  session <- shiny::MockShinySession$new()
  send_chunk_start(session, seg("<div>a</div>"))
  send_chunk(session, "<div>b</div>")
  send_chunk_end(session)

  out <- messages_input_value(
    reported_html(seg("<div>a</div><div>b</div>")),
    session
  )

  expect_equal(out[[1]]$segments[[1]]$content_type, "html")
})

test_that("one warning covers a whole forged transcript", {
  session <- shiny::MockShinySession$new()
  forged <- reported_html(seg("<div>1</div>"), seg("<div>2</div>"))

  warnings <- character()
  withCallingHandlers(
    messages_input_value(forged, session),
    warning = function(w) {
      warnings <<- c(warnings, conditionMessage(w))
      invokeRestart("muffleWarning")
    }
  )

  expect_length(warnings, 1)
  expect_match(warnings[[1]], "2")
})

test_that("no session means no trusted html", {
  expect_warning(
    out <- messages_input_value(reported_html(seg("<div>a</div>")), NULL),
    "did not send"
  )
  expect_equal(out[[1]]$segments[[1]]$content_type, "markdown")
})

test_that("a legitimate multi-block conversation round-trips, and replay repopulates the registry", {
  # restore_history_message() is the shared replay primitive: it's what a
  # history-conversation switch calls per stored message (chat_history.R's
  # replay_ui()), and what bookmark restore calls per snapshot message. Neither
  # scaffold is available to this trust boundary on its own, so exercising the
  # primitive directly covers both callers without depending on either.
  author <- shiny::MockShinySession$new()
  send_message(author, seg("<div>island</div>"), seg("<div>tool card</div>"))
  sanitized <- messages_input_value(
    reported_html(seg("<div>island</div>"), seg("<div>tool card</div>")),
    author
  )
  types <- vapply(
    sanitized[[1]]$segments,
    function(s) s$content_type,
    character(1)
  )
  expect_equal(types, c("html", "html"))

  # A replay goes through send_chat_action(), so the restoring session ends up
  # trusting what it just rendered -- that's what keeps a
  # replay-then-report-again chain valid without special-casing replay.
  restorer <- shiny::MockShinySession$new()
  expect_false(is_trusted_html_content(restorer, "<div>island</div>"))
  restore_history_message("chat", sanitized[[1]], session = restorer)
  expect_true(is_trusted_html_content(restorer, "<div>island</div>"))
  expect_true(is_trusted_html_content(restorer, "<div>tool card</div>"))

  rereported <- messages_input_value(
    reported_html(seg("<div>island</div>"), seg("<div>tool card</div>")),
    restorer
  )
  retypes <- vapply(
    rereported[[1]]$segments,
    function(s) s$content_type,
    character(1)
  )
  expect_equal(retypes, c("html", "html"))
})

test_that("a forged snapshot cannot replay attacker html through the store", {
  # End-to-end for the stored-script vector, mirroring the html_deps case in
  # test-html_deps_trust.R: both the history store and a server bookmark are
  # persisted then replayed into a (possibly different) later session, so
  # anything saved from the browser's report reaches that later session's
  # renderer via restore_history_message().
  attacker <- shiny::MockShinySession$new()
  forged <- reported_html(seg("<img src=x onerror=alert(1)>"))
  sanitized <- suppressWarnings(messages_input_value(forged, attacker))

  victim <- shiny::MockShinySession$new()
  captured <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      captured[[length(captured) + 1]] <<- action
      invisible()
    }
  )
  restore_history_message("chat", sanitized[[1]], session = victim)

  types <- unlist(
    lapply(captured, function(a) {
      vapply(a$message$segments, function(s) s$content_type, character(1))
    })
  )
  expect_true(length(types) > 0)
  expect_false("html" %in% types)
})
