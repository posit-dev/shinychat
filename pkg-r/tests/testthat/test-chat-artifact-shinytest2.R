test_that("R artifact actions render dynamic Shiny content and preserve state", {
  skip_if_shinytest2_unavailable()

  app <- shinytest2::AppDriver$new(
    test_path("apps/page-chat-artifact"),
    name = "page-chat-artifact",
    width = 1440,
    height = 900,
    timeout = 30 * 1000
  )
  withr::defer(app$stop())

  artifact_state <- function() {
    jsonlite::fromJSON(app$get_js(
      paste(
        "(() => {",
        "const panel = document.querySelector('#chat .shiny-chat-artifact');",
        "const marker = panel?.querySelector(",
        "'.artifact-dependency-marker');",
        "const input = panel?.querySelector('#artifact_text');",
        "return JSON.stringify({",
        "  hidden: panel?.hidden,",
        "  title: panel?.querySelector('h2')?.innerText,",
        "  label: panel?.querySelector('.artifact-content-label')?.innerText,",
        "  value: input?.value,",
        "  echo: panel?.querySelector('#artifact_echo')?.innerText,",
        "  border: marker ? getComputedStyle(marker).borderTopColor : null",
        "});",
        "})()",
        sep = "\n"
      )
    ))
  }

  app$wait_for_js(
    "document.querySelector('#chat .shiny-chat-artifact') !== null;",
    timeout = 30 * 1000
  )
  app$wait_for_idle(timeout = 30 * 1000)

  initial <- artifact_state()
  expect_true(isTRUE(initial$hidden))
  expect_identical(initial$title, "Initial artifact")

  app$click(input = "show_artifact")
  app$wait_for_js(
    paste(
      "document.querySelector(",
      "'#chat .shiny-chat-artifact:not([hidden]) .artifact-content-label'",
      ")?.innerText === 'Initial content';",
      sep = "\n"
    ),
    timeout = 30 * 1000
  )
  app$wait_for_idle(timeout = 30 * 1000)

  shown <- artifact_state()
  expect_false(isTRUE(shown$hidden))
  expect_identical(shown$title, "Initial artifact")
  expect_identical(shown$label, "Initial content")
  expect_identical(shown$value, "Initial")
  expect_identical(shown$border, "rgb(24, 119, 242)")

  app$set_inputs(artifact_text = "browser value")
  app$wait_for_js(
    paste(
      "document.querySelector('#chat #artifact_echo')?.innerText ===",
      jsonlite::toJSON("Echo: browser value", auto_unbox = TRUE),
      ";",
      sep = "\n"
    ),
    timeout = 30 * 1000
  )

  app$click(input = "update_artifact")
  app$wait_for_js(
    paste(
      "document.querySelector(",
      "'#chat .shiny-chat-artifact:not([hidden]) h2'",
      ")?.innerText === 'Updated artifact';",
      sep = "\n"
    ),
    timeout = 30 * 1000
  )
  app$wait_for_idle(timeout = 30 * 1000)

  updated <- artifact_state()
  expect_identical(updated$title, "Updated artifact")
  expect_identical(updated$label, "Updated content")
  expect_identical(updated$value, "Updated")
  expect_identical(updated$border, "rgb(24, 119, 242)")

  app$click(input = "hide_artifact")
  app$wait_for_js(
    "document.querySelector('#chat .shiny-chat-artifact')?.hidden === true;",
    timeout = 30 * 1000
  )
  app$wait_for_idle(timeout = 30 * 1000)

  app$click(input = "show_preserved")
  app$wait_for_js(
    paste(
      "document.querySelector(",
      "'#chat .shiny-chat-artifact:not([hidden]) #artifact_text'",
      ")?.value === 'Updated';",
      sep = "\n"
    ),
    timeout = 30 * 1000
  )
  app$wait_for_idle(timeout = 30 * 1000)
  preserved <- artifact_state()
  expect_false(isTRUE(preserved$hidden))
  expect_identical(preserved$title, "Updated artifact")
  expect_identical(preserved$value, "Updated")

  app$click(input = "toggle_artifact")
  app$wait_for_js(
    "document.querySelector('#chat .shiny-chat-artifact')?.hidden === true;",
    timeout = 30 * 1000
  )
  app$click(input = "toggle_artifact")
  app$wait_for_js(
    paste(
      "document.querySelector(",
      "'#chat .shiny-chat-artifact:not([hidden]) #artifact_text'",
      ")?.value === 'Updated';",
      sep = "\n"
    ),
    timeout = 30 * 1000
  )

  app$click(selector = "button[data-page-target='settings']")
  app$wait_for_idle(timeout = 30 * 1000)
  expect_true(
    app$get_js(paste(
      "document.querySelector('#chat')?.closest(",
      "'.shiny-chat-page-panel')?.hidden === true;",
      sep = "\n"
    ))
  )

  app$click(selector = "button[data-page-home]")
  app$wait_for_js(
    paste(
      "document.querySelector('shiny-chat-page')?.dataset.activePage ===",
      "'__home__' && document.querySelector(",
      "'#chat .shiny-chat-artifact:not([hidden]) #artifact_text'",
      ")?.value === 'Updated';",
      sep = "\n"
    ),
    timeout = 30 * 1000
  )
  app$wait_for_idle(timeout = 30 * 1000)
  after_navigation <- artifact_state()
  expect_false(isTRUE(after_navigation$hidden))
  expect_identical(after_navigation$title, "Updated artifact")
  expect_identical(after_navigation$value, "Updated")
  expect_identical(after_navigation$echo, "Echo: Updated")
})
