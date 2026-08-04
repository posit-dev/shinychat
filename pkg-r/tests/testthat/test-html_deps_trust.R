make_dep <- function(name, version, script) {
  list(
    name = name,
    version = version,
    src = list(href = paste0("lib/", name)),
    script = script
  )
}

test_that("reported htmlDeps are dropped when the server has sent none", {
  session <- shiny::MockShinySession$new()
  reported <- list(
    list(
      role = "assistant",
      segments = list(list(content = "hi", content_type = "markdown")),
      htmlDeps = list(make_dep("evil", "1.0", "evil.js"))
    )
  )

  out <- messages_input_value(reported, session)

  expect_null(out[[1]]$htmlDeps)
})

test_that("a reported dep is replaced by the server's own copy of it", {
  session <- shiny::MockShinySession$new()
  sent <- make_dep("widget", "1.0", "widget.js")
  send_chat_action(
    "chat",
    action = list(type = "message"),
    html_deps = list(sent),
    session = session
  )

  # Same identity, attacker-chosen payload.
  forged <- make_dep("widget", "1.0", "evil.js")
  forged$head <- "<script>alert(1)</script>"
  reported <- list(
    list(
      role = "assistant",
      segments = list(list(content = "hi", content_type = "markdown")),
      htmlDeps = list(forged)
    )
  )

  out <- messages_input_value(reported, session)

  expect_equal(out[[1]]$htmlDeps, list(sent))
})

test_that("unknown deps are dropped while known ones survive", {
  session <- shiny::MockShinySession$new()
  known <- make_dep("widget", "1.0", "widget.js")
  send_chat_action(
    "chat",
    action = list(type = "message"),
    html_deps = list(known),
    session = session
  )

  reported <- list(
    list(
      role = "assistant",
      segments = list(list(content = "hi", content_type = "markdown")),
      htmlDeps = list(
        make_dep("evil", "1.0", "evil.js"),
        known,
        # Right name, wrong version -- not something we sent.
        make_dep("widget", "9.9", "evil.js")
      )
    )
  )

  out <- messages_input_value(reported, session)

  expect_equal(out[[1]]$htmlDeps, list(known))
})

test_that("deps with a malformed identity are dropped", {
  session <- shiny::MockShinySession$new()
  send_chat_action(
    "chat",
    action = list(type = "message"),
    html_deps = list(make_dep("widget", "1.0", "widget.js")),
    session = session
  )

  reported <- list(
    list(
      role = "assistant",
      segments = list(list(content = "hi", content_type = "markdown")),
      htmlDeps = list(
        list(script = "evil.js"),
        list(name = c("widget", "widget"), version = "1.0"),
        list(name = "widget", version = NA_character_)
      )
    )
  )

  expect_null(messages_input_value(reported, session)[[1]]$htmlDeps)
})

test_that("a forged snapshot cannot replay attacker scripts through a bookmark", {
  # End-to-end for the stored-script vector: a server bookmark is shareable via
  # its `_state_id_` URL, so anything we persist from the browser's `_messages`
  # report is replayed into whoever opens that URL.
  attacker <- shiny::MockShinySession$new()
  forged <- list(
    list(
      role = "assistant",
      segments = list(list(content = "hi", content_type = "markdown")),
      htmlDeps = list(make_dep("pwn", "1.0", "https://evil.test/pwn.js"))
    )
  )
  sanitized <- messages_input_value(forged, attacker)

  local_mocked_bindings(
    is_server_bookmarkstore = function() TRUE,
    get_reported_messages = function(session, chat_id) sanitized
  )
  state <- rlang::env(values = list())
  bookmark_save_ui(state, attacker, "chat")

  victim <- shiny::MockShinySession$new()
  captured_deps <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      captured_deps[[length(captured_deps) + 1]] <<- html_deps
      invisible()
    }
  )
  bookmark_restore_ui(state, client = NULL, id = "chat", session = victim)

  expect_true(all(vapply(captured_deps, is.null, logical(1))))
})
