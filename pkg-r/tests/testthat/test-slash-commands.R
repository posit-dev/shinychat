# chat_server isn't a module function, so session$returned requires a module
# wrapper to work with shiny::testServer.
chat_server_module <- function(id, client, ...) {
  shiny::moduleServer(id, function(input, output, session) {
    chat_server("chat", client, ..., session = session)
  })
}

test_that("chat_ui does not emit data-slash-commands attribute by default", {
  ui <- chat_ui("chat")
  html <- as.character(ui)
  expect_false(grepl("data-slash-commands", html))
})

test_that("chat_server slash_command supports zero-argument handlers", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  calls <- 0

  shiny::testServer(
    chat_server_module,
    args = list(
      client = structure(list(), class = "Chat"),
      bookmark_on_input = FALSE,
      bookmark_on_response = FALSE
    ),
    {
      session$returned$slash_command(
        "clear",
        "Clear the conversation",
        function() {
          calls <<- calls + 1
        }
      )

      session$setInputs(
        chat_slash_command = list(command = "clear", userText = "ignored")
      )

      expect_equal(calls, 1)
    }
  )
})

test_that("chat_server slash_command rejects handlers with more than one parameter", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  shiny::testServer(
    chat_server_module,
    args = list(
      client = structure(list(), class = "Chat"),
      bookmark_on_input = FALSE,
      bookmark_on_response = FALSE
    ),
    {
      expect_error(
        session$returned$slash_command(
          "bad",
          "Too many parameters",
          function(a, b) NULL
        ),
        "0 or 1 argument"
      )
    }
  )
})

test_that("chat_server slash_command errors on duplicate name by default", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  shiny::testServer(
    chat_server_module,
    args = list(
      client = structure(list(), class = "Chat"),
      bookmark_on_input = FALSE,
      bookmark_on_response = FALSE
    ),
    {
      session$returned$slash_command("greet", "Say hello", function() NULL)
      expect_error(
        session$returned$slash_command("greet", "Say hi", function() NULL),
        "already registered"
      )
    }
  )
})

test_that("chat_server slash_command removal unregisters the command", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  calls <- 0

  shiny::testServer(
    chat_server_module,
    args = list(
      client = structure(list(), class = "Chat"),
      bookmark_on_input = FALSE,
      bookmark_on_response = FALSE
    ),
    {
      remove <- session$returned$slash_command(
        "greet",
        "Say hello",
        function() calls <<- calls + 1
      )

      # Command works before removal
      session$setInputs(
        chat_slash_command = list(command = "greet", userText = "")
      )
      expect_equal(calls, 1)

      # Remove and verify it no longer fires
      remove()
      session$setInputs(
        chat_slash_command = list(command = "greet", userText = "")
      )
      expect_equal(calls, 1)

      # Re-registering without force should succeed after removal
      session$returned$slash_command(
        "greet",
        "Say hello again",
        function() calls <<- calls + 1
      )
      session$setInputs(
        chat_slash_command = list(command = "greet", userText = "")
      )
      expect_equal(calls, 2)
    }
  )
})

test_that("chat_server slash_command allows overwrite with force = TRUE", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  calls <- character()

  shiny::testServer(
    chat_server_module,
    args = list(
      client = structure(list(), class = "Chat"),
      bookmark_on_input = FALSE,
      bookmark_on_response = FALSE
    ),
    {
      session$returned$slash_command(
        "greet",
        "Say hello",
        function() calls <<- c(calls, "v1")
      )
      session$returned$slash_command(
        "greet",
        "Say hi",
        function() calls <<- c(calls, "v2"),
        force = TRUE
      )

      session$setInputs(
        chat_slash_command = list(command = "greet", userText = "")
      )

      expect_equal(calls, "v2")
    }
  )
})

test_that("chat_server slash_command echo defaults to handler presence", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  shiny::testServer(
    chat_server_module,
    args = list(
      client = structure(list(), class = "Chat"),
      bookmark_on_input = FALSE,
      bookmark_on_response = FALSE
    ),
    {
      session$returned$slash_command(
        "withhandler",
        "Has handler",
        function() NULL
      )
      session$returned$slash_command("nohandler", "No handler", NULL)

      # slash_commands state now lives in session$userData, keyed by id; read
      # it back through the same registry accessor the machinery uses.
      cmds <- slash_commands_registry("chat", session = session)()
      expect_true(cmds[["withhandler"]]$definition$echo)
      expect_false(cmds[["nohandler"]]$definition$echo)
      expect_null(cmds[["nohandler"]]$handler)
    }
  )
})

test_that("chat_server slash_command echo can be set explicitly", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  shiny::testServer(
    chat_server_module,
    args = list(
      client = structure(list(), class = "Chat"),
      bookmark_on_input = FALSE,
      bookmark_on_response = FALSE
    ),
    {
      session$returned$slash_command(
        "sideeffect",
        "Side effect",
        function() NULL,
        echo = FALSE
      )
      cmds <- slash_commands_registry("chat", session = session)()
      expect_false(cmds[["sideeffect"]]$definition$echo)
    }
  )
})

test_that("chat_server slash_command rejects a non-function, non-NULL handler", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  shiny::testServer(
    chat_server_module,
    args = list(
      client = structure(list(), class = "Chat"),
      bookmark_on_input = FALSE,
      bookmark_on_response = FALSE
    ),
    {
      expect_error(
        session$returned$slash_command("bad", "Bad", handler = 42),
        "must be a function"
      )
    }
  )
})

