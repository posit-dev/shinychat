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

  # TODO: it'd be nice to mock the shinyChatMessage custom messages
})

test_that("chat_append_stream() returns the stream contents as string if all text", {
  local_mocked_bindings(
    chat_append_message = coro::async(function(...) invisible()),
    chat_update_bookmark = function(id, p, session) p
  )

  stream <- coro::async_generator(function() {
    for (i in c("Hello", ",", " world", "!")) {
      yield(i)
    }
  })

  session <- list(sendCustomMessage = function(...) {})

  p <- chat_append_stream("chat", stream(), session = session)
  res <- sync(p)

  expect_promise(p, "fulfilled")
  expect_equal(res, "Hello, world!")
})

test_that("chat_append_stream() returns the stream contents as list if not all text", {
  local_mocked_bindings(
    chat_append_message = coro::async(function(...) invisible()),
    chat_update_bookmark = function(id, p, session) p
  )

  stream <- coro::async_generator(function() {
    for (i in c("Hello", ",", " world", "!")) {
      yield(ellmer::ContentText(i))
    }
  })

  session <- list(sendCustomMessage = function(...) {})
  p <- chat_append_stream("chat", stream(), session = session)
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
