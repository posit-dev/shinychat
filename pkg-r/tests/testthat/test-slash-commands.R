# chat_server isn't a module function, so session$returned requires a module
# wrapper to work with shiny::testServer.
chat_server_module <- function(id, client, ...) {
  shiny::moduleServer(id, function(input, output, session) {
    chat_server("chat", client, ..., session = session)
  })
}

# A plain server function with no chat_server(), the way an app that drives
# chat_ui() with its own logic would call chat_slash_command().
bare_server <- function(input, output, session) NULL

# Record every chat action sent to the client instead of sending it.
record_chat_actions <- function(env = parent.frame()) {
  sent <- new.env()
  sent$actions <- list()
  local_mocked_bindings(
    send_chat_action = function(id, action, html_deps = NULL, session) {
      sent$actions[[length(sent$actions) + 1]] <- list(id = id, action = action)
      invisible(NULL)
    },
    .env = env
  )
  sent
}

actions_of_type <- function(sent, type, id = NULL) {
  Filter(
    function(x) identical(x$action$type, type) && (is.null(id) || x$id == id),
    sent$actions
  )
}

last_slash_commands_sync <- function(sent, id = NULL) {
  syncs <- actions_of_type(sent, "update_slash_commands", id)
  if (length(syncs) == 0) {
    return(NULL)
  }
  syncs[[length(syncs)]]$action$commands
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
      history = FALSE
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
      history = FALSE
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
      history = FALSE
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
      history = FALSE
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
      history = FALSE
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
  local_mocked_bindings(chat_restore = function(...) invisible(NULL))
  sent <- record_chat_actions()

  shiny::testServer(
    chat_server_module,
    args = list(
      client = structure(list(), class = "Chat"),
      history = FALSE
    ),
    {
      session$returned$slash_command(
        "withhandler",
        "Has handler",
        function() NULL
      )
      session$returned$slash_command("nohandler", "No handler", NULL)
      session$flushReact()

      expect_equal(
        last_slash_commands_sync(sent),
        list(
          list(name = "withhandler", description = "Has handler", echo = TRUE),
          list(name = "nohandler", description = "No handler", echo = FALSE)
        )
      )
    }
  )
})

