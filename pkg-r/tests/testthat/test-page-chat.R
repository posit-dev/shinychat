artifact_child <- function(ui) {
  children <- Filter(
    function(child) identical(child$name, "shiny-chat-artifact"),
    ui$children
  )
  expect_length(children, 1)
  children[[1]]
}

page_chat_tags <- function(ui, selector) {
  htmltools::tagQuery(ui)$find(selector)$selectedTags()
}

page_chat_tag <- function(ui, selector) {
  tags <- page_chat_tags(ui, selector)
  expect_length(tags, 1)
  tags[[1]]
}

test_that("chat_sidebar() validates and normalizes configuration", {
  expect_null(chat_sidebar()$history)

  sidebar <- chat_sidebar(
    htmltools::tags$p("Extra controls"),
    history = TRUE,
    width = "20rem",
    open = TRUE,
    resizable = FALSE
  )

  expect_s3_class(sidebar, "chat_sidebar")
  expect_equal(sidebar$open, "open")
  expect_equal(sidebar$content, list(htmltools::tags$p("Extra controls")))
  expect_true(sidebar$history)
  expect_equal(sidebar$width, "20rem")
  expect_false(sidebar$resizable)

  expect_snapshot(error = TRUE, chat_sidebar(history = NA))
  expect_snapshot(error = TRUE, chat_sidebar(width = 0))
  expect_snapshot(error = TRUE, chat_sidebar(width = "bogus"))
  expect_snapshot(error = TRUE, chat_sidebar(open = "desktop"))
  expect_snapshot(error = TRUE, chat_sidebar(class = "not-an-attribute"))
})

test_that("chat_artifact_panel() validates configuration", {
  artifact <- chat_artifact_panel(
    htmltools::tags$p("Artifact content"),
    title = "Preview",
    width = 480,
    resizable = FALSE
  )

  expect_s3_class(artifact, "chat_artifact_panel")
  expect_equal(artifact$title, "Preview")
  expect_equal(artifact$width, "480px")
  expect_true(artifact$open)
  expect_false(artifact$resizable)
  expect_false(chat_artifact_panel(open = FALSE)$open)

  expect_snapshot(error = TRUE, chat_artifact_panel(title = list()))
  expect_snapshot(error = TRUE, chat_artifact_panel(width = -1))
  expect_snapshot(error = TRUE, chat_artifact_panel(width = "bogus"))
  expect_snapshot(error = TRUE, chat_artifact_panel(open = "yes"))
  expect_snapshot(error = TRUE, chat_artifact_panel(data_role = "artifact"))
})

test_that("page_chat_theme() composes caller overrides over a preset", {
  theme <- page_chat_theme(
    preset = "flatly",
    primary = "#123456",
    "shiny-chat-page-canvas-bg" = "#F0F0F0"
  )
  expect_s3_class(theme, "bs_theme")
  expect_equal(
    bslib::bs_get_variables(
      theme,
      c(
        "primary",
        "shiny-chat-page-canvas-bg"
      )
    ),
    c(
      "primary" = "#123456",
      "shiny-chat-page-canvas-bg" = "#F0F0F0"
    )
  )
  expect_no_error(bslib::bs_theme_dependencies(theme))
})

test_that("page_chat_theme() contains the page-specific baseline tokens", {
  page_theme <- page_chat_theme()
  standard_theme <- bslib::bs_theme()
  tokens <- c(
    "shiny-chat-page-header-height",
    "shiny-chat-page-header-padding-y",
    "shiny-chat-page-sidebar-padding",
    "shiny-chat-page-title-gap",
    "shiny-chat-page-title-font-size",
    "shiny-chat-page-title-font-weight",
    "shiny-chat-page-controls-gap",
    "shiny-chat-page-nav-link-font-size",
    "shiny-chat-page-panel-padding-block",
    "shiny-chat-page-fill-padding",
    "shiny-chat-page-artifact-box-shadow"
  )

  expect_false(anyNA(bslib::bs_get_variables(page_theme, tokens)))
  expect_true(all(is.na(bslib::bs_get_variables(standard_theme, tokens))))

  bootstrap <- bslib::bs_theme_dependencies(page_theme)[[2]]
  css <- paste(
    readLines(
      file.path(bootstrap$src$file, bootstrap$stylesheet),
      warn = FALSE
    ),
    collapse = "\n"
  )
  expect_match(
    css,
    "--shiny-chat-fill-padding: var(--shiny-chat-page-fill-padding)",
    fixed = TRUE
  )
  expect_match(
    css,
    "--shiny-chat-input-padding-bottom: var(--shiny-chat-page-input-padding-bottom)",
    fixed = TRUE
  )
  expect_match(
    css,
    "background:var(--shiny-chat-page-artifact-bg)",
    fixed = TRUE
  )
  expect_match(
    css,
    "box-shadow:var(--shiny-chat-page-artifact-box-shadow)",
    fixed = TRUE
  )
  expect_match(
    css,
    "background:var(--shiny-chat-page-artifact-header-bg)",
    fixed = TRUE
  )
})

