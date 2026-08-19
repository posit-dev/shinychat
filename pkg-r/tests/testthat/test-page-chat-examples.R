page_chat_example_path <- function(...) {
  testthat::test_path("..", "..", "..", "examples", "page-chat", ...)
}

test_that("tracked page-chat R examples parse and construct", {
  apps <- c(
    page_chat_example_path("artifact-controls", "app.R"),
    page_chat_example_path("navigation", "app.R")
  )

  for (app in apps) {
    expect_no_error(parse(file = app))

    env <- new.env(parent = globalenv())
    source(app, local = env)
    expect_s3_class(env$ui, "shiny.tag.list")
  }
})