test_that("chat_server slash_command with NULL handler does not run server-side", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  calls <- 0

  shiny::testServer(
    chat_server_module,
    args = list(
      client = structure(list(), class = "Chat"),
      bookmark_on_input = FALSE,
      bookmark_on_response = FALSE
    ),
    {
      # A real handler on a different command, to prove the NULL command does not
      # accidentally invoke anything.
      session$returned$slash_command(
        "real",
        "Real",
        function() calls <<- calls + 1
      )
      session$returned$slash_command("clientside", "Client side", NULL)

      slash_commands <- slash_commands_registry("chat", session = session)()
      expect_null(slash_commands[["clientside"]]$handler)

      # Invoking the NULL-handler command must not error (the observer guard
      # skips calling a non-function handler) and must not run the real handler.
      expect_no_error(
        session$setInputs(
          chat_slash_command = list(
            command = "clientside",
            userText = "",
            echo = FALSE
          )
        )
      )
      expect_equal(calls, 0)

      # Sanity: the real handler still fires when its command is invoked.
      session$setInputs(
        chat_slash_command = list(command = "real", userText = "")
      )
      expect_equal(calls, 1)
    }
  )
})


# ---------------------------------------------------------------------------
# register_slash_command(): the standalone, free-function entry point. Works
# WITHOUT chat_server() and without threading any returned value -- callers
# just need the chat `id` and the `session`. chat_server() uses the same
# machinery internally.
# ---------------------------------------------------------------------------

# A bare server function (no chat_server, no module wrapper) so these tests
# exercise register_slash_command() exactly as an app author would call it.
slash_only_server <- function(input, output, session) {
  invisible(NULL)
}

test_that("register_slash_command dispatches a zero-argument handler standalone", {
  local_mocked_bindings(send_chat_action = function(...) invisible(NULL))
  calls <- 0

  shiny::testServer(slash_only_server, {
    register_slash_command(
      "chat", "clear", "Clear the conversation",
      function() calls <<- calls + 1,
      session = session
    )
    session$setInputs(
      chat_slash_command = list(command = "clear", userText = "ignored")
    )
    expect_equal(calls, 1)
  })
})

test_that("register_slash_command passes a ContentSlashCommand to 1-arg handlers", {
  local_mocked_bindings(send_chat_action = function(...) invisible(NULL))
  received <- NULL

  shiny::testServer(slash_only_server, {
    register_slash_command(
      "chat", "greet", "Greet someone",
      function(content) received <<- content,
      session = session
    )
    session$setInputs(
      chat_slash_command = list(command = "greet", userText = "world")
    )
    expect_s3_class(received, "shinychat::ContentSlashCommand")
    expect_equal(received@command, "greet")
    expect_equal(received@user_text, "world")
    expect_match(received@text, "greet slash command with arguments: world")
  })
})

test_that("register_slash_command validates name, description, handler, arity", {
  local_mocked_bindings(send_chat_action = function(...) invisible(NULL))

  shiny::testServer(slash_only_server, {
    expect_error(
      register_slash_command("chat", c("a", "b"), "d", NULL, session = session),
      "single string"
    )
    expect_error(
      register_slash_command("chat", "bad name", "d", NULL, session = session),
      "alphanumeric"
    )
    expect_error(
      register_slash_command("chat", "ok", 1, NULL, session = session),
      "single string"
    )
    expect_error(
      register_slash_command("chat", "ok", "d", 42, session = session),
      "function or"
    )
    expect_error(
      register_slash_command("chat", "ok", "d", function(a, b) NULL, session = session),
      "0 or 1 argument"
    )
  })
})

test_that("register_slash_command echo defaults to handler presence", {
  local_mocked_bindings(send_chat_action = function(...) invisible(NULL))

  shiny::testServer(slash_only_server, {
    register_slash_command("chat", "withh", "has handler", function() NULL, session = session)
    register_slash_command("chat", "noh", "no handler", NULL, session = session)
    register_slash_command("chat", "forced", "explicit", NULL, echo = TRUE, session = session)

    cmds <- slash_commands_registry("chat", session = session)()
    expect_true(cmds[["withh"]]$definition$echo)
    expect_false(cmds[["noh"]]$definition$echo)
    expect_true(cmds[["forced"]]$definition$echo)
  })
})

test_that("register_slash_command enforces force = TRUE on duplicate names", {
  local_mocked_bindings(send_chat_action = function(...) invisible(NULL))

  shiny::testServer(slash_only_server, {
    register_slash_command("chat", "dup", "first", NULL, session = session)
    expect_error(
      register_slash_command("chat", "dup", "second", NULL, session = session),
      "already registered"
    )
    expect_no_error(
      register_slash_command("chat", "dup", "second", NULL, force = TRUE, session = session)
    )
  })
})

test_that("register_slash_command returns a working unregister function", {
  local_mocked_bindings(send_chat_action = function(...) invisible(NULL))

  shiny::testServer(slash_only_server, {
    unregister <- register_slash_command("chat", "tmp", "temp", NULL, session = session)
    cmds <- slash_commands_registry("chat", session = session)
    expect_true("tmp" %in% names(cmds()))
    unregister()
    expect_false("tmp" %in% names(cmds()))
  })
})

test_that("register_slash_command reuses one registry per (session, id)", {
  local_mocked_bindings(send_chat_action = function(...) invisible(NULL))

  shiny::testServer(slash_only_server, {
    register_slash_command("chat", "one", "first", NULL, session = session)
    register_slash_command("chat", "two", "second", NULL, session = session)
    # Both commands land in the same registry -- no threading, no re-setup.
    cmds <- slash_commands_registry("chat", session = session)()
    expect_setequal(names(cmds), c("one", "two"))
  })
})