test_that("chat_nav_panel() requires page-chat configuration", {
  panel <- chat_nav_panel(
    "Settings",
    htmltools::tags$p("Settings content"),
    value = "settings",
    icon = htmltools::tags$span("S"),
    sidebar = chat_sidebar()
  )

  expect_s3_class(panel, "chat_nav_panel")
  expect_equal(panel$title, "Settings")
  expect_equal(panel$value, "settings")
  expect_s3_class(panel$sidebar, "chat_sidebar")
  expect_null(panel$toolbar)
  expect_equal(panel$content_width, "min(680px, 100%)")
  expect_false(chat_nav_panel("Default")$sidebar)
  expect_equal(
    chat_nav_panel("Wide", content_width = 720)$content_width,
    "720px"
  )
  expect_equal(
    chat_nav_panel("Full", content_width = "100vw")$content_width,
    "100vw"
  )
  expect_error(
    chat_nav_panel("Inherited", toolbar = TRUE),
    "must be NULL or UI content"
  )
  expect_error(
    chat_nav_panel("Legacy empty", toolbar = FALSE),
    "must be NULL or UI content"
  )
  custom_toolbar <- htmltools::tags$span("Custom toolbar")
  expect_identical(
    chat_nav_panel("Custom", toolbar = custom_toolbar)$toolbar,
    custom_toolbar
  )

  home <- page_chat("Assistant", sidebar = chat_sidebar())
  panel <- page_chat(
    "Assistant",
    sidebar = FALSE,
    pages_navbar = list(chat_nav_panel("About", sidebar = chat_sidebar()))
  )
  expect_length(page_chat_tags(home, "shiny-chat-history"), 1)
  expect_length(page_chat_tags(panel, "shiny-chat-history"), 0)

  expect_snapshot(error = TRUE, chat_nav_panel(""))
  expect_snapshot(error = TRUE, chat_nav_panel("Settings", value = ""))
  expect_snapshot(error = TRUE, chat_nav_panel("Settings", sidebar = list()))
  expect_error(
    chat_nav_panel("Settings", content_width = ""),
    "`content_width` must be a positive number"
  )
  expect_s3_class(
    chat_nav_panel("Settings", sidebar = bslib::sidebar()),
    "chat_nav_panel"
  )
  expect_s3_class(
    chat_nav_panel("Settings", toolbar = new.env()),
    "chat_nav_panel"
  )
})

test_that("page_chat() normalizes bslib sidebars", {
  page <- page_chat(
    "Assistant",
    sidebar = bslib::sidebar(
      htmltools::tags$p("Home controls"),
      width = 320,
      open = "open",
      resizable = FALSE
    ),
    pages_navbar = list(
      chat_nav_panel(
        "Settings",
        sidebar = bslib::sidebar(
          htmltools::tags$p("Settings controls"),
          width = "18rem",
          open = "closed"
        )
      )
    )
  )
  panels <- page_chat_tags(page, ".shiny-chat-page-sidebar-panel")

  expect_equal(panels[[1]]$attribs[["data-sidebar-width"]], "320px")
  expect_equal(panels[[1]]$attribs[["data-sidebar-open"]], "open")
  expect_equal(panels[[1]]$attribs[["data-sidebar-resizable"]], "false")
  expect_match(
    htmltools::renderTags(panels[[1]])$html,
    "Home controls",
    fixed = TRUE
  )
  expect_equal(panels[[2]]$attribs[["data-sidebar-width"]], "18rem")
  expect_equal(panels[[2]]$attribs[["data-sidebar-open"]], "closed")
  expect_error(
    page_chat("Assistant", sidebar = bslib::sidebar(position = "right")),
    "left-positioned"
  )
})

test_that("chat_nav_panel() renders a content-width wrapper", {
  page <- page_chat(
    "Assistant",
    pages_navbar = list(
      chat_nav_panel("Default", htmltools::tags$p("Default")),
      chat_nav_panel(
        "Custom",
        htmltools::tags$p("Custom"),
        content_width = "42rem"
      ),
      chat_nav_panel("Full", htmltools::tags$p("Full"), content_width = "100%"),
      chat_nav_panel(
        "Viewport",
        htmltools::tags$p("Viewport"),
        content_width = "100vw"
      ),
      chat_nav_panel(
        "Dynamic",
        htmltools::tags$p("Dynamic"),
        content_width = "100dvw"
      )
    )
  )

  content <- page_chat_tags(page, ".shiny-chat-page-panel-content")
  expect_length(content, 5)
  expect_match(
    content[[1]]$attribs$style,
    "--shiny-chat-page-content-width:min(680px, 100%)",
    fixed = TRUE
  )
  expect_match(
    content[[2]]$attribs$style,
    "--shiny-chat-page-content-width:42rem",
    fixed = TRUE
  )
  expect_equal(
    unname(vapply(
      content[3:5],
      function(x) x$attribs[["data-content-full-bleed"]],
      character(1)
    )),
    rep("true", 3)
  )
})

test_that("chat_ui_history() resolves IDs and accepts named HTML attributes", {
  session <- shiny::MockShinySession$new()
  shiny::withReactiveDomain(session, {
    history <- chat_ui_history("chat", class = "history", `data-test` = "one")

    expect_equal(history$name, "shiny-chat-history")
    expect_equal(history$attribs[["for"]], session$ns("chat"))
    expect_equal(history$attribs$class, "history")
    expect_equal(history$attribs[["data-test"]], "one")
  })

  expect_snapshot(
    error = TRUE,
    chat_ui_history("chat", htmltools::tags$span("Nope"))
  )
  expect_snapshot(
    error = TRUE,
    chat_ui_history("chat", `for` = "another-chat")
  )
})

