page_chat_example_path <- function(...) {
  testthat::test_path("..", "..", "inst", "examples-shiny", ...)
}

page_chat_example_names <- c(
  "page-chat-artifact-controls",
  "page-chat-navigation"
)

test_that("page-chat R examples parse and construct", {
  apps <- c(
    page_chat_example_path("page-chat-artifact-controls", "app.R"),
    page_chat_example_path("page-chat-navigation", "app.R")
  )

  for (app in apps) {
    expect_no_error(parse(file = app))

    env <- new.env(parent = globalenv())
    source(app, local = env)
    expect_s3_class(env$ui, "shiny.tag.list")
  }
})

test_that("page-chat R examples are discoverable as package examples", {
  examples_dir <- page_chat_example_path()
  expect_true(dir.exists(examples_dir))
  expect_setequal(
    list.dirs(examples_dir, full.names = FALSE, recursive = FALSE),
    page_chat_example_names
  )

  for (name in page_chat_example_names) {
    example_dir <- system.file(
      "examples-shiny",
      name,
      package = "shinychat"
    )
    if (!nzchar(example_dir)) {
      example_dir <- page_chat_example_path(name)
    }
    expect_true(dir.exists(example_dir))
    expect_true(file.exists(file.path(example_dir, "app.R")))
  }
})
