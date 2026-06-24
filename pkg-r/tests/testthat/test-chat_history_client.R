test_that("get_turns_recorded() serializes ellmer turns", {
  skip_if_not_installed("ellmer")
  turn <- ellmer::UserTurn(list(ellmer::ContentText("hello")))
  client <- list(
    get_turns = function() list(turn),
    get_tools = function() list()
  )
  class(client) <- c("Chat", "R6")

  recorded <- get_turns_recorded(client)
  expect_length(recorded, 1)
  expect_equal(recorded[[1]]$class, "ellmer::UserTurn")
  expect_true("contents" %in% names(recorded[[1]]$props))
})

test_that("set_turns_recorded() round-trips through record/replay", {
  skip_if_not_installed("ellmer")
  turn <- ellmer::UserTurn(list(ellmer::ContentText("hello")))
  recorded <- ellmer::contents_record(turn)

  turns_set <- NULL
  client <- list(
    get_tools = function() list(),
    set_turns = function(value) {
      turns_set <<- value
    }
  )
  class(client) <- c("Chat", "R6")

  set_turns_recorded(client, list(recorded))
  expect_length(turns_set, 1)
  expect_true(S7::S7_inherits(turns_set[[1]], ellmer::UserTurn))
  expect_equal(turns_set[[1]]@contents[[1]]@text, "hello")
})

test_that("turn_fallback_markdown() extracts text", {
  recorded <- list(
    class = "ellmer::UserTurn",
    version = 1L,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1L,
          props = list(text = "Hello world")
        )
      )
    )
  )
  expect_equal(turn_fallback_markdown(recorded), "Hello world")
})

test_that("turn_fallback_markdown() joins multiple text contents", {
  recorded <- list(
    class = "ellmer::AssistantTurn",
    version = 1L,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1L,
          props = list(text = "Part 1")
        ),
        list(
          class = "ellmer::ContentText",
          version = 1L,
          props = list(text = "Part 2")
        )
      )
    )
  )
  expect_equal(turn_fallback_markdown(recorded), "Part 1Part 2")
})