test_that("page_chat() has the agreed public signature", {
  expect_identical(
    names(formals(page_chat)),
    c(
      "title",
      "icon",
      "...",
      "id",
      "pages_navbar",
      "toolbar",
      "toolbar_global",
      "navbar_options",
      "sidebar",
      "messages",
      "greeting",
      "placeholder",
      "width",
      "icon_assistant",
      "enable_cancel",
      "allow_attachments",
      "footer",
      "artifact_panel",
      "window_title",
      "lang",
      "theme"
    )
  )
})

test_that("page_chat() builds the default fillable page contract", {
  page <- page_chat(
    "Assistant",
    htmltools::tags$span("A"),
    submit_key = "enter+modifier",
    `data-app-role` = "primary"
  )

  root <- page_chat_tag(page, "shiny-chat-page")
  expect_equal(root$attribs$id, "chat_page")
  expect_equal(root$attribs[["data-chat-id"]], "chat")
  expect_equal(root$attribs[["data-active-page"]], "__home__")
  dark_mode <- page_chat_tag(page, "bslib-input-dark-mode")
  expect_equal(dark_mode$attribs$attribute, "data-bs-theme")
  global_toolbar <- page_chat_tag(page, ".shiny-chat-page-toolbar-global")
  expect_length(page_chat_tags(global_toolbar, ".bslib-toolbar"), 1)
  expect_length(page_chat_tags(global_toolbar, "bslib-input-dark-mode"), 1)

  opt_out <- page_chat("Assistant", toolbar_global = NULL)
  expect_length(page_chat_tags(opt_out, "bslib-input-dark-mode"), 0)

  toggle <- page_chat_tag(page, ".shiny-chat-page-sidebar-toggle")
  expect_equal(toggle$attribs$type, "button")
  expect_equal(toggle$attribs[["aria-controls"]], "chat-sidebar")
  expect_equal(toggle$attribs[["aria-expanded"]], "false")
  expect_match(
    htmltools::renderTags(toggle)$html,
    'class="shiny-chat-page-sidebar-icon bi bi-list"',
    fixed = TRUE
  )

  close_button <- page_chat_tag(page, ".shiny-chat-page-sidebar-close")
  expect_equal(close_button$name, "button")
  expect_equal(close_button$attribs$type, "button")
  expect_equal(close_button$attribs$id, "chat-sidebar-close")
  expect_match(
    as.character(close_button),
    "bslib-toolbar-input-button",
    fixed = TRUE
  )
  close_toolbar <- page_chat_tag(
    page,
    ".shiny-chat-page-sidebar > .bslib-toolbar"
  )
  expect_length(
    page_chat_tags(close_toolbar, ".shiny-chat-page-sidebar-close"),
    1
  )
  expect_match(as.character(page), "Close app menu", fixed = TRUE)
  expect_match(as.character(close_button), "bi bi-x", fixed = TRUE)

  identity <- page_chat_tag(page, ".shiny-chat-page-identity")
  expect_equal(identity$name, "div")
  expect_null(identity$attribs[["data-page-home"]])
  expect_length(page_chat_tags(identity, ".shiny-chat-page-identity-icon"), 1)
  expect_length(page_chat_tags(identity, ".shiny-chat-page-identity-title"), 1)

  expect_length(page_chat_tags(page, ".shiny-chat-page-controls"), 1)
  expect_length(
    page_chat_tags(page, ".shiny-chat-page-controls-mount-desktop"),
    1
  )
  mobile_controls <- page_chat_tag(
    page,
    ".shiny-chat-page-controls-mount-mobile"
  )
  expect_length(mobile_controls$children, 0)

  nav <- page_chat_tag(page, ".shiny-chat-page-nav")
  expect_equal(nav$name, "nav")
  expect_equal(nav$attribs[["aria-label"]], "Pages")
  expect_null(nav$attribs$role)
  expect_length(page_chat_tags(nav, ".shiny-chat-page-nav-link"), 0)
  expect_length(page_chat_tags(page, ".shiny-chat-page-toolbar"), 1)
  header <- page_chat_tag(page, ".shiny-chat-page-header")
  expect_equal(
    header$attribs[["data-shiny-chat-page-nav-style"]],
    "underline"
  )
  expect_equal(header$attribs[["data-bs-theme"]], "auto")

  aside <- page_chat_tag(page, ".shiny-chat-page-sidebar")
  expect_equal(aside$name, "aside")
  expect_equal(aside$attribs$id, "chat-sidebar")
  expect_equal(aside$attribs[["aria-label"]], "App menu")
  expect_equal(aside$attribs[["data-sidebar-key"]], "default")
  expect_equal(aside$attribs[["data-sidebar-open"]], "auto")
  expect_equal(aside$attribs[["data-sidebar-width"]], "280px")
  expect_equal(aside$attribs[["data-sidebar-resizable"]], "true")

  sidebar_panel <- page_chat_tag(page, ".shiny-chat-page-sidebar-panel")
  expect_equal(sidebar_panel$attribs[["data-sidebar-for"]], "default")
  expect_null(sidebar_panel$attribs$hidden)
  history <- page_chat_tag(sidebar_panel, "shiny-chat-history")
  expect_equal(history$attribs[["for"]], root$attribs[["data-chat-id"]])

  main <- page_chat_tag(page, ".shiny-chat-page-main")
  expect_equal(main$name, "main")
  home <- page_chat_tag(main, ".shiny-chat-page-home")
  expect_equal(home$attribs[["data-page-value"]], "__home__")
  expect_equal(home$attribs[["data-sidebar-key"]], "default")

  chat <- page_chat_tag(home, "shiny-chat-container")
  expect_equal(chat$attribs$id, root$attribs[["data-chat-id"]])
  expect_null(chat$attribs[["show-history"]])
  expect_true(is.na(chat$attribs$fill))
  expect_match(chat$attribs$style, "height:100%", fixed = TRUE)
  expect_equal(chat$attribs[["submit-key"]], "enter+modifier")
  expect_equal(chat$attribs[["data-app-role"]], "primary")

  rendered <- render_tags(page)
  document <- htmltools::renderTags(page)
  expect_match(
    rendered$html,
    'data-require-bs-caller="page_chat"',
    fixed = TRUE
  )
  expect_match(rendered$deps, '"name":"shinychat"', fixed = TRUE)
  expect_match(document$head, "<title>Assistant</title>", fixed = TRUE)
  expect_identical(attr(page, "lang"), NULL)
  expect_s3_class(attr(page, "bs_theme"), "bs_theme")

  rendered_html <- gsub(
    "btn-label-[0-9]+",
    "btn-label-{id}",
    rendered$html
  )
  expect_snapshot(cat(rendered_html, "\n", sep = ""))
})

