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

test_that("chat_drawer_show() sends an action without updates", {
  spy <- artifact_session_with_spy()
  chat_drawer_show("chat", session = spy$session)

  messages <- spy$messages()
  expect_length(messages, 1)
  expect_equal(messages[[1]]$type, "shinyChatMessage")
  expect_equal(messages[[1]]$message$id, spy$session$ns("chat"))
  expect_equal(messages[[1]]$message$action, list(type = "drawer_show"))
  expect_null(messages[[1]]$message$html_deps)
})

test_that("chat_drawer_show() serializes content, dependencies, and title", {
  spy <- artifact_session_with_spy()
  dependency <- htmltools::htmlDependency(
    "artifact-dependency",
    "1.0.0",
    src = tempdir()
  )

  chat_drawer_show(
    "chat",
    content = htmltools::tags$div("Artifact", dependency),
    title = "Preview",
    session = spy$session
  )

  message <- spy$messages()[[1]]$message
  expect_equal(message$action$type, "drawer_show")
  expect_match(message$action$content, "<div>Artifact</div>", fixed = TRUE)
  expect_no_match(message$action$content, "shiny-chat-raw-html", fixed = TRUE)
  expect_equal(message$action$title, "Preview")
  expect_length(message$html_deps, 1)
  expect_equal(message$html_deps[[1]]$name, "artifact-dependency")
})

test_that("chat_drawer_show() preserves omitted fields and clears empty UI", {
  spy <- artifact_session_with_spy()
  chat_drawer_show(
    "chat",
    content = htmltools::tagList(),
    title = "",
    session = spy$session
  )

  message <- spy$messages()[[1]]$message
  expect_equal(
    message$action,
    list(
      type = "drawer_show",
      content = "",
      title = ""
    )
  )
  expect_equal(message$html_deps, list())
})

test_that("chat_drawer_update() changes supplied fields without visibility", {
  spy <- artifact_session_with_spy()
  chat_drawer_update(
    "chat",
    content = htmltools::tags$span("Updated"),
    session = spy$session
  )

  message <- spy$messages()[[1]]$message
  expect_equal(message$action$type, "drawer_update")
  expect_match(message$action$content, "<span>Updated</span>", fixed = TRUE)
  expect_equal(message$html_deps, list())
})

test_that("chat_drawer_show() mixed tagList content keeps bare string unescaped", {
  spy <- artifact_session_with_spy()
  chat_drawer_show(
    "chat",
    content = htmltools::tagList("**markdown**", htmltools::tags$b("bold")),
    session = spy$session
  )

  message <- spy$messages()[[1]]$message
  expect_equal(message$action$type, "drawer_show")
  # The bare string portion is raw (unescaped), not HTML-escaped by renderTags.
  expect_match(message$action$content, "**markdown**", fixed = TRUE)
  # The tag portion is rendered as HTML.
  expect_match(message$action$content, "<b>bold</b>", fixed = TRUE)
  expect_no_match(message$action$content, "shiny-chat-raw-html", fixed = TRUE)
})

test_that("chat_drawer_update() mixed tagList content keeps bare string unescaped", {
  spy <- artifact_session_with_spy()
  chat_drawer_update(
    "chat",
    content = htmltools::tagList("**md**", htmltools::tags$span("tag")),
    session = spy$session
  )

  message <- spy$messages()[[1]]$message
  expect_equal(message$action$type, "drawer_update")
  expect_match(message$action$content, "**md**", fixed = TRUE)
  expect_match(message$action$content, "<span>tag</span>", fixed = TRUE)
})

test_that("chat_drawer_update() sends a title-only update", {
  spy <- artifact_session_with_spy()
  chat_drawer_update("chat", title = "", session = spy$session)

  message <- spy$messages()[[1]]$message
  expect_equal(message$action, list(type = "drawer_update", title = ""))
  expect_null(message$html_deps)
})

test_that("chat_drawer_hide() and chat_drawer_toggle() send exact actions", {
  spy <- artifact_session_with_spy()
  chat_drawer_hide("chat", session = spy$session)
  chat_drawer_toggle("chat", session = spy$session)

  messages <- spy$messages()
  expect_equal(messages[[1]]$message$action, list(type = "drawer_hide"))
  expect_equal(messages[[2]]$message$action, list(type = "drawer_toggle"))
  expect_null(messages[[1]]$message$html_deps)
  expect_null(messages[[2]]$message$html_deps)
})

test_that("chat drawer controls validate inputs and sessions", {
  session <- shiny::MockShinySession$new()

  expect_error(
    chat_drawer_show("", session = session),
    "`id` must be a single string"
  )
  expect_error(
    chat_drawer_update("chat", title = list(), session = session),
    "`title` must be a single string"
  )
  expect_error(
    chat_drawer_update(
      "chat",
      content = function() NULL,
      session = session
    ),
    "`content` must be static UI content"
  )
  expect_error(chat_drawer_hide("chat"), "active Shiny session")
})
