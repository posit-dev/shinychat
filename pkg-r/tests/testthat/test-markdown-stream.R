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

test_that("non-string content is always labelled html, regardless of content_type", {
  tag <- output_markdown_stream("stream", content = div("Hello"))
  expect_equal(tag$attribs[["content-type"]], "html")

  # Even if the caller explicitly (and wrongly) asks for markdown.
  tag <- output_markdown_stream(
    "stream",
    content = div("Hello"),
    content_type = "markdown"
  )
  expect_equal(tag$attribs[["content-type"]], "html")

  # A plain string keeps whatever the caller asked for.
  tag <- output_markdown_stream(
    "stream",
    content = "Hello",
    content_type = "text"
  )
  expect_equal(tag$attribs[["content-type"]], "text")
})
