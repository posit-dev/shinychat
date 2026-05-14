library(htmltools)

# Helper: create a mock session and collect custom messages sent to it.
# Uses an environment so the message list is captured by reference.
mock_session_with_spy <- function() {
  sess <- shiny::MockShinySession$new()
  spy_env <- new.env(parent = emptyenv())
  spy_env$messages <- list()
  sess$sendCustomMessage <- function(type, msg) {
    spy_env$messages[[length(spy_env$messages) + 1]] <- list(type = type, message = msg)
  }
  list(session = sess, spy_env = spy_env)
}

# Return the custom messages recorded by a spy session.
spy_messages <- function(spy) spy$spy_env$messages


# ── chat_greeting() ────────────────────────────────────────────────────────────

test_that("chat_greeting() returns class 'chat_greeting' with all fields", {
  g <- chat_greeting("Hello")
  expect_s3_class(g, "chat_greeting")
  expect_equal(g$content, "Hello")
  expect_true(g$dismissible)
  expect_false(g$include_in_history)
})

test_that("chat_greeting() stores non-default option values", {
  g <- chat_greeting(
    "Hi",
    dismissible = FALSE,
    include_in_history = TRUE
  )
  expect_false(g$dismissible)
  expect_true(g$include_in_history)
})

test_that("chat_greeting() accepts HTML() content", {
  g <- chat_greeting(HTML("<b>bold</b>"))
  expect_s3_class(g, "chat_greeting")
  expect_s3_class(g$content, "html")
  expect_equal(as.character(g$content), "<b>bold</b>")
})

test_that("chat_greeting() accepts htmltools tag content", {
  tag_content <- tags$div("Welcome")
  g <- chat_greeting(tag_content)
  expect_s3_class(g, "chat_greeting")
  expect_s3_class(g$content, "shiny.tag")
})


# ── chat_ui(greeting = ...) ───────────────────────────────────────────────────

test_that("chat_ui() plain string greeting produces markdown content_type, dismissible, no include_in_history", {
  ui <- chat_ui("chat", greeting = "## Hello")
  attr_raw <- ui$attribs$greeting
  expect_false(is.null(attr_raw))
  payload <- jsonlite::fromJSON(attr_raw)
  expect_equal(payload$content, "## Hello")
  expect_equal(payload$content_type, "markdown")
  expect_true(payload$options$dismissible)
  expect_false("include_in_history" %in% names(payload))
  expect_false("include_in_history" %in% names(payload$options))
})

test_that("chat_ui() chat_greeting with dismissible=FALSE serializes correctly", {
  g <- chat_greeting("## Hi", dismissible = FALSE)
  ui <- chat_ui("chat", greeting = g)
  payload <- jsonlite::fromJSON(ui$attribs$greeting)
  expect_equal(payload$content, "## Hi")
  expect_equal(payload$content_type, "markdown")
  expect_false(payload$options$dismissible)
  expect_false("include_in_history" %in% names(payload))
})

test_that("chat_ui() include_in_history never appears in serialized JSON even when TRUE", {
  g <- chat_greeting("Hi", include_in_history = TRUE)
  ui <- chat_ui("chat", greeting = g)
  payload <- jsonlite::fromJSON(ui$attribs$greeting)
  expect_false("include_in_history" %in% names(payload))
  expect_false("include_in_history" %in% names(payload$options))
})

test_that("chat_ui() HTML() greeting produces html content_type", {
  ui <- chat_ui("chat", greeting = HTML("<b>hi</b>"))
  payload <- jsonlite::fromJSON(ui$attribs$greeting)
  expect_equal(payload$content_type, "html")
  expect_equal(payload$content, "<b>hi</b>")
})

test_that("chat_ui() tag greeting produces html content_type and attaches dependencies", {
  tag_content <- tags$div("Hello", class = "greeting")
  ui <- chat_ui("chat", greeting = tag_content)
  payload <- jsonlite::fromJSON(ui$attribs$greeting)
  expect_equal(payload$content_type, "html")
  deps <- htmltools::findDependencies(ui)
  dep_names <- vapply(deps, `[[`, character(1), "name")
  expect_true("shinychat" %in% dep_names)
})

