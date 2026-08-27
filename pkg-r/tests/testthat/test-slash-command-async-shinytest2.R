press_enter <- function(chromote_session) {
  for (event_type in c("keyDown", "keyUp")) {
    chromote_session$Input$dispatchKeyEvent(
      type = event_type,
      code = "Enter",
      key = "Enter",
      windowsVirtualKeyCode = 13,
      nativeVirtualKeyCode = 13
    )
  }
}

# Type a slash command into the chat input and submit it. The palette item is
# clicked directly (rather than selecting via Enter) because Enter selects the
# first *filtered* item, which may be a different command whose name also
# matches the query (e.g. typing "/work" also matches "/worksync").
submit_slash_command <- function(app, chromote_session, command) {
  command_json <- jsonlite::toJSON(paste0("/", command), auto_unbox = TRUE)

  app$run_js(
    sprintf(
      paste(
        "const input = document.querySelector('#chat [role=\"textbox\"]');",
        "input.focus();",
        "document.execCommand('insertText', false, %s);",
        sep = "\n"
      ),
      command_json
    )
  )
  app$wait_for_js(
    sprintf(
      paste(
        "Array.from(document.querySelectorAll(",
        "'.shiny-chat-slash-palette-name')).some(",
        "(el) => el.textContent === %s);",
        sep = "\n"
      ),
      command_json
    )
  )
  app$run_js(
    sprintf(
      paste(
        "Array.from(document.querySelectorAll(",
        "'.shiny-chat-slash-palette-item')).find(",
        "(el) => el.querySelector('.shiny-chat-slash-palette-name')",
        "?.textContent === %s)?.click();",
        sep = "\n"
      ),
      command_json
    )
  )
  app$wait_for_js(
    "document.querySelector('.shiny-chat-slash-palette') === null"
  )
  # Confirm the intended command is what's actually in the editor before
  # submitting.
  app$wait_for_js(
    sprintf(
      paste(
        "document.querySelector('#chat [role=\"textbox\"]')",
        "?.innerText.trim() === %s;",
        sep = "\n"
      ),
      command_json
    )
  )
  press_enter(chromote_session)
  app$wait_for_idle()
}

expected_response <-
  "Why did the chicken cross the road? To get to the other side!"

wait_for_response <- function(app, timeout = 15 * 1000) {
  tryCatch(
    {
      app$wait_for_js(
        sprintf(
          paste(
            "Array.from(document.querySelectorAll(",
            "'#chat .shiny-chat-messages-content > *')).some(",
            "(el) => el.innerText.includes(%s));",
            sep = "\n"
          ),
          jsonlite::toJSON(expected_response, auto_unbox = TRUE)
        ),
        timeout = timeout
      )
      TRUE
    },
    error = function(e) FALSE
  )
}

message_list_text <- function(app) {
  app$get_js(
    paste(
      "Array.from(document.querySelectorAll(",
      "'#chat .shiny-chat-messages-content > *')).map(",
      "(element) => element.innerText);",
      sep = "\n"
    )
  )
}

test_that("slash-command handler can append a synchronous response", {
  skip_if_shinytest2_unavailable()

  app <- shinytest2::AppDriver$new(
    test_path("apps/slash-command-async-stream"),
    name = "slash-command-sync-control",
    timeout = 30 * 1000
  )
  withr::defer(app$stop())
  chromote_session <- app$get_chromote_session()

  app$wait_for_js(
    "document.querySelector('#chat [role=\"textbox\"]') !== null"
  )
  app$wait_for_idle()

  submit_slash_command(app, chromote_session, "worksync")

  appeared <- wait_for_response(app)
  expect_true(
    appeared,
    info = sprintf(
      "The sync slash-command response never appeared. Message list: %s",
      paste(unlist(message_list_text(app)), collapse = " | ")
    )
  )
})

test_that("slash-command handler can stream an async response (issue #336)", {
  skip_if_shinytest2_unavailable()

  app <- shinytest2::AppDriver$new(
    test_path("apps/slash-command-async-stream"),
    name = "slash-command-async-stream",
    timeout = 30 * 1000
  )
  withr::defer(app$stop())
  chromote_session <- app$get_chromote_session()

  app$wait_for_js(
    "document.querySelector('#chat [role=\"textbox\"]') !== null"
  )
  app$wait_for_idle()

  submit_slash_command(app, chromote_session, "work")

  # The response takes ~1s to stream (0.5s initial sleep + per-chunk sleeps).
  # With the bug, `remove_loading` force-finalizes the streaming message the
  # moment the handler returns, so every chunk is dropped and the text never
  # appears.
  appeared <- wait_for_response(app)
  expect_true(
    appeared,
    info = sprintf(
      paste(
        "The async slash-command response never appeared in the chat.",
        "Message list contents at timeout: %s"
      ),
      paste(unlist(message_list_text(app)), collapse = " | ")
    )
  )
})