test_that("page_chat() applies supported navbar_options to its title bar", {
  page <- page_chat(
    "Assistant",
    navbar_options = bslib::navbar_options(
      bg = "#123456",
      theme = "dark",
      underline = FALSE,
      class = "custom-header",
      `data-test` = "navbar"
    )
  )
  header <- page_chat_tag(page, ".shiny-chat-page-header")

  expect_match(as.character(header), 'class="[^"]*custom-header')
  expect_equal(header$attribs[["data-test"]], "navbar")
  expect_equal(header$attribs[["data-bs-theme"]], "dark")
  expect_equal(header$attribs[["data-shiny-chat-page-nav-style"]], "pill")
  expect_match(header$attribs$style, "background-color:#123456;")

  expect_error(
    page_chat(
      "Assistant",
      navbar_options = bslib::navbar_options(position = "fixed-top")
    ),
    "cannot set.*position"
  )
  expect_error(
    page_chat(
      "Assistant",
      navbar_options = bslib::navbar_options(collapsible = FALSE)
    ),
    "cannot set.*collapsible"
  )
  expect_error(
    page_chat("Assistant", navbar_options = list()),
    "must be created by"
  )
})

test_that("page_chat() normalizes navigation and sidebar metadata once", {
  page <- page_chat(
    htmltools::tags$span("Reactive title"),
    icon = htmltools::tags$span("R"),
    pages_navbar = list(
      chat_nav_panel(
        "About",
        htmltools::tags$p("About content"),
        icon = htmltools::tags$span("?")
      ),
      chat_nav_panel(
        "Conversations",
        htmltools::tags$p("Conversation content"),
        value = "conversations",
        sidebar = TRUE
      ),
      chat_nav_panel(
        "Settings",
        htmltools::tags$p("Settings content"),
        value = "settings",
        sidebar = chat_sidebar(
          htmltools::tags$p("Settings menu"),
          history = TRUE,
          width = 360,
          open = "open",
          resizable = FALSE
        ),
        toolbar = shiny::actionButton("settings_save", "Save settings")
      )
    ),
    toolbar = htmltools::tags$button("Help"),
    toolbar_global = htmltools::tags$button("Global help"),
    sidebar = chat_sidebar(
      htmltools::tags$p("Default menu"),
      history = TRUE,
      width = "18rem",
      open = "always"
    ),
    window_title = "Assistant window",
    lang = "en"
  )

  identity <- page_chat_tag(page, ".shiny-chat-page-identity")
  expect_equal(identity$name, "button")
  expect_equal(identity$attribs[["data-page-home"]], "")
  expect_equal(identity$attribs[["aria-label"]], "Return to chat")
  expect_match(
    as.character(identity),
    "<span>Reactive title</span>",
    fixed = TRUE
  )

  controls <- page_chat_tag(page, ".shiny-chat-page-controls")
  nav <- page_chat_tag(controls, ".shiny-chat-page-nav")
  expect_null(nav$attribs$role)
  nav_links <- page_chat_tags(controls, ".shiny-chat-page-nav-link")
  expect_equal(
    unname(vapply(
      nav_links,
      function(x) x$attribs[["data-page-target"]],
      character(1)
    )),
    c("About", "conversations", "settings")
  )
  expect_equal(
    unname(vapply(nav_links, function(x) x$attribs$id, character(1))),
    paste0("chat-nav-", 1:3)
  )
  expect_equal(
    unname(vapply(
      nav_links,
      function(x) x$attribs[["aria-controls"]],
      character(1)
    )),
    paste0("chat-panel-", 1:3)
  )
  expect_true(all(vapply(
    nav_links,
    function(x) {
      is.null(x$attribs$role) &&
        is.null(x$attribs[["aria-selected"]]) &&
        is.null(x$attribs$tabindex)
    },
    logical(1)
  )))
  toolbar <- page_chat_tag(controls, ".shiny-chat-page-toolbar")
  expect_length(toolbar$children, 2)
  expect_equal(
    vapply(toolbar$children, function(x) x$attribs$class, character(1)),
    c(
      "shiny-chat-page-toolbar-scoped",
      "shiny-chat-page-toolbar-global"
    )
  )
  expect_true(grepl(
    "Global help",
    as.character(toolbar$children[[2]]),
    fixed = TRUE
  ))
  toolbar_sources <- page_chat_tags(page, ".shiny-chat-page-toolbar-source")
  expect_length(toolbar_sources, 2)
  expect_equal(
    unname(vapply(
      toolbar_sources,
      function(x) x$attribs[["data-page-toolbar-source"]],
      character(1)
    )),
    c("home", "page-3")
  )
  expect_length(page_chat_tags(page, ".shiny-chat-page-toolbar-content"), 2)
  expect_true(grepl("Help", as.character(toolbar_sources[[1]]), fixed = TRUE))
  expect_true(grepl(
    "Save settings",
    as.character(toolbar_sources[[2]]),
    fixed = TRUE
  ))

  expect_false(any(vapply(
    toolbar_sources,
    function(x) grepl("Global help", as.character(x), fixed = TRUE),
    logical(1)
  )))

  aside <- page_chat_tag(page, ".shiny-chat-page-sidebar")
  expect_equal(aside$attribs[["data-sidebar-key"]], "home")
  expect_equal(aside$attribs[["data-sidebar-open"]], "always")
  expect_equal(aside$attribs[["data-sidebar-width"]], "18rem")
  expect_equal(aside$attribs[["data-sidebar-resizable"]], "true")

  sections <- page_chat_tags(page, ".shiny-chat-page-panel")
  expect_equal(
    unname(vapply(
      sections,
      function(x) x$attribs[["data-page-value"]],
      character(1)
    )),
    c("__home__", "About", "conversations", "settings")
  )
  expect_equal(
    unname(vapply(
      sections,
      function(x) {
        x$attribs[["data-sidebar-key"]] %||% NA_character_
      },
      character(1)
    )),
    c("home", NA, "default", "page-3")
  )
  expect_equal(
    unname(vapply(
      sections,
      function(x) x$attribs[["data-page-toolbar-source"]] %||% NA_character_,
      character(1)
    )),
    c("home", NA, NA, "page-3")
  )
  expect_null(sections[[1]]$attribs$hidden)
  expect_true(all(vapply(
    sections[-1],
    function(x) is.na(x$attribs$hidden),
    logical(1)
  )))
  expect_equal(
    unname(vapply(
      sections[-1],
      function(x) x$attribs[["data-page-title"]],
      character(1)
    )),
    c("About", "Conversations", "Settings")
  )
  expect_equal(
    unname(vapply(
      sections[-1],
      function(x) x$attribs$id,
      character(1)
    )),
    paste0("chat-panel-", 1:3)
  )
  expect_equal(
    unname(vapply(
      sections[-1],
      function(x) x$attribs[["aria-labelledby"]],
      character(1)
    )),
    paste0("chat-nav-", 1:3)
  )
  expect_true(all(vapply(
    sections[-1],
    function(x) is.null(x$attribs$role),
    logical(1)
  )))

  sidebar_panels <- page_chat_tags(page, ".shiny-chat-page-sidebar-panel")
  expect_length(sidebar_panels, 3)
  expect_equal(
    unname(vapply(
      sidebar_panels,
      function(x) x$attribs[["data-sidebar-for"]],
      character(1)
    )),
    c("default", "home", "page-3")
  )
  expect_equal(
    unname(vapply(
      sidebar_panels,
      function(x) x$attribs[["data-sidebar-width"]],
      character(1)
    )),
    c("280px", "18rem", "360px")
  )
  expect_equal(
    unname(vapply(
      sidebar_panels,
      function(x) x$attribs[["data-sidebar-resizable"]],
      character(1)
    )),
    c("true", "true", "false")
  )
  expect_length(page_chat_tags(page, "shiny-chat-history"), 3)
  expect_equal(
    unname(vapply(
      sidebar_panels,
      function(x) identical(x$attribs$hidden, NA),
      logical(1)
    )),
    c(TRUE, FALSE, TRUE)
  )

  document <- htmltools::renderTags(page)
  expect_match(document$head, "<title>Assistant window</title>", fixed = TRUE)
  expect_identical(attr(page, "lang"), "en")
})