test_that("chat_ui() tag with explicit htmlDependency attaches that dep", {
  tag_content <- tags$div(
    "Hello",
    htmlDependency("my-dep", "1.0.0", ".")
  )
  ui <- chat_ui("chat", greeting = tag_content)
  deps <- htmltools::findDependencies(ui)
  dep_names <- vapply(deps, `[[`, character(1), "name")
  expect_true("my-dep" %in% dep_names)
})

test_that("chat_ui() rejects generator as greeting", {
  gen <- coro::async_generator(function() yield("x"))
  expect_error(
    chat_ui("chat", greeting = gen()),
    regexp = "generator or promise"
  )
})

test_that("chat_ui() snapshot for plain string greeting", {
  expect_snapshot(chat_ui("chat", greeting = "## Welcome!"))
})

test_that("chat_ui() snapshot for chat_greeting with dismissible=FALSE", {
  expect_snapshot(chat_ui("chat", greeting = chat_greeting("## Hi", dismissible = FALSE)))
})


# ── chat_set_greeting() ───────────────────────────────────────────────────────

test_that("chat_set_greeting() NULL sends greeting_clear action", {
  spy <- mock_session_with_spy()
  shiny::withReactiveDomain(spy$session, {
    chat_set_greeting("chat", NULL, session = spy$session)
  })
  msgs <- spy_messages(spy)
  expect_length(msgs, 1)
  expect_equal(msgs[[1]]$type, "shinyChatMessage")
  expect_equal(msgs[[1]]$message$action$type, "greeting_clear")
})

test_that("chat_set_greeting() plain string sends greeting action with markdown content_type", {
  spy <- mock_session_with_spy()
  shiny::withReactiveDomain(spy$session, {
    chat_set_greeting("chat", "Hello", session = spy$session)
  })
  msgs <- spy_messages(spy)
  expect_length(msgs, 1)
  action <- msgs[[1]]$message$action
  expect_equal(action$type, "greeting")
  expect_equal(action$content_type, "markdown")
  expect_true(action$options$dismissible)
  expect_false("include_in_history" %in% names(action))
})

test_that("chat_set_greeting() HTML() content sends html content_type", {
  spy <- mock_session_with_spy()
  shiny::withReactiveDomain(spy$session, {
    chat_set_greeting("chat", chat_greeting(HTML("<b>hi</b>")), session = spy$session)
  })
  msgs <- spy_messages(spy)
  action <- msgs[[1]]$message$action
  expect_equal(action$type, "greeting")
  expect_equal(action$content_type, "html")
  expect_equal(action$content, "<b>hi</b>")
})

test_that("chat_set_greeting() include_in_history never sent to client", {
  spy <- mock_session_with_spy()
  shiny::withReactiveDomain(spy$session, {
    chat_set_greeting(
      "chat",
      chat_greeting("Hi", include_in_history = TRUE),
      session = spy$session
    )
  })
  msgs <- spy_messages(spy)
  action <- msgs[[1]]$message$action
  expect_false("include_in_history" %in% names(action))
  expect_false("include_in_history" %in% names(action$options))
})

test_that("chat_set_greeting() generator sends greeting_start, greeting_chunk(s), greeting_end", {
  spy <- mock_session_with_spy()
  chunks <- c("He", "ll", "o")
  gen <- coro::async_generator(function() {
    for (ch in chunks) yield(ch)
  })
  shiny::withReactiveDomain(spy$session, {
    p <- chat_set_greeting("chat", chat_greeting(gen()), session = spy$session)
    done <- FALSE
    promises::then(p, function(x) { done <<- TRUE }, function(e) { done <<- TRUE })
    while (!done) later::run_now(0.1)
  })
  msgs <- spy_messages(spy)
  action_types <- vapply(msgs, function(m) m$message$action$type, character(1))
  expect_equal(action_types[[1]], "greeting_start")
  expect_equal(action_types[[length(action_types)]], "greeting_end")
  chunk_types <- action_types[action_types == "greeting_chunk"]
  expect_gte(length(chunk_types), 1)
  chunk_msgs <- Filter(function(m) m$message$action$type == "greeting_chunk", msgs)
  operations <- vapply(chunk_msgs, function(m) m$message$action$operation, character(1))
  expect_true(all(operations == "append"))
})
