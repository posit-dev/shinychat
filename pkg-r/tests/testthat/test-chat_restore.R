test_that("encode/decode UI snapshot round-trips a simple message", {
  messages <- list(
    list(
      role = "user",
      segments = list(list(content = "hi", content_type = "markdown"))
    )
  )
  encoded <- encode_ui_snapshot(messages)
  expect_type(encoded, "character")
  expect_length(encoded, 1L)
  expect_identical(decode_ui_snapshot(encoded), messages)
})

test_that("encode/decode UI snapshot preserves htmlDeps and attachments", {
  messages <- list(
    list(
      role = "assistant",
      segments = list(
        list(content = "**hi** (displayed)", content_type = "html")
      ),
      htmlDeps = list(
        list(name = "widget", version = "1.0", src = list(href = "w"))
      ),
      attachments = list(
        list(content_type = "image/png", url = "data:...", filename = "a.png")
      )
    )
  )
  expect_identical(decode_ui_snapshot(encode_ui_snapshot(messages)), messages)
})

test_that("encode returns NULL for empty input; decode guards non-values", {
  expect_null(encode_ui_snapshot(list()))
  expect_null(encode_ui_snapshot(NULL))
  expect_null(decode_ui_snapshot(NULL))
  expect_null(decode_ui_snapshot(""))
  expect_null(decode_ui_snapshot(NA_character_))
})