test_that("page_chat() supports standard bslib navigation items", {
  page <- page_chat(
    "Assistant",
    pages_navbar = list(
      bslib::nav_panel(
        "About",
        htmltools::tags$p("About content"),
        value = "about"
      ),
      bslib::nav_menu(
        "More",
        bslib::nav_panel(
          "Help",
          htmltools::tags$p("Help content"),
          value = "help"
        ),
        "---",
        bslib::nav_menu(
          "Nested",
          bslib::nav_panel(
            "Details",
            htmltools::tags$p("Details content"),
            value = "details"
          )
        )
      ),
      bslib::nav_item(
        htmltools::tags$a("Documentation", href = "https://example.com")
      ),
      bslib::nav_spacer(),
      chat_nav_panel("Settings", htmltools::tags$p("Settings content")),
      bslib::nav_panel_hidden(
        "advanced",
        htmltools::tags$p("Advanced content")
      )
    )
  )

  sections <- page_chat_tags(page, ".shiny-chat-page-panel")
  expect_equal(
    unname(vapply(
      sections,
      function(section) section$attribs[["data-page-value"]],
      character(1)
    )),
    c("__home__", "about", "help", "details", "Settings", "advanced")
  )
  expect_equal(
    unname(vapply(
      sections[-1],
      function(section) section$attribs[["aria-labelledby"]],
      character(1)
    )),
    paste0("chat-nav-", 1:5)
  )
  controls <- page_chat_tag(page, ".shiny-chat-page-nav")
  nav_links <- page_chat_tags(controls, ".shiny-chat-page-nav-link")
  expect_length(nav_links, 5)
  expect_length(page_chat_tags(controls, ".shiny-chat-page-nav-menu"), 2)
  expect_length(page_chat_tags(controls, ".shiny-chat-page-nav-divider"), 1)
  expect_length(page_chat_tags(controls, ".shiny-chat-page-nav-control"), 1)
  expect_length(page_chat_tags(controls, ".bslib-nav-spacer"), 1)
  expect_match(as.character(controls), "Documentation", fixed = TRUE)
  expect_match(
    as.character(page),
    "--shiny-chat-page-content-width:min(680px, 100%)",
    fixed = TRUE
  )
})

