library(htmltools)

test_that("Chat component markup", {
  expect_snapshot(
    cat(format(output_markdown_stream("stream")))
  )

  expect_snapshot({
    cat(format(output_markdown_stream("stream", content = "Foo\nBar")))
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
