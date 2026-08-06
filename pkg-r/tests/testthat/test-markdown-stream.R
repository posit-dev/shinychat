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

test_that("non-string and HTML() content is always labelled html, regardless of content_type", {
  tag <- output_markdown_stream("stream", content = div("Hello"))
  expect_equal(tag$attribs[["content-type"]], "html")
  expect_match(tag$attribs[["content"]], "shinychat-raw-html", fixed = TRUE)

  # Even if the caller explicitly (and wrongly) asks for markdown/text: a Tag
  # is already rendered into a <shinychat-raw-html> island, which is only
  # ever valid as "html".
  tag <- output_markdown_stream(
    "stream",
    content = div("Hello"),
    content_type = "markdown"
  )
  expect_equal(tag$attribs[["content-type"]], "html")

  # htmltools::HTML() is a character vector too (class c("html", "character")),
  # but it gets the same wrapping and forced "html" as a Tag -- it's meant to
  # render exactly like real HTML (e.g. Shiny bindings inside it still work),
  # not the fast path used for a plain string.
  tag <- output_markdown_stream("stream", content = HTML("<b>Hello</b>"))
  expect_equal(tag$attribs[["content-type"]], "html")
  expect_match(tag$attribs[["content"]], "shinychat-raw-html", fixed = TRUE)

  tag <- output_markdown_stream(
    "stream",
    content = HTML("<b>Hello</b>"),
    content_type = "text"
  )
  expect_equal(tag$attribs[["content-type"]], "html")
})

test_that("a plain string's content_type defaults to markdown, or respects an explicit value", {
  tag <- output_markdown_stream("stream", content = "Hello")
  expect_equal(tag$attribs[["content-type"]], "markdown")

  tag <- output_markdown_stream(
    "stream",
    content = "Hello",
    content_type = "text"
  )
  expect_equal(tag$attribs[["content-type"]], "text")
})
