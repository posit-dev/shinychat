test_that("fallback_title() uses first user message", {
  turns <- list(
    list(
      class = "ellmer::UserTurn",
      version = 1L,
      props = list(
        contents = list(
          list(
            class = "ellmer::ContentText",
            version = 1L,
            props = list(text = "Tell me about penguins")
          )
        )
      )
    ),
    list(
      class = "ellmer::AssistantTurn",
      version = 1L,
      props = list(
        contents = list(
          list(
            class = "ellmer::ContentText",
            version = 1L,
            props = list(text = "Penguins are fascinating birds...")
          )
        )
      )
    )
  )
  expect_equal(fallback_title(turns), "Tell me about penguins")
})

test_that("fallback_title() truncates long messages", {
  long_text <- paste(rep("word", 20), collapse = " ")
  turns <- list(
    list(
      class = "ellmer::UserTurn",
      version = 1L,
      props = list(
        contents = list(
          list(
            class = "ellmer::ContentText",
            version = 1L,
            props = list(text = long_text)
          )
        )
      )
    )
  )
  result <- fallback_title(turns)
  expect_true(nchar(result) <= 50)
  expect_true(endsWith(result, "..."))
})

test_that("fallback_title() returns 'New chat' for empty turns", {
  expect_equal(fallback_title(list()), "New chat")
})

test_that("history_options() accepts 'auto', a function, or NULL for title", {
  expect_no_error(history_options(title = "auto"))
  expect_no_error(history_options(title = function(recorded_turns) "Title"))
  expect_no_error(history_options(title = NULL))
})

test_that("history_options() errors on unrecognized title values", {
  expect_error(history_options(title = "fallback"), "auto")
  expect_error(history_options(title = TRUE), "auto")
})
