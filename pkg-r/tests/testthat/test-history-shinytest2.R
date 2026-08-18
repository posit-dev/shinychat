test_that("file-backed history restores after reload", {
  skip_if_shinytest2_unavailable()

  history_dir <- withr::local_tempdir()
  withr::local_envvar(SHINYCHAT_HISTORY_TEST_DIR = history_dir)

  app <- shinytest2::AppDriver$new(
    test_path("apps/history-restore-on-reload"),
    name = "history-restore-on-reload",
    timeout = 30 * 1000
  )
  withr::defer(app$stop())
  chromote_session <- app$get_chromote_session()

  submit_message <- function(text) {
    app$run_js(
      sprintf(
        paste(
          "const input = document.querySelector('#chat [role=\"textbox\"]');",
          "input.focus();",
          "document.execCommand('insertText', false, %s);",
          sep = "\n"
        ),
        jsonlite::toJSON(text, auto_unbox = TRUE)
      )
    )
    chromote_session$Input$dispatchKeyEvent(
      type = "keyDown",
      code = "Enter",
      key = "Enter",
      windowsVirtualKeyCode = 13,
      nativeVirtualKeyCode = 13
    )
    chromote_session$Input$dispatchKeyEvent(
      type = "keyUp",
      code = "Enter",
      key = "Enter",
      windowsVirtualKeyCode = 13,
      nativeVirtualKeyCode = 13
    )
    app$wait_for_idle(timeout = 30 * 1000)
  }

  wait_for_message <- function(text) {
    escaped_text <- jsonlite::toJSON(text, auto_unbox = TRUE)
    app$wait_for_js(
      sprintf(
        paste(
          "const message = document.querySelector(",
          "'#chat .shiny-chat-messages-content > :last-child');",
          "message?.innerText === %s;",
          sep = "\n"
        ),
        escaped_text
      ),
      timeout = 30 * 1000
    )
    app$wait_for_idle(timeout = 30 * 1000)
  }

  reload_app <- function() {
    app$run_js("window.location.reload(); return true;", timeout = 30 * 1000)
    app$wait_for_idle(timeout = 30 * 1000)
  }

  messages <- function() {
    app$get_js(
      paste(
        "Array.from(document.querySelectorAll(",
        "'#chat .shiny-chat-messages-content > *')).map(",
        "(element) => element.innerText);",
        sep = "\n"
      )
    )
  }

  app$wait_for_js(
    "document.querySelector('#chat [role=\"textbox\"]') !== null;",
    timeout = 30 * 1000
  )

  submit_message("first")
  wait_for_message("echo: first")

  reload_app()
  wait_for_message("echo: first")

  submit_message("second")
  wait_for_message("echo: second")

  reload_app()
  wait_for_message("echo: second")
  expect_identical(
    unname(unlist(messages())),
    c("first", "echo: first", "second", "echo: second")
  )
})