test_that("page_chat() pre-renders hidden nav controls in configured position", {
  page <- page_chat(
    "Assistant",
    pages_navbar = list(
      chat_nav_panel("About", htmltools::tags$p("About content")),
      bslib::nav_panel_hidden(
        "advanced",
        htmltools::tags$p("Advanced content")
      ),
      chat_nav_panel("Settings", htmltools::tags$p("Settings content"))
    )
  )

  sections <- page_chat_tags(page, ".shiny-chat-page-panel")
  expect_equal(
    unname(vapply(
      sections,
      function(section) section$attribs[["data-page-value"]],
      character(1)
    )),
    c("__home__", "About", "advanced", "Settings")
  )

  nav <- page_chat_tag(page, ".shiny-chat-page-nav")
  nav_links <- page_chat_tags(nav, ".shiny-chat-page-nav-link")
  expect_length(nav_links, 3)

  # The hidden control renders in its configured position (second).
  expect_equal(nav_links[[1]]$attribs[["data-page-target"]], "About")
  expect_equal(nav_links[[2]]$attribs[["data-page-target"]], "advanced")
  expect_equal(nav_links[[3]]$attribs[["data-page-target"]], "Settings")

  # The hidden control has the `hidden` attribute; visible controls do not.
  expect_null(nav_links[[1]]$attribs$hidden)
  expect_true(is.na(nav_links[[2]]$attribs$hidden))
  expect_null(nav_links[[3]]$attribs$hidden)

  # The hidden control's visible label falls back to the panel value.
  title_spans <- page_chat_tags(
    nav,
    ".shiny-chat-page-nav-title"
  )
  expect_match(as.character(title_spans[[2]]), "advanced", fixed = TRUE)

  # The hidden panel's section has aria-labelledby referencing its control.
  hidden_section <- sections[[3]]
  expect_equal(
    hidden_section$attribs[["aria-labelledby"]],
    nav_links[[2]]$attribs$id
  )
  expect_equal(hidden_section$attribs[["data-page-title"]], "advanced")
})

test_that("page_chat() pre-renders hidden nav controls inside nav_menu()", {
  page <- page_chat(
    "Assistant",
    pages_navbar = list(
      chat_nav_panel("About", htmltools::tags$p("About content")),
      bslib::nav_menu(
        "More",
        bslib::nav_panel(
          "Help",
          htmltools::tags$p("Help content"),
          value = "help"
        ),
        bslib::nav_panel_hidden(
          "secret",
          htmltools::tags$p("Secret content")
        )
      )
    )
  )

  sections <- page_chat_tags(page, ".shiny-chat-page-panel")
  expect_equal(
    unname(vapply(
      sections,
      function(section) section$attribs[["data-page-value"]],
      character(1)
    )),
    c("__home__", "About", "help", "secret")
  )

  nav <- page_chat_tag(page, ".shiny-chat-page-nav")
  nav_links <- page_chat_tags(nav, ".shiny-chat-page-nav-link")
  expect_length(nav_links, 3)

  # The hidden control is inside the menu, in its configured position.
  expect_equal(nav_links[[1]]$attribs[["data-page-target"]], "About")
  expect_equal(nav_links[[2]]$attribs[["data-page-target"]], "help")
  expect_equal(nav_links[[3]]$attribs[["data-page-target"]], "secret")
  expect_true(is.na(nav_links[[3]]$attribs$hidden))
  expect_null(nav_links[[2]]$attribs$hidden)

  # The hidden panel's section has aria-labelledby referencing its control.
  secret_section <- sections[[4]]
  expect_equal(
    secret_section$attribs[["aria-labelledby"]],
    nav_links[[3]]$attribs$id
  )
})

