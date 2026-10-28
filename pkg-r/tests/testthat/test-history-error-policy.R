test_that("history notifications are safe independently of Shiny sanitization", {
  notifications <- list()
  local_mocked_bindings(
    showNotification = function(ui, ...) {
      notifications[[length(notifications) + 1L]] <<- ui
    },
    .package = "shiny"
  )
  for (sanitize in c(FALSE, TRUE)) {
    withr::local_options(shiny.sanitize.errors = sanitize)
    for (err in list(
      simpleError("PRIVATE_HISTORY_DETAIL"),
      structure(
        simpleError("PRIVATE_CUSTOM_DETAIL"),
        class = c(
          "shiny.custom.error",
          "simpleError",
          "error",
          "condition"
        )
      )
    )) {
      warning <- NULL
      withCallingHandlers(
        notify_error("Could not load conversation", err),
        warning = function(w) {
          warning <<- w
          invokeRestart("muffleWarning")
        }
      )
      expect_identical(
        tail(notifications, 1L)[[1L]],
        "Could not load conversation"
      )
      expect_s3_class(warning, "warning")
      expect_identical(warning$parent, err)
    }
  }
})

test_that("live chat errors still follow Shiny sanitization", {
  err <- simpleError("PRIVATE_LIVE_DETAIL")
  withr::local_options(shiny.sanitize.errors = FALSE)
  expect_match(sanitized_chat_error(err), "PRIVATE_LIVE_DETAIL", fixed = TRUE)
  withr::local_options(shiny.sanitize.errors = TRUE)
  expect_false(grepl(
    "PRIVATE_LIVE_DETAIL",
    sanitized_chat_error(err),
    fixed = TRUE
  ))
})
