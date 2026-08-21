test_that("page_chat navigation and sidebars work in a real Shiny app", {
  skip_if_shinytest2_unavailable()

  app <- shinytest2::AppDriver$new(
    test_path("apps/page-chat-artifact"),
    name = "page-chat-navigation",
    width = 1440,
    height = 900,
    timeout = 30 * 1000
  )
  withr::defer(app$stop())

  page_state <- function() {
    jsonlite::fromJSON(app$get_js(
      paste(
        "(() => {",
        "const root = document.querySelector('shiny-chat-page');",
        "const aside = root?.querySelector('.shiny-chat-page-sidebar');",
        "const panels = Array.from(",
        "root?.querySelectorAll('.shiny-chat-page-panel') || []);",
        "const controls = root?.querySelector('.shiny-chat-page-controls');",
        "return JSON.stringify({",
        "  active: root?.dataset.activePage,",
        "  asideHidden: aside?.hidden,",
        "  sidebarKey: aside?.dataset.sidebarKey,",
        "  sidebarOpen: aside?.dataset.sidebarOpen,",
        "  sidebarWidth: aside?.dataset.sidebarWidth,",
        "  toggleExpanded: root?.querySelector(",
        "    '.shiny-chat-page-sidebar-toggle')?.getAttribute('aria-expanded'),",
        "  visiblePanels: panels.filter((panel) => !panel.hidden).length,",
        "  controls: controls?.parentElement?.className,",
        "  toolbarInput: root?.querySelector(",
        "    '.shiny-chat-page-toolbar input')?.id,",
        "  toolbarValue: root?.querySelector(",
        "    '.shiny-chat-page-toolbar input')?.value,",
        "  visibleToolbarContentCount: root?.querySelectorAll(",
        "    '.shiny-chat-page-toolbar-scoped > .shiny-chat-page-toolbar-content')?.length,",
        "  toolbarSourceHidden: root?.querySelector(",
        "    '.shiny-chat-page-toolbar-sources')?.hidden",
        "});",
        "})()",
        sep = "\n"
      )
    ))
  }

  app$wait_for_js(
    "document.querySelector('shiny-chat-page #chat [role=\"textbox\"]') !== null;",
    timeout = 30 * 1000
  )
  app$wait_for_idle(timeout = 30 * 1000)

  initial <- page_state()
  expect_identical(initial$active, "home")
  expect_false(initial$asideHidden)
  expect_identical(initial$sidebarKey, "home")
  expect_identical(initial$sidebarOpen, "open")
  expect_identical(initial$sidebarWidth, "280px")
  expect_identical(initial$toggleExpanded, "true")
  expect_equal(initial$visiblePanels, 1)
  expect_match(initial$controls, "mount-desktop", fixed = TRUE)
  expect_identical(initial$toolbarInput, "home_toolbar")
  expect_equal(initial$visibleToolbarContentCount, 1)
  expect_true(initial$toolbarSourceHidden)
  app$run_js(
    "document.querySelector('#home_toolbar').value = 'home toolbar state';"
  )

  app$click(selector = "button[data-page-target='settings']")
  app$wait_for_idle(timeout = 30 * 1000)

  settings <- page_state()
  expect_identical(settings$active, "settings")
  expect_true(settings$asideHidden)
  expect_identical(settings$sidebarKey, "page-2")
  expect_identical(settings$sidebarOpen, "closed")
  expect_identical(settings$sidebarWidth, "320px")
  expect_identical(settings$toggleExpanded, "false")
  expect_equal(settings$visiblePanels, 1)
  expect_identical(settings$toolbarInput, "settings_toolbar")
  expect_equal(settings$visibleToolbarContentCount, 1)
  app$run_js(
    "document.querySelector('#settings_toolbar').value = 'settings toolbar state';"
  )
  expect_true(
    app$get_js(paste(
      "document.querySelector(",
      "'button[data-page-target=\"settings\"]')?.getAttribute('aria-current')",
      sep = "\n"
    )) ==
      "page"
  )

  app$click(selector = ".shiny-chat-page-sidebar-toggle")
  app$wait_for_idle(timeout = 30 * 1000)
  opened <- page_state()
  expect_false(opened$asideHidden)
  expect_identical(opened$toggleExpanded, "true")

  app$click(selector = "button[data-page-target='about']")
  app$wait_for_idle(timeout = 30 * 1000)
  about <- page_state()
  expect_identical(about$active, "about")
  expect_true(about$asideHidden)
  expect_null(about$sidebarKey)
  expect_null(about$sidebarOpen)
  expect_equal(about$visiblePanels, 1)
  expect_null(about$toolbarInput)
  expect_equal(about$visibleToolbarContentCount, 0)

  app$click(selector = "button[data-page-home]")
  app$wait_for_idle(timeout = 30 * 1000)
  home <- page_state()
  expect_identical(home$active, "home")
  expect_false(home$asideHidden)
  expect_identical(home$sidebarKey, "home")
  expect_identical(home$sidebarOpen, "open")
  expect_identical(home$toolbarInput, "home_toolbar")
  expect_identical(home$toolbarValue, "home toolbar state")
  expect_equal(home$visibleToolbarContentCount, 1)

  app$click(selector = "button[data-page-target='empty']")
  app$wait_for_idle(timeout = 30 * 1000)
  empty <- page_state()
  expect_identical(empty$toolbarInput, NULL)
  expect_equal(empty$visibleToolbarContentCount, 0)
  expect_equal(
    app$get_js("document.querySelectorAll('#home_toolbar').length"),
    1
  )
  expect_equal(
    app$get_js("document.querySelectorAll('#settings_toolbar').length"),
    1
  )

  app$click(selector = "button[data-page-target='settings']")
  app$wait_for_idle(timeout = 30 * 1000)
  settings_return <- page_state()
  expect_identical(settings_return$toolbarInput, "settings_toolbar")
  expect_identical(settings_return$toolbarValue, "settings toolbar state")
  expect_equal(settings_return$visibleToolbarContentCount, 1)

  app$set_window_size(700, 900)
  app$wait_for_idle(timeout = 30 * 1000)
  narrow <- page_state()
  expect_match(narrow$controls, "mount-mobile", fixed = TRUE)

  app$click(selector = ".shiny-chat-page-sidebar-toggle")
  app$wait_for_idle(timeout = 30 * 1000)
  mobile <- jsonlite::fromJSON(app$get_js(
    paste(
      "(() => {",
      "const root = document.querySelector('shiny-chat-page');",
      "const aside = root?.querySelector('.shiny-chat-page-sidebar');",
      "return JSON.stringify({",
      "  menuOpen: root?.hasAttribute('data-mobile-menu-open'),",
      "  role: aside?.getAttribute('role'),",
      "  focused: document.activeElement === aside",
      "});",
      "})()",
      sep = "\n"
    )
  ))
  expect_true(isTRUE(mobile$menuOpen))
  expect_identical(mobile$role, "dialog")
  expect_true(isTRUE(mobile$focused))

  app$run_js(
    paste(
      "document.dispatchEvent(new KeyboardEvent('keydown', {",
      "  key: 'Escape', bubbles: true",
      "}));",
      sep = "\n"
    )
  )
  app$wait_for_idle(timeout = 30 * 1000)
  closed <- jsonlite::fromJSON(app$get_js(
    paste(
      "(() => {",
      "const root = document.querySelector('shiny-chat-page');",
      "const toggle = root?.querySelector('.shiny-chat-page-sidebar-toggle');",
      "return JSON.stringify({",
      "  menuOpen: root?.hasAttribute('data-mobile-menu-open'),",
      "  focused: document.activeElement === toggle",
      "});",
      "})()",
      sep = "\n"
    )
  ))
  expect_false(isTRUE(closed$menuOpen))
  expect_true(isTRUE(closed$focused))
})