test_that("page_chat() preserves icon on hidden nav controls", {
  icon_html <- htmltools::tags$span("A")
  page <- page_chat(
    "Assistant",
    pages_navbar = list(
      bslib::nav_panel_hidden(
        "advanced",
        htmltools::tags$p("Advanced content"),
        icon = icon_html
      )
    )
  )

  nav <- page_chat_tag(page, ".shiny-chat-page-nav")
  nav_link <- page_chat_tag(nav, ".shiny-chat-page-nav-link")
  expect_true(is.na(nav_link$attribs$hidden))
  icon_spans <- page_chat_tags(nav_link, ".shiny-chat-page-nav-icon")
  expect_length(icon_spans, 1)
  expect_match(as.character(icon_spans[[1]]), "<span>A</span>", fixed = TRUE)
})

test_that("page_chat() keeps global and custom panel toolbars separate", {
  page <- page_chat(
    "Assistant",
    toolbar = htmltools::tags$button("Home"),
    toolbar_global = htmltools::tags$button("Global"),
    pages_navbar = list(
      chat_nav_panel("Default"),
      chat_nav_panel("No toolbar"),
      chat_nav_panel("Custom", toolbar = htmltools::tags$button("Custom"))
    )
  )

  toolbar <- page_chat_tag(page, ".shiny-chat-page-toolbar")
  expect_equal(
    vapply(toolbar$children, function(x) x$attribs$class, character(1)),
    c(
      "shiny-chat-page-toolbar-scoped",
      "shiny-chat-page-toolbar-global"
    )
  )
  expect_true(grepl(
    "Global",
    as.character(toolbar$children[[2]]),
    fixed = TRUE
  ))
  expect_length(page_chat_tags(page, ".shiny-chat-page-toolbar-source"), 2)
  sections <- page_chat_tags(page, ".shiny-chat-page-panel")
  expect_null(sections[[2]]$attribs[["data-page-toolbar-source"]])
  expect_null(sections[[3]]$attribs[["data-page-toolbar-source"]])
  expect_equal(sections[[4]]$attribs[["data-page-toolbar-source"]], "page-3")
})

test_that("page_chat() retains the app-menu shell without a home sidebar", {
  page <- page_chat(
    "Assistant",
    sidebar = FALSE,
    pages_navbar = list(chat_nav_panel("About", sidebar = TRUE)),
    window_title = NULL
  )

  aside <- page_chat_tag(page, ".shiny-chat-page-sidebar")
  expect_null(aside$attribs[["data-sidebar-key"]])
  expect_null(aside$attribs[["data-sidebar-open"]])
  expect_null(aside$attribs[["data-sidebar-width"]])
  expect_null(aside$attribs[["data-sidebar-resizable"]])
  expect_length(
    page_chat_tags(aside, ".shiny-chat-page-controls-mount-mobile"),
    1
  )
  sidebar_panel <- page_chat_tag(aside, ".shiny-chat-page-sidebar-panel")
  expect_equal(sidebar_panel$attribs[["data-sidebar-for"]], "default")
  expect_true(is.na(sidebar_panel$attribs$hidden))
  expect_length(page_chat_tags(sidebar_panel, "shiny-chat-history"), 1)

  sections <- page_chat_tags(page, ".shiny-chat-page-panel")
  expect_null(sections[[1]]$attribs[["data-sidebar-key"]])
  expect_equal(sections[[2]]$attribs[["data-sidebar-key"]], "default")
  expect_false(grepl(
    "<title>",
    htmltools::renderTags(page)$head,
    fixed = TRUE
  ))
})

test_that("page_chat() initializes sidebar accessibility state", {
  open_page <- page_chat(
    "Assistant",
    sidebar = chat_sidebar(open = "open")
  )
  always_page <- page_chat(
    "Assistant",
    sidebar = chat_sidebar(open = "always")
  )

  expect_equal(
    page_chat_tag(
      open_page,
      ".shiny-chat-page-sidebar-toggle"
    )$attribs[["aria-expanded"]],
    "true"
  )
  expect_equal(
    page_chat_tag(
      always_page,
      ".shiny-chat-page-sidebar-toggle"
    )$attribs[["aria-expanded"]],
    "true"
  )
})

test_that("page_chat() revalidates mutated sidebar configurations", {
  missing <- chat_sidebar()
  missing$width <- NULL
  expect_error(page_chat("Assistant", sidebar = missing), "must contain")

  named_content <- chat_sidebar()
  named_content$content <- list(control = htmltools::tags$p("Controls"))
  expect_error(
    page_chat("Assistant", sidebar = named_content),
    "unnamed UI content"
  )

  invalid_history <- chat_sidebar()
  invalid_history$history <- NA
  expect_error(page_chat("Assistant", sidebar = invalid_history), "`history`")

  invalid_width <- chat_sidebar()
  invalid_width$width <- 0
  expect_error(page_chat("Assistant", sidebar = invalid_width), "`width`")

  invalid_open <- chat_sidebar()
  invalid_open$open <- "sometimes"
  expect_error(page_chat("Assistant", sidebar = invalid_open), "`open`")

  invalid_resizable <- chat_sidebar()
  invalid_resizable$resizable <- NA
  panel <- chat_nav_panel("About", sidebar = invalid_resizable)
  expect_error(
    page_chat("Assistant", pages_navbar = list(panel)),
    "`resizable`"
  )
})

