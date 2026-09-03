chat_app_request <- function() {
  list(REQUEST_METHOD = "GET", PATH_INFO = "/", QUERY_STRING = "")
}

chat_app_html <- function(app) {
  app$httpHandler(chat_app_request())$content
}

test_that("chat_app() rejects startup messages while history is enabled", {
  client <- mock_chat_client()
  expect_snapshot(
    error = TRUE,
    chat_app(client, messages = list("Hi!"))
  )
  expect_no_error(chat_app(client, messages = NULL))
  expect_no_error(suppressWarnings(
    chat_app(client, messages = list("Hi!"), history = FALSE)
  ))
})

test_that("chat_app() composes a page chat with client-derived titles", {
  client <- mock_chat_client()
  app <- chat_app(client)
  html <- chat_app_html(app)
  date <- format(Sys.Date(), "%Y-%m-%d")

  expect_match(
    html,
    '<shiny-chat-page id="chat_page" data-chat-id="chat"',
    fixed = TRUE
  )
  expect_match(
    html,
    '<span class="shiny-chat-page-identity-title">mock-model (Mock)</span>',
    fixed = TRUE
  )
  expect_match(
    html,
    paste0("<title>shinychat | mock-model | ", date, "</title>"),
    fixed = TRUE
  )
  expect_match(html, 'id="chat-sidebar"', fixed = TRUE)
  expect_match(html, '<shiny-chat-history for="chat">', fixed = TRUE)
})

test_that("chat_app() forwards page and browser-title options", {
  app <- chat_app(
    mock_chat_client(),
    title = "Custom title",
    window_title = "Custom window",
    id = "custom-chat",
    sidebar = FALSE,
    drawer = FALSE
  )
  html <- chat_app_html(app)

  expect_match(html, 'data-chat-id="custom-chat"', fixed = TRUE)
  expect_match(
    html,
    '<span class="shiny-chat-page-identity-title">Custom title</span>',
    fixed = TRUE
  )
  expect_match(html, "<title>Custom window</title>", fixed = TRUE)
  expect_false(grepl(
    '<shiny-chat-history for="custom-chat">',
    html,
    fixed = TRUE
  ))
  expect_false(grepl("<shiny-chat-drawer", html, fixed = TRUE))
})

test_that("chat_app() preserves an explicitly supplied bslib theme", {
  captured_theme <- NULL
  local_mocked_bindings(
    page_chat = function(...) {
      captured_theme <<- rlang::list2(...)$theme
      bslib::page_fillable()
    },
    .package = "shinychat"
  )
  theme <- bslib::bs_theme(primary = "#123456")

  chat_app_html(chat_app(mock_chat_client(), theme = theme))

  expect_identical(captured_theme, theme)
  expect_equal(
    bslib::bs_get_variables(
      captured_theme,
      c("primary", "shiny-chat-page-header-height")
    ),
    c("primary" = "#123456", "shiny-chat-page-header-height" = NA_character_)
  )
})

test_that("chat_app() forwards chat_server() options", {
  called <- NULL
  local_mocked_bindings(
    chat_server = function(id, client, greeting, history) {
      called <<- list(
        id = id,
        client = client,
        greeting = greeting,
        history = history
      )
    },
    .package = "shinychat"
  )
  client <- mock_chat_client()
  app <- chat_app(
    client,
    id = "custom-chat",
    greeting = "Welcome",
    history = FALSE
  )

  expect_false(grepl(
    '<shiny-chat-history for="custom-chat">',
    chat_app_html(app),
    fixed = TRUE
  ))
  app$serverFuncSource()(NULL, NULL, NULL)

  expect_identical(
    called,
    list(
      id = "custom-chat",
      client = client,
      greeting = "Welcome",
      history = FALSE
    )
  )
})

test_that("chat_app() preserves an explicit sidebar when history is disabled", {
  html <- chat_app_html(chat_app(
    mock_chat_client(),
    history = FALSE,
    sidebar = TRUE
  ))

  expect_match(html, '<shiny-chat-history for="chat">', fixed = TRUE)
})

test_that("chat_app() forwards app options and bookmark store", {
  app <- chat_app(
    mock_chat_client(),
    app_options = list(workerId = "chat-app"),
    bookmark_store = "server"
  )

  expect_identical(app$options, list(workerId = "chat-app"))
  expect_identical(app$appOptions$bookmarkStore, "server")
  expect_snapshot(
    error = TRUE,
    chat_app(mock_chat_client(), app_options = "not-a-list")
  )
})

test_that("chat_app() diagnoses legacy shinyApp() arguments in dots", {
  client <- mock_chat_client()

  expect_snapshot(
    error = TRUE,
    chat_app(client, options = list())
  )
  expect_snapshot(
    error = TRUE,
    chat_app(client, enableBookmarking = "server")
  )
  expect_snapshot(
    error = TRUE,
    chat_app(client, onStart = function() NULL)
  )
  expect_snapshot(
    error = TRUE,
    chat_app(client, uiPattern = "/chat")
  )
  expect_snapshot(
    error = TRUE,
    chat_app(client, ui = shiny::fluidPage())
  )
  expect_snapshot(
    error = TRUE,
    chat_app(client, server = function(...) NULL)
  )
})

test_that("chat_app() puts the interactive stop button in the page toolbar", {
  local_mocked_bindings(
    is_interactive = function() TRUE,
    .package = "rlang"
  )
  html <- chat_app_html(chat_app(mock_chat_client()))

  expect_match(
    html,
    '<div class="shiny-chat-page-toolbar-global">',
    fixed = TRUE
  )
  expect_match(html, 'id="chat-close-btn"', fixed = TRUE)
  expect_match(
    html,
    '<div class="bslib-toolbar bslib-gap-spacing" data-align="right">',
    fixed = TRUE
  )
  expect_match(html, "bslib-input-dark-mode", fixed = TRUE)
  expect_match(html, "bi-stop-circle-fill text-danger", fixed = TRUE)
  expect_match(html, "Stop chat app", fixed = TRUE)
  expect_false(grepl("position: fixed", html, fixed = TRUE))

  opt_out_html <- chat_app_html(
    chat_app(mock_chat_client(), toolbar_global = NULL)
  )
  expect_false(grepl("bslib-input-dark-mode", opt_out_html, fixed = TRUE))
  expect_match(opt_out_html, "bi-stop-circle-fill text-danger", fixed = TRUE)
})

test_that("chat_app() omits the stop button outside interactive use", {
  local_mocked_bindings(
    is_interactive = function() FALSE,
    .package = "rlang"
  )
  html <- chat_app_html(chat_app(mock_chat_client()))

  expect_false(grepl('id="chat-close-btn"', html, fixed = TRUE))
  expect_false(grepl("bi-stop-circle-fill", html, fixed = TRUE))
})
