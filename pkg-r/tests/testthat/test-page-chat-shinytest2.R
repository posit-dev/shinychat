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
  expect_identical(initial$active, "__home__")
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
  expect_identical(home$active, "__home__")
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

nav_visibility_state <- function(app) {
  jsonlite::fromJSON(app$get_js(
    paste(
      "(() => {",
      "const root = document.querySelector('shiny-chat-page');",
      "const controls = {};",
      "root?.querySelectorAll('.shiny-chat-page-nav button[data-page-target]')",
      "  .forEach((button) => {",
      "    controls[button.dataset.pageTarget] = button.hidden;",
      "  });",
      "return JSON.stringify({",
      "  active: root?.dataset.activePage,",
      "  input: document.querySelector('#page_value')?.textContent.trim(),",
      "  controls: controls,",
      "});",
      "})()",
      sep = "\n"
    )
  ))
}

nav_visibility_wait_active <- function(app, value) {
  app$wait_for_js(
    sprintf(
      "document.querySelector('shiny-chat-page')?.dataset.activePage === '%s';",
      value
    ),
    timeout = 30 * 1000
  )
}

nav_visibility_wait_input <- function(app, value) {
  app$wait_for_js(
    sprintf(
      "document.querySelector('#page_value')?.textContent.trim() === '%s';",
      value
    ),
    timeout = 30 * 1000
  )
}

test_that("page_chat supports bslib nav_select in a real Shiny app", {
  skip_if_shinytest2_unavailable()

  app <- shinytest2::AppDriver$new(
    test_path("apps/page-chat-nav-visibility"),
    name = "page-chat-nav-select",
    width = 1440,
    height = 900,
    timeout = 30 * 1000
  )
  withr::defer(app$stop())

  # The input binding round-trips the initial home value to the server.
  app$wait_for_js(
    "document.querySelector('#page_value')?.textContent.trim() === '__home__';",
    timeout = 30 * 1000
  )
  initial <- nav_visibility_state(app)
  expect_identical(initial$active, "__home__")
  # The nav_panel_hidden() control is pre-rendered but hidden.
  expect_true(isTRUE(initial$controls$secret))
  expect_false(isTRUE(initial$controls$about))
  expect_false(isTRUE(initial$controls$nested))

  # nav_select drives the page and the server-visible input value.
  app$click(selector = "#select_about")
  nav_visibility_wait_active(app, "about")
  nav_visibility_wait_input(app, "about")

  # Menu children are selectable.
  app$click(selector = "#select_nested")
  nav_visibility_wait_active(app, "nested")
  nav_visibility_wait_input(app, "nested")

  # Hidden panels stay selectable; the control remains hidden.
  app$click(selector = "#select_secret")
  nav_visibility_wait_active(app, "secret")
  nav_visibility_wait_input(app, "secret")
  secret <- nav_visibility_state(app)
  expect_true(isTRUE(secret$controls$secret))

  # nav_select returns home via the reserved value.
  app$click(selector = "#select_home")
  nav_visibility_wait_active(app, "__home__")
  nav_visibility_wait_input(app, "__home__")
})

test_that("page_chat supports bslib nav_hide/nav_show in a real Shiny app", {
  skip_if_shinytest2_unavailable()

  app <- shinytest2::AppDriver$new(
    test_path("apps/page-chat-nav-visibility"),
    name = "page-chat-nav-visibility",
    width = 1440,
    height = 900,
    timeout = 30 * 1000
  )
  withr::defer(app$stop())

  app$wait_for_js(
    "document.querySelector('#page_value')?.textContent.trim() === '__home__';",
    timeout = 30 * 1000
  )

  # Hiding a non-active page hides only its nav control.
  app$click(selector = "#hide_about")
  app$wait_for_js(
    "document.querySelector(\"button[data-page-target='about']\")?.hidden === true;",
    timeout = 30 * 1000
  )
  hidden <- nav_visibility_state(app)
  expect_identical(hidden$active, "__home__")
  expect_false(isTRUE(hidden$controls$nested))

  # nav_show reveals the control without selecting the page.
  app$click(selector = "#show_about")
  app$wait_for_js(
    "document.querySelector(\"button[data-page-target='about']\")?.hidden === false;",
    timeout = 30 * 1000
  )
  expect_identical(nav_visibility_state(app)$active, "__home__")

  # Hiding the active page returns home and the input value follows.
  app$click(selector = "#select_about")
  nav_visibility_wait_active(app, "about")
  app$click(selector = "#hide_about")
  nav_visibility_wait_active(app, "__home__")
  nav_visibility_wait_input(app, "__home__")
  app$click(selector = "#show_about")
  app$wait_for_js(
    "document.querySelector(\"button[data-page-target='about']\")?.hidden === false;",
    timeout = 30 * 1000
  )

  # nav_show(select = TRUE) reveals the hidden panel's control and selects it.
  app$click(selector = "#show_secret_select")
  nav_visibility_wait_active(app, "secret")
  nav_visibility_wait_input(app, "secret")
  revealed <- nav_visibility_state(app)
  expect_false(isTRUE(revealed$controls$secret))

  # Error cases (hiding home, unknown target) leave the app fully functional.
  app$click(selector = "#select_home")
  nav_visibility_wait_active(app, "__home__")
  app$click(selector = "#hide_home")
  app$click(selector = "#hide_unknown")
  app$wait_for_idle(timeout = 30 * 1000)
  after_errors <- nav_visibility_state(app)
  expect_identical(after_errors$active, "__home__")
  expect_false(isTRUE(after_errors$controls$about))
  expect_false(isTRUE(after_errors$controls$nested))

  app$click(selector = "#select_nested")
  nav_visibility_wait_active(app, "nested")
  nav_visibility_wait_input(app, "nested")
})
