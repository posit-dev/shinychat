artifact_session_with_spy <- function() {
  session <- shiny::MockShinySession$new()
  messages <- list()
  session$sendCustomMessage <- function(type, message) {
    messages[[length(messages) + 1]] <<- list(type = type, message = message)
  }
  list(
    session = session,
    messages = function() messages
  )
}

test_that("chat_artifact_panel_show() sends an action without updates", {
  spy <- artifact_session_with_spy()
  chat_artifact_panel_show("chat", session = spy$session)

  messages <- spy$messages()
  expect_length(messages, 1)
  expect_equal(messages[[1]]$type, "shinyChatMessage")
  expect_equal(messages[[1]]$message$id, spy$session$ns("chat"))
  expect_equal(messages[[1]]$message$action, list(type = "artifact_show"))
  expect_null(messages[[1]]$message$html_deps)
})

test_that("chat_artifact_panel_show() serializes content, dependencies, and title", {
  spy <- artifact_session_with_spy()
  dependency <- htmltools::htmlDependency(
    "artifact-dependency",
    "1.0.0",
    src = tempdir()
  )

  chat_artifact_panel_show(
    "chat",
    content = htmltools::tags$div("Artifact", dependency),
    title = "Preview",
    session = spy$session
  )

  message <- spy$messages()[[1]]$message
  expect_equal(message$action$type, "artifact_show")
  expect_match(message$action$content, "<div>Artifact</div>", fixed = TRUE)
  expect_equal(message$action$title, "Preview")
  expect_length(message$html_deps, 1)
  expect_equal(message$html_deps[[1]]$name, "artifact-dependency")
})

test_that("chat_artifact_panel_show() preserves omitted fields and clears empty UI", {
  spy <- artifact_session_with_spy()
  chat_artifact_panel_show(
    "chat",
    content = htmltools::tagList(),
    title = "",
    session = spy$session
  )

  message <- spy$messages()[[1]]$message
  expect_equal(
    message$action,
    list(
      type = "artifact_show",
      content = "",
      title = ""
    )
  )
  expect_equal(message$html_deps, list())
})

test_that("chat_artifact_panel_update() changes supplied fields without visibility", {
  spy <- artifact_session_with_spy()
  chat_artifact_panel_update(
    "chat",
    content = htmltools::tags$span("Updated"),
    session = spy$session
  )

  message <- spy$messages()[[1]]$message
  expect_equal(message$action$type, "artifact_update")
  expect_match(message$action$content, "<span>Updated</span>", fixed = TRUE)
  expect_equal(message$html_deps, list())
})

test_that("chat_artifact_panel_update() sends a title-only update", {
  spy <- artifact_session_with_spy()
  chat_artifact_panel_update("chat", title = "", session = spy$session)

  message <- spy$messages()[[1]]$message
  expect_equal(message$action, list(type = "artifact_update", title = ""))
  expect_null(message$html_deps)
})

test_that("chat_artifact_panel_hide() and chat_artifact_panel_toggle() send exact actions", {
  spy <- artifact_session_with_spy()
  chat_artifact_panel_hide("chat", session = spy$session)
  chat_artifact_panel_toggle("chat", session = spy$session)

  messages <- spy$messages()
  expect_equal(messages[[1]]$message$action, list(type = "artifact_hide"))
  expect_equal(messages[[2]]$message$action, list(type = "artifact_toggle"))
  expect_null(messages[[1]]$message$html_deps)
  expect_null(messages[[2]]$message$html_deps)
})

test_that("chat artifact panel controls validate inputs and sessions", {
  session <- shiny::MockShinySession$new()

  expect_error(
    chat_artifact_panel_show("", session = session),
    "`id` must be a single string"
  )
  expect_error(
    chat_artifact_panel_update("chat", title = list(), session = session),
    "`title` must be a single string"
  )
  expect_error(
    chat_artifact_panel_update(
      "chat",
      content = function() NULL,
      session = session
    ),
    "`content` must be static UI content"
  )
  expect_error(chat_artifact_panel_hide("chat"), "active Shiny session")
})