test_that("chat_server slash_command echo can be set explicitly", {
  local_mocked_bindings(chat_restore = function(...) invisible(NULL))
  sent <- record_chat_actions()

  shiny::testServer(
    chat_server_module,
    args = list(
      client = structure(list(), class = "Chat"),
      history = FALSE
    ),
    {
      session$returned$slash_command(
        "sideeffect",
        "Side effect",
        function() NULL,
        echo = FALSE
      )
      session$flushReact()

      expect_equal(
        last_slash_commands_sync(sent),
        list(list(
          name = "sideeffect",
          description = "Side effect",
          echo = FALSE
        ))
      )
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
      history = FALSE
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
      history = FALSE
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

test_that("chat_slash_command sends command definitions to the client without chat_server", {
  sent <- record_chat_actions()

  shiny::testServer(bare_server, {
    chat_slash_command("chat", "clear", "Clear", function() NULL, echo = FALSE)
    chat_slash_command("chat", "ask", "Ask", function(content) NULL)
    chat_slash_command("chat", "js", "Client side", NULL)
    session$flushReact()

    expect_equal(
      last_slash_commands_sync(sent, "chat"),
      list(
        list(name = "clear", description = "Clear", echo = FALSE),
        list(name = "ask", description = "Ask", echo = TRUE),
        list(name = "js", description = "Client side", echo = FALSE)
      )
    )
  })
})

test_that("chat_slash_command dispatches a zero-argument handler without chat_server", {
  sent <- record_chat_actions()
  calls <- 0

  shiny::testServer(bare_server, {
    chat_slash_command("chat", "clear", "Clear", function() calls <<- calls + 1)
    session$setInputs(
      chat_slash_command = list(command = "clear", userText = "ignored")
    )

    expect_equal(calls, 1)
    expect_length(actions_of_type(sent, "remove_loading", "chat"), 1)
  })
})

test_that("chat_slash_command passes a ContentSlashCommand to one-argument handlers", {
  record_chat_actions()
  received <- NULL

  shiny::testServer(bare_server, {
    chat_slash_command("chat", "greet", "Greet", function(content) {
      received <<- content
    })
    session$setInputs(
      chat_slash_command = list(command = "greet", userText = "world")
    )

    expect_true(S7::S7_inherits(received, ContentSlashCommand))
    expect_equal(received@command, "greet")
    expect_equal(received@user_text, "world")
    expect_equal(
      received@text,
      "The user entered the /greet slash command with arguments: world"
    )
  })
})

test_that("chat_slash_command's unregister function removes the command from the client", {
  sent <- record_chat_actions()
  calls <- 0

  shiny::testServer(bare_server, {
    remove <- chat_slash_command("chat", "tmp", "Temp", function() {
      calls <<- calls + 1
    })
    session$flushReact()
    remove()
    session$flushReact()

    expect_equal(last_slash_commands_sync(sent, "chat"), list())

    session$setInputs(chat_slash_command = list(command = "tmp", userText = ""))
    expect_equal(calls, 0)
  })
})

test_that("chat_slash_command keeps commands for different chats separate", {
  sent <- record_chat_actions()
  calls <- character()

  shiny::testServer(bare_server, {
    chat_slash_command("a", "help", "Help A", function() {
      calls <<- c(calls, "a")
    })
    chat_slash_command("b", "help", "Help B", function() {
      calls <<- c(calls, "b")
    })
    session$flushReact()

    expect_equal(
      last_slash_commands_sync(sent, "a"),
      list(list(name = "help", description = "Help A", echo = TRUE))
    )

    session$setInputs(b_slash_command = list(command = "help", userText = ""))
    expect_equal(calls, "b")
  })
})

test_that("chat_slash_command and chat_server's $slash_command share one set of commands", {
  local_mocked_bindings(chat_restore = function(...) invisible(NULL))
  record_chat_actions()
  calls <- 0

  shiny::testServer(
    chat_server_module,
    args = list(client = structure(list(), class = "Chat"), history = FALSE),
    {
      # testServer()'s default domain here is the root mock session, not the
      # module (unlike in a real module), so pass the module session explicitly.
      chat_slash_command(
        "chat",
        "greet",
        "Say hello",
        function() calls <<- calls + 1,
        session = session
      )
      expect_error(
        session$returned$slash_command("greet", "Say hi", function() NULL),
        "already registered"
      )

      session$setInputs(
        chat_slash_command = list(command = "greet", userText = "")
      )
      expect_equal(calls, 1)
    }
  )
})

test_that("a promise-returning handler keeps the loading state until it resolves", {
  sent <- record_chat_actions()
  resolve_reply <- NULL

  shiny::testServer(bare_server, {
    chat_slash_command("chat", "ask", "Ask a remote agent", function() {
      promises::promise(function(resolve, reject) resolve_reply <<- resolve)
    })
    session$setInputs(chat_slash_command = list(command = "ask", userText = ""))
    later::run_now(0.05)
    expect_length(actions_of_type(sent, "remove_loading"), 0)

    resolve_reply(NULL)
    wait_until(
      function() length(actions_of_type(sent, "remove_loading")) == 1,
      description = "remove_loading after the handler's promise resolves"
    )
  })
})

test_that("a promise-returning handler that rejects is reported and clears the loading state", {
  sent <- record_chat_actions()

  shiny::testServer(bare_server, {
    chat_slash_command("chat", "ask", "Ask", function() {
      promises::promise_reject(simpleError("agent unreachable"))
    })
    expect_warning(
      {
        session$setInputs(
          chat_slash_command = list(command = "ask", userText = "")
        )
        wait_until(
          function() length(actions_of_type(sent, "remove_loading")) == 1,
          description = "remove_loading after the handler's promise rejects"
        )
      },
      "Error in slash command '/ask'"
    )
  })
})
