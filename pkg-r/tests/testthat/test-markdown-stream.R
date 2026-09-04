library(htmltools)

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

  # TODO: it'd be nice to mock the messages that send_stream_message() sends
})

test_that("mixed initial content carries leaf-level provenance", {
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
  expect_true(segments[[2]]$trusted)
  expect_match(segments[[2]]$text, "<shiny-chat-raw-html>", fixed = TRUE)
  expect_match(segments[[2]]$text, "<div>This is HTML</div>", fixed = TRUE)
  expect_identical(el$attribs[["content-trusted"]], "false")
})
