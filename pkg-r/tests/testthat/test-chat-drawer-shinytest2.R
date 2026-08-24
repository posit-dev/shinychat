test_that("R drawer actions render dynamic Shiny content and preserve state", {
  skip_if_shinytest2_unavailable()

  app <- shinytest2::AppDriver$new(
    test_path("apps/page-chat-drawer"),
    name = "page-chat-drawer",
    width = 1440,
    height = 900,
    timeout = 30 * 1000
  )
  withr::defer(app$stop())

  drawer_state <- function() {
    jsonlite::fromJSON(app$get_js(
      paste(
        "(() => {",
        "const panel = document.querySelector('#chat .shiny-chat-drawer');",
        "const marker = panel?.querySelector(",
        "'.drawer-dependency-marker');",
        "const input = panel?.querySelector('#drawer_text');",
        "return JSON.stringify({",
        "  hidden: panel?.hidden,",
        "  title: panel?.querySelector('h2')?.innerText,",
        "  label: panel?.querySelector('.drawer-content-label')?.innerText,",
        "  value: input?.value,",
        "  echo: panel?.querySelector('#drawer_echo')?.innerText,",
        "  border: marker ? getComputedStyle(marker).borderTopColor : null",
        "});",
        "})()",
        sep = "\n"
      )
    ))
  }

  app$wait_for_js(
    "document.querySelector('#chat .shiny-chat-drawer') !== null;",
    timeout = 30 * 1000
  )
  app$wait_for_idle(timeout = 30 * 1000)

  initial <- drawer_state()
  expect_true(isTRUE(initial$hidden))
  expect_identical(initial$title, "Initial drawer")

  app$click(input = "show_drawer")
  app$wait_for_js(
    paste(
      "document.querySelector(",
      "'#chat .shiny-chat-drawer:not([hidden]) .drawer-content-label'",
      ")?.innerText === 'Initial content';",
      sep = "\n"
    ),
    timeout = 30 * 1000
  )
  app$wait_for_idle(timeout = 30 * 1000)

  shown <- drawer_state()
  expect_false(isTRUE(shown$hidden))
  expect_identical(shown$title, "Initial drawer")
  expect_identical(shown$label, "Initial content")
  expect_identical(shown$value, "Initial")
  expect_identical(shown$border, "rgb(24, 119, 242)")

  app$set_inputs(drawer_text = "browser value")
  app$wait_for_js(
    paste(
      "document.querySelector('#chat #drawer_echo')?.innerText ===",
      jsonlite::toJSON("Echo: browser value", auto_unbox = TRUE),
      ";",
      sep = "\n"
    ),
    timeout = 30 * 1000
  )

  app$click(input = "update_drawer")
  app$wait_for_js(
    paste(
      "document.querySelector(",
      "'#chat .shiny-chat-drawer:not([hidden]) h2'",
      ")?.innerText === 'Updated drawer';",
      sep = "\n"
    ),
    timeout = 30 * 1000
  )
  app$wait_for_idle(timeout = 30 * 1000)

  updated <- drawer_state()
  expect_identical(updated$title, "Updated drawer")
  expect_identical(updated$label, "Updated content")
  expect_identical(updated$value, "Updated")
  expect_identical(updated$border, "rgb(24, 119, 242)")

  app$click(input = "hide_drawer")
  app$wait_for_js(
    "document.querySelector('#chat .shiny-chat-drawer')?.hidden === true;",
    timeout = 30 * 1000
  )
  app$wait_for_idle(timeout = 30 * 1000)

  app$click(input = "show_preserved")
  app$wait_for_js(
    paste(
      "document.querySelector(",
      "'#chat .shiny-chat-drawer:not([hidden]) #drawer_text'",
      ")?.value === 'Updated';",
      sep = "\n"
    ),
    timeout = 30 * 1000
  )
  app$wait_for_idle(timeout = 30 * 1000)
  preserved <- drawer_state()
  expect_false(isTRUE(preserved$hidden))
  expect_identical(preserved$title, "Updated drawer")
  expect_identical(preserved$value, "Updated")

  app$click(input = "toggle_drawer")
  app$wait_for_js(
    "document.querySelector('#chat .shiny-chat-drawer')?.hidden === true;",
    timeout = 30 * 1000
  )
  app$click(input = "toggle_drawer")
  app$wait_for_js(
    paste(
      "document.querySelector(",
      "'#chat .shiny-chat-drawer:not([hidden]) #drawer_text'",
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
      "'#chat .shiny-chat-drawer:not([hidden]) #drawer_text'",
      ")?.value === 'Updated';",
      sep = "\n"
    ),
    timeout = 30 * 1000
  )
  app$wait_for_idle(timeout = 30 * 1000)
  after_navigation <- drawer_state()
  expect_false(isTRUE(after_navigation$hidden))
  expect_identical(after_navigation$title, "Updated drawer")
  expect_identical(after_navigation$value, "Updated")
  expect_identical(after_navigation$echo, "Echo: Updated")
})
