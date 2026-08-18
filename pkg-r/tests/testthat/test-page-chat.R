artifact_child <- function(ui) {
  children <- Filter(
    function(child) identical(child$name, "shiny-chat-artifact"),
    ui$children
  )
  expect_length(children, 1)
  children[[1]]
}

test_that("chat_sidebar() validates and normalizes configuration", {
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

test_that("chat_artifact() validates configuration", {
  artifact <- chat_artifact(
    htmltools::tags$p("Artifact content"),
    title = "Preview",
    width = 480,
    open = TRUE,
    resizable = FALSE
  )

  expect_s3_class(artifact, "chat_artifact")
  expect_equal(artifact$title, "Preview")
  expect_equal(artifact$width, "480px")
  expect_true(artifact$open)
  expect_false(artifact$resizable)

  expect_snapshot(error = TRUE, chat_artifact(title = list()))
  expect_snapshot(error = TRUE, chat_artifact(width = -1))
  expect_snapshot(error = TRUE, chat_artifact(width = "bogus"))
  expect_snapshot(error = TRUE, chat_artifact(open = "yes"))
  expect_snapshot(error = TRUE, chat_artifact(data_role = "artifact"))
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

  expect_snapshot(error = TRUE, chat_nav_panel(""))
  expect_snapshot(error = TRUE, chat_nav_panel("Settings", value = ""))
  expect_snapshot(error = TRUE, chat_nav_panel("Settings", sidebar = list()))
  expect_snapshot(
    error = TRUE,
    chat_nav_panel("Settings", sidebar = bslib::sidebar())
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
    artifact = chat_artifact(
      htmltools::tags$div("Artifact", artifact_dep),
      title = "",
      width = "30rem",
      open = TRUE,
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
  ui <- chat_ui("chat", artifact = FALSE, show_history = FALSE)

  expect_equal(ui$attribs[["show-history"]], "false")
  expect_false(any(vapply(
    ui$children,
    function(child) identical(child$name, "shiny-chat-artifact"),
    logical(1)
  )))

  expect_snapshot(error = TRUE, chat_ui("chat", artifact = list()))
  expect_snapshot(error = TRUE, chat_ui("chat", show_history = NA))
})
