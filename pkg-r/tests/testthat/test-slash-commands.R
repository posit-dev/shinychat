test_that("chat_ui does not emit data-slash-commands attribute by default", {
  ui <- chat_ui("chat")
  html <- as.character(ui)
  expect_false(grepl("data-slash-commands", html))
})

test_that("chat_mod_server slash_command supports zero-argument handlers", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  calls <- 0

  shiny::testServer(
    chat_mod_server,
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
        chat_slash_command = list(command = "clear", args = "ignored")
      )

      expect_equal(calls, 1)
    }
  )
})

test_that("chat_mod_server slash_command rejects handlers with more than one parameter", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  shiny::testServer(
    chat_mod_server,
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

test_that("chat_mod_server slash_command errors on duplicate name by default", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  shiny::testServer(
    chat_mod_server,
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

test_that("chat_mod_server slash_command removal unregisters the command", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  calls <- 0

  shiny::testServer(
    chat_mod_server,
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
        chat_slash_command = list(command = "greet", args = "")
      )
      expect_equal(calls, 1)

      # Remove and verify it no longer fires
      remove()
      session$setInputs(
        chat_slash_command = list(command = "greet", args = "")
      )
      expect_equal(calls, 1)

      # Re-registering without force should succeed after removal
      session$returned$slash_command(
        "greet",
        "Say hello again",
        function() calls <<- calls + 1
      )
      session$setInputs(
        chat_slash_command = list(command = "greet", args = "")
      )
      expect_equal(calls, 2)
    }
  )
})

test_that("chat_mod_server slash_command allows overwrite with force = TRUE", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  calls <- character()

  shiny::testServer(
    chat_mod_server,
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
        chat_slash_command = list(command = "greet", args = "")
      )

      expect_equal(calls, "v2")
    }
  )
})

test_that("chat_mod_server slash_command echo defaults to handler presence", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  shiny::testServer(
    chat_mod_server,
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

      # slash_commands lives in the module closure; read it via the function env
      cmds <- get(
        "slash_commands",
        envir = environment(session$returned$slash_command)
      )
      expect_true(cmds[["withhandler"]]$definition$echo)
      expect_false(cmds[["nohandler"]]$definition$echo)
      expect_null(cmds[["nohandler"]]$handler)
    }
  )
})

test_that("chat_mod_server slash_command echo can be set explicitly", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  shiny::testServer(
    chat_mod_server,
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
      cmds <- get(
        "slash_commands",
        envir = environment(session$returned$slash_command)
      )
      expect_false(cmds[["sideeffect"]]$definition$echo)
    }
  )
})

test_that("chat_mod_server slash_command rejects a non-function, non-NULL handler", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  shiny::testServer(
    chat_mod_server,
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

test_that("chat_mod_server slash_command with NULL handler does not run server-side", {
  local_mocked_bindings(
    chat_restore = function(...) invisible(NULL),
    send_chat_action = function(...) invisible(NULL)
  )

  calls <- 0

  shiny::testServer(
    chat_mod_server,
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

      slash_commands <- get(
        "slash_commands",
        envir = environment(session$returned$slash_command)
      )
      expect_null(slash_commands[["clientside"]]$handler)

      # Invoking the NULL-handler command must not error (the observer guard
      # skips calling a non-function handler) and must not run the real handler.
      expect_no_error(
        session$setInputs(
          chat_slash_command = list(
            command = "clientside",
            args = "",
            echo = FALSE
          )
        )
      )
      expect_equal(calls, 0)

      # Sanity: the real handler still fires when its command is invoked.
      session$setInputs(
        chat_slash_command = list(command = "real", args = "")
      )
      expect_equal(calls, 1)
    }
  )
})
