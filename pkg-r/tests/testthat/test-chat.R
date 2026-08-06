library(htmltools)

test_that("Chat component markup", {
  expect_snapshot(chat_ui("chat"))

  expect_snapshot({
    chat_ui("chat", messages = list("Foo", "Bar"))
  })

  expect_snapshot({
    chat_ui(
      "chat",
      messages = list(
        list(content = "Assistant", role = "assistant"),
        list(content = "User", role = "user")
      )
    )
  })

  expect_snapshot({
    chat_ui(
      "chat",
      messages = list(
        div("Hello"),
        span("world")
      )
    )
  })

  expect_snapshot({
    render_tags(
      chat_ui(
        "chat",
        messages = list(
          div("Hello", htmlDependency("foo", "1.0.0", "")),
          span("world")
        )
      )
    )
  })

  # Initial messages with react elements are island-split
  expect_snapshot({
    react_tag <- tags$div("react", `data-shinychat-react` = NA)
    chat_ui(
      "chat",
      messages = list(
        tagList(tags$div("before"), react_tag, tags$div("after"))
      )
    )
  })

  # TODO: it'd be nice to mock the shinyChatMessage custom messages
})

test_that("chat_ui() labels non-string messages as html content", {
  md_only <- as.character(chat_ui("chat", messages = list("plain string")))
  expect_false(grepl("content-type", md_only, fixed = TRUE))

  tagged <- as.character(chat_ui("chat", messages = list(htmltools::div("hi"))))
  expect_match(tagged, 'content-type="html"', fixed = TRUE)

  # The island wrapper is what the html content type exists to protect: as
  # markdown it would be escaped and shown as literal text.
  expect_match(tagged, "shinychat-raw-html", fixed = TRUE)

  # htmltools::HTML() is a character vector too (class c("html", "character")),
  # so is.character() alone would treat it as markdown -- it needs its own
  # branch, same as chat_set_greeting()'s check. It gets the same
  # <shinychat-raw-html> wrapping as a Tag/TagList, so e.g. Shiny bindings
  # inside an HTML() string still work.
  html_string <- as.character(
    chat_ui("chat", messages = list(htmltools::HTML("<b>hi</b>")))
  )
  expect_match(html_string, 'content-type="html"', fixed = TRUE)
  expect_match(html_string, "shinychat-raw-html", fixed = TRUE)
})

test_that("chat_append_stream() returns the stream contents as string if all text", {
  local_mocked_bindings(
    chat_append_message = coro::async(function(...) invisible())
  )

  stream <- coro::async_generator(function() {
    for (i in c("Hello", ",", " world", "!")) {
      yield(i)
    }
  })

  p <- chat_append_stream("chat", stream())
  res <- sync(p)

  expect_promise(p, "fulfilled")
  expect_equal(res, "Hello, world!")
})

test_that("chat_append_stream() returns the stream contents as list if not all text", {
  local_mocked_bindings(
    chat_append_message = coro::async(function(...) invisible())
  )

  stream <- coro::async_generator(function() {
    for (i in c("Hello", ",", " world", "!")) {
      yield(ellmer::ContentText(i))
    }
  })

  p <- chat_append_stream("chat", stream())
  res <- sync(p)

  expect_promise(p, "fulfilled")

  expect_true(is.list(res))
  expect_true(every(res, inherits, "ellmer::ContentText"))
  expect_equal(
    paste(map_chr(res, ellmer::contents_text), collapse = ""),
    "Hello, world!"
  )
})

test_that("chat_append_stream() handles errors in the stream", {
  local_mocked_bindings(
    chat_append_message = coro::async(function(...) invisible())
  )

  shiny::withReactiveDomain(shiny::MockShinySession$new(), {
    stream <- coro::async_generator(function() {
      for (i in 1:3) {
        yield(i)
      }
      stop("boom")
    })

    p <- chat_append_stream("chat", stream())
    expect_warning(
      res <- tryCatch(sync(p), error = identity),
      regexp = 'chat_append_stream'
    )

    expect_promise(p, "rejected")

    expect_s3_class(res, class = c("condition", "error"))
    expect_s3_class(res, class = "shiny.silent.error")
    expect_equal(conditionMessage(res), "boom")
  })
})

test_that("chat_server handles string user_input values", {
  local_mocked_bindings(
    chat_restore = function(...) function() invisible(NULL),
    chat_append = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  args_seen <- NULL
  client <- structure(
    list(
      stream_async = function(...) {
        args_seen <<- rlang::list2(...)
        NULL
      },
      last_turn = function() NULL
    ),
    class = "Chat"
  )

  shiny::testServer(
    function(input, output, session) {
      chat_server(
        "chat",
        client,
        history = FALSE,
        session = session
      )
    },
    {
      expect_no_warning(session$setInputs(chat_user_input = "hello"))
      expect_identical(args_seen[[1]], "hello")
    }
  )
})

test_that("chat_append_message() emits segment payloads incl. thinking", {
  captured <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      captured[[length(captured) + 1]] <<- action
      invisible()
    }
  )
  session <- shiny::MockShinySession$new()

  chat_append_message(
    "chat",
    list(role = "assistant", content = "hello"),
    chunk = FALSE,
    session = session
  )
  th <- structure("reasoning", class = "shinychat_thinking")
  chat_append_message(
    "chat",
    list(role = "assistant", content = th),
    chunk = TRUE,
    session = session
  )

  msg <- captured[[1]]
  expect_equal(msg$type, "message")
  expect_null(msg$message$content)
  expect_equal(msg$message$segments[[1]]$content, "hello")
  expect_equal(msg$message$segments[[1]]$content_type, "markdown")

  chunk <- captured[[2]]
  expect_equal(chunk$content_type, "thinking")
})

test_that("chat_append_message() labels content without an explicit html class as html", {
  captured <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      captured[[length(captured) + 1]] <<- action
      invisible()
    }
  )
  session <- shiny::MockShinySession$new()

  # A bare list of tag children (not wrapped in tagList()) has none of the
  # classes is_html's allowlist checks for, but pre_process_ui() still
  # resolves it via as.tags() and wraps it in a <shinychat-raw-html> island --
  # same as chat_ui()'s and chat_set_greeting()'s HTML()/Tag/TagList content.
  chat_append_message(
    "chat",
    list(role = "assistant", content = list(htmltools::div("hi"))),
    chunk = FALSE,
    session = session
  )

  msg <- captured[[1]]
  segment <- msg$message$segments[[1]]
  expect_equal(segment$content_type, "html")
  expect_match(segment$content, "shinychat-raw-html", fixed = TRUE)
})