test_that("page_chat() resolves its shared chat ID once", {
  session <- shiny::MockShinySession$new()
  namespaced_id <- session$ns("chat")

  shiny::withReactiveDomain(session, {
    page <- page_chat(
      "Assistant",
      id = "chat",
      pages_navbar = list(chat_nav_panel("About"))
    )
    root <- page_chat_tag(page, "shiny-chat-page")
    chat <- page_chat_tag(page, "shiny-chat-container")
    history <- page_chat_tag(page, "shiny-chat-history")

    expect_equal(root$attribs[["data-chat-id"]], namespaced_id)
    expect_equal(chat$attribs$id, namespaced_id)
    expect_equal(history$attribs[["for"]], namespaced_id)
    expect_equal(
      page_chat_tag(page, ".shiny-chat-page-sidebar-toggle")$attribs[[
        "aria-controls"
      ]],
      paste0(namespaced_id, "-sidebar")
    )
    nav <- page_chat_tag(page, ".shiny-chat-page-nav-link")
    panel <- page_chat_tags(page, ".shiny-chat-page-panel")[[2]]
    expect_equal(nav$attribs$id, paste0(namespaced_id, "-nav-1"))
    expect_equal(
      nav$attribs[["aria-controls"]],
      paste0(
        namespaced_id,
        "-panel-1"
      )
    )
    expect_equal(panel$attribs$id, paste0(namespaced_id, "-panel-1"))
    expect_equal(
      panel$attribs[["aria-labelledby"]],
      paste0(
        namespaced_id,
        "-nav-1"
      )
    )
  })
})

test_that("page_chat() validates page-owned arguments and page metadata", {
  expect_snapshot(error = TRUE, page_chat("Assistant", NULL, "extra"))
  expect_snapshot(
    error = TRUE,
    page_chat("Assistant", height = "10rem", fill = FALSE)
  )
  expect_snapshot(error = TRUE, page_chat("Assistant", id = NULL))
  expect_error(page_chat("Assistant", id = " "), "`id`")
  expect_snapshot(error = TRUE, page_chat("", id = "chat"))
  expect_no_error(page_chat(c("Assistant", "Chat")))
  expect_snapshot(error = TRUE, page_chat(NULL))
  expect_no_error(page_chat("Assistant", icon = FALSE))
  expect_no_error(page_chat("Assistant", toolbar = new.env()))
  expect_snapshot(
    error = TRUE,
    page_chat("Assistant", pages_navbar = chat_nav_panel("About"))
  )
  expect_snapshot(
    error = TRUE,
    page_chat("Assistant", pages_navbar = list(htmltools::tags$p("About")))
  )
  expect_snapshot(
    error = TRUE,
    page_chat(
      "Assistant",
      pages_navbar = list(chat_nav_panel("Home", value = "__home__"))
    )
  )
  expect_snapshot(
    error = TRUE,
    page_chat(
      "Assistant",
      pages_navbar = list(chat_nav_panel("About"), chat_nav_panel("About"))
    )
  )
  expect_snapshot(
    error = TRUE,
    page_chat("Assistant", window_title = htmltools::HTML("Unsafe"))
  )
  expect_snapshot(error = TRUE, page_chat("Assistant", lang = ""))
})

test_that("page_chat() derives window title only from a scalar text title", {
  text_page <- page_chat("Assistant")
  ui_page <- page_chat(htmltools::tags$span("Assistant"))
  html_page <- page_chat(htmltools::HTML("<span>Assistant</span>"))

  expect_match(
    htmltools::renderTags(text_page)$head,
    "<title>Assistant</title>",
    fixed = TRUE
  )
  expect_false(grepl(
    "<title>",
    htmltools::renderTags(ui_page)$head,
    fixed = TRUE
  ))
  expect_false(grepl(
    "<title>",
    htmltools::renderTags(html_page)$head,
    fixed = TRUE
  ))
})

test_that("chat_ui() keeps default artifact support hidden", {
  ui <- chat_ui("chat")
  artifact <- artifact_child(ui)

  expect_equal(artifact$name, "shiny-chat-artifact")
  expect_equal(artifact$attribs$width, "400px")
  expect_null(artifact$attribs$open)
  expect_null(artifact$attribs$resizable)
  expect_null(ui$attribs[["show-history"]])
})

test_that("chat_ui() renders configured artifact content and dependencies", {
  artifact_dep <- htmltools::htmlDependency("artifact-dep", "1.0.0", "")
  ui <- chat_ui(
    "chat",
    artifact_panel = chat_artifact_panel(
      htmltools::tags$div("Artifact", artifact_dep),
      title = "",
      width = "30rem",
      resizable = FALSE
    )
  )
  artifact <- artifact_child(ui)

  expect_equal(artifact$attribs$title, "")
  expect_equal(artifact$attribs$width, "30rem")
  expect_true(is.na(artifact$attribs$open))
  expect_equal(artifact$attribs$resizable, "false")
  expect_match(as.character(artifact), "Artifact", fixed = TRUE)
  expect_match(
    render_tags(ui)$deps,
    "artifact-dep",
    fixed = TRUE
  )
  expect_snapshot(ui)
})

test_that("chat_ui() omits disabled artifact support and history presentation", {
  ui <- chat_ui("chat", artifact_panel = FALSE, show_history = FALSE)

  expect_equal(ui$attribs[["show-history"]], "false")
  expect_false(any(vapply(
    ui$children,
    function(child) identical(child$name, "shiny-chat-artifact"),
    logical(1)
  )))

  expect_snapshot(error = TRUE, chat_ui("chat", artifact_panel = list()))
  expect_snapshot(error = TRUE, chat_ui("chat", show_history = NA))
})
