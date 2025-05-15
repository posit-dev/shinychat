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

    expect_s3_class(p, "promise")
    expect_true(promises::is.promise(p))
    expect_equal(attr(p, "promise_impl")$status(), "rejected")

    expect_s3_class(res, class = c("condition", "error"))
    expect_s3_class(res, class = "shiny.silent.error")
    expect_equal(conditionMessage(res), "boom")
  })
})
