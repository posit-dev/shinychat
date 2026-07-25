#' Add Shiny bookmarking for shinychat
#'
#' @description
#' Adds Shiny bookmarking hooks to save and restore the \pkg{ellmer} chat
#' `client`. Also restores chat messages from the history in the `client`.
#'
#' If either `bookmark_on_input` or `bookmark_on_response` is `TRUE`, the Shiny
#' App's bookmark will be automatically updated without showing a modal to the
#' user.
#'
#' Note: The chat's displayed UI is restored from the browser's own message
#' snapshot when `bookmarkStore = "server"`, so display-only transformations
#' (rendering applied between receiving a message and showing it) are preserved.
#' Under `bookmarkStore = "url"`, and for bookmarks saved before this snapshot
#' existed, restoration falls back to re-deriving the UI from the `client`'s
#' turns, which does not capture such transformations. The greeting content is
#' also saved/restored automatically.
#'
#' To avoid restoring chat history from the `client`, you can ensure that the
#' history is empty by calling `client$set_turns(list())` before passing the
#' client to `chat_restore()`.
#'
#' `chat_restore()` bookmarks the whole session and doesn't know about
#' multiple conversations. If you need per-conversation history (the chat
#' history drawer, switching between saved conversations), use
#' [chat_enable_history()] with `history_options(restore_mode = "bookmark")`
#' instead — it replaces `chat_restore()`'s job for history-aware apps. The
#' two are mutually exclusive; `chat_app()` picks one or the other based on
#' whether `history` is set.
#'
#' @param id The ID of the chat element
#' @param client The \pkg{ellmer} LLM chat client.
#' @param ... Used for future parameter expansion.
#' @param bookmark_on_input A logical value determines if the bookmark should be updated when the user submits a message. Default is `TRUE`.
#' @param bookmark_on_response A logical value determines if the bookmark should be updated when the response stream completes. Default is `TRUE`.
#' @param restore_ui Whether to render the client's existing turns into the
#'   chat UI on registration. Default is `TRUE`. Set to `FALSE` when
#'   re-registering bookmarks after a client swap (where the UI already reflects
#'   the conversation).
#' @param session The Shiny session object
#' @returns Invisibly returns a function that, when called, cancels all
#'   bookmark registrations made by this call. This is useful when swapping
#'   the chat client: cancel the previous bookmarks, then call
#'   `chat_restore()` again with the new client.
#'
#' @examplesIf interactive()
#' library(shiny)
#' library(bslib)
#' library(shinychat)
#'
#' ui <- function(request) {
#'   page_fillable(
#'     chat_ui("chat", fill = TRUE)
#'   )
#' }
#'
#' server <- function(input, output, session) {
#'   chat_client <- ellmer::chat_ollama(
#'     system_prompt = "Important: Always respond in a limerick",
#'     model = "qwen2.5-coder:1.5b",
#'     echo = TRUE
#'   )
#'   # Update bookmark to chat on user submission and completed response
#'   chat_restore("chat", chat_client)
#'
#'   observeEvent(input$chat_user_input, {
#'     stream <- chat_client$stream_async(input$chat_user_input)
#'     chat_append("chat", stream)
#'   })
#' }
#'
#' # Enable bookmarking!
#' shinyApp(ui, server, enableBookmarking = "server")
#' @export
chat_restore <- function(
  id,
  client,
  ...,
  bookmark_on_input = TRUE,
  bookmark_on_response = TRUE,
  restore_ui = TRUE,
  session = getDefaultReactiveDomain()
) {
  rlang::check_dots_empty()
  stopifnot(is.character(id) && length(id) == 1)

  rlang::check_installed("ellmer")
  if (!(inherits(client, "R6") && inherits(client, "Chat"))) {
    rlang::abort(
      "`client` must be an `ellmer::Chat()` object. If you would like to have {shinychat} support your own package, please submit a GitHub Issue at https://github.com/posit-dev/shinychat"
    )
  }
  bookmark_on_input <- rlang::is_true(bookmark_on_input)
  bookmark_on_response <- rlang::is_true(bookmark_on_response)

  if (is.null(session)) {
    rlang::abort(
      "A `session` must be provided. Be sure to call `chat_restore()` where a session context is available."
    )
  }

  # Exclude works with bookmark names
  excluded_names <- session$getBookmarkExclude()
  id_user_input <- paste0(id, "_user_input")
  id_messages <- paste0(id, "_messages")
  to_exclude <- setdiff(
    paste0(
      id,
      c(
        "_user_input",
        "_cancel",
        "_slash_command",
        "_greeting_requested",
        "_greeting_dismissed",
        # Carries StoredMessage-like list objects, which aren't
        # JSON-serializable for Shiny's bookmark input.json.
        "_messages"
      )
    ),
    excluded_names
  )
  if (length(to_exclude) > 0) {
    session$setBookmarkExclude(c(excluded_names, to_exclude))
  }

  # Save
  cancel_on_bookmark_client <-
    session$onBookmark(function(state) {
      if (id %in% names(state$values)) {
        rlang::abort(
          paste0(
            "Bookmark value with id (`\"",
            id,
            "\"`)) already exists. Please remove it or use a different id."
          )
        )
      }

      client_state <- client_get_state(client)

      state$values[[id]] <- client_state
      bookmark_save_ui(state, session, id)
    })

  cancel_on_bookmark_greeting <-
    session$onBookmark(function(state) {
      g <- get_session_greeting_state(session, id)
      if (!is.null(g) && is.character(g$content) && nzchar(g$content)) {
        state$values[[paste0(id, "_greeting")]] <- g
      }
    })

  # Guards against cancel_bookmark_on_response() firing on the browser's echo
  # of UI we just populated ourselves (initial turn replay or restore), rather
  # than an actual user-triggered response. is_replaying_ui/suppress_next_bookmark
  # mirror HistoryController's is_replaying/suppress_next_save pair (see
  # chat_history.R): the echo is async, so is_replaying alone (cleared on next
  # flush) isn't enough to cover every flush between now and the echo's
  # arrival. Those two flags are NOT sufficient on their own here, though:
  # replaying N existing messages (turn replay or restore) can make the
  # browser echo back N separate growing "_messages" snapshots -- one as each
  # message settles -- and every one of them can independently end in an
  # assistant message, so a single-use suppression flag only catches the
  # first of an arbitrary number of pre-interaction echoes (confirmed
  # empirically: a 2-message replay produces two such echoes, both bookmark-
  # worthy by the naive check). has_user_submitted closes that gap: no
  # response-triggered bookmark is legitimate before the user has actually
  # submitted something in *this* session, no matter how many startup echoes
  # arrive before that happens.
  is_replaying_ui <- FALSE
  suppress_next_bookmark <- FALSE
  has_user_submitted <- FALSE

  cancel_set_ui <- NULL
  if (restore_ui) {
    cancel_set_ui <- shiny::observe(label = "set_ui", {
      is_replaying_ui <<- TRUE
      suppress_next_bookmark <<- TRUE
      client_set_ui(client, id = id)
      cancel_set_ui$destroy()
      session$onFlushed(
        function() {
          is_replaying_ui <<- FALSE
        },
        once = TRUE
      )
    })
  }

  # Restore
  cancel_on_restore_client <-
    session$onRestore(function(state) {
      client_state <- state$values[[id]]
      if (is.null(client_state)) {
        return()
      }

      if (!is.null(cancel_set_ui)) {
        cancel_set_ui$destroy()
      }
      client_set_state(client, client_state)

      is_replaying_ui <<- TRUE
      suppress_next_bookmark <<- TRUE
      # Set the UI: prefer the browser's displayed snapshot, fall back to turns.
      shiny::withReactiveDomain(session, {
        bookmark_restore_ui(state, client, id, session)
      })
      session$onFlushed(
        function() {
          is_replaying_ui <<- FALSE
        },
        once = TRUE
      )
    })

  cancel_on_restore_greeting <-
    session$onRestore(function(state) {
      g <- state$values[[paste0(id, "_greeting")]]
      if (!is.null(g) && is.character(g$content)) {
        shiny::withReactiveDomain(session, {
          chat_set_greeting(id, g$content, session = session)
        })
      }
    })

  # Update URL
  cancel_bookmark_on_input <-
    if (bookmark_on_input) {
      shiny::observeEvent(
        session$input[[id_user_input]],
        label = "on_user_submit_do_bookmark",
        {
          # On user submit
          has_user_submitted <<- TRUE
          session$doBookmark()
        }
      )
    } else {
      NULL
    }

  # Track real user submissions even when bookmark_on_input is disabled: it's
  # what cancel_bookmark_on_response uses to tell a genuine response apart
  # from the browser's echo of messages we populated ourselves at startup.
  cancel_mark_user_submitted <-
    if (bookmark_on_response && !bookmark_on_input) {
      shiny::observeEvent(
        session$input[[id_user_input]],
        label = "mark_user_submitted",
        {
          has_user_submitted <<- TRUE
        }
      )
    } else {
      NULL
    }

  # Bookmark once the browser has echoed a settled transcript ending in an
  # assistant reply. This must NOT fire on stream completion: the client reports
  # the finished assistant message in a later round trip, so bookmarking earlier
  # would persist a snapshot missing that reply (mirrors the history feature's
  # message_response_effect). It also must NOT fire on the browser's echo of
  # messages we populated ourselves (initial turn replay or restore) -- see
  # has_user_submitted's comment above.
  cancel_bookmark_on_response <-
    if (bookmark_on_response) {
      shiny::observeEvent(
        session$input[[id_messages]],
        label = "on_response_do_bookmark",
        ignoreInit = TRUE,
        {
          if (!has_user_submitted) {
            return()
          }
          if (is_replaying_ui) {
            return()
          }
          if (suppress_next_bookmark) {
            suppress_next_bookmark <<- FALSE
            return()
          }
          if (messages_end_with_assistant(get_reported_messages(session, id))) {
            session$doBookmark()
          }
        }
      )
    } else {
      NULL
    }

  cancel_update_bookmark <- NULL
  if (bookmark_on_input || bookmark_on_response) {
    cancel_update_bookmark <-
      shiny::withReactiveDomain(session$rootScope(), {
        # Update the query string when bookmarked
        shiny::onBookmarked(function(url) {
          shiny::updateQueryString(url)
        })
      })
  }

  # Return a single cancel callback that tears down all registrations
  cancel_all <- function() {
    # session$onBookmark() and shiny::onBookmarked() return cancel functions
    if (!is.null(cancel_on_bookmark_client)) {
      cancel_on_bookmark_client()
    }
    if (!is.null(cancel_on_restore_client)) {
      cancel_on_restore_client()
    }
    if (!is.null(cancel_on_bookmark_greeting)) {
      cancel_on_bookmark_greeting()
    }
    if (!is.null(cancel_on_restore_greeting)) {
      cancel_on_restore_greeting()
    }
    if (!is.null(cancel_update_bookmark)) {
      cancel_update_bookmark()
    }
    # observeEvent() returns an Observer with $destroy()
    if (!is.null(cancel_bookmark_on_input)) {
      cancel_bookmark_on_input$destroy()
    }
    if (!is.null(cancel_mark_user_submitted)) {
      cancel_mark_user_submitted$destroy()
    }
    if (!is.null(cancel_bookmark_on_response)) {
      cancel_bookmark_on_response$destroy()
    }
  }

  invisible(cancel_all)
}

# Capture the browser's displayed-message snapshot into the bookmark state so
# restore can reproduce the exact UI. Server store only: the base64 payload
# would bloat a URL bookmark, and URL/old bookmarks fall back to turn-derived UI.
bookmark_save_ui <- function(state, session, id) {
  if (!is_server_bookmarkstore()) {
    return(invisible())
  }
  state$values[[paste0(id, "_ui")]] <- encode_ui_snapshot(
    get_reported_messages(session, id)
  )
  invisible()
}

bookmark_restore_ui <- function(state, client, id, session) {
  ui_snapshot <- decode_ui_snapshot(state$values[[paste0(id, "_ui")]])
  restore_chat_ui(client, id, ui_snapshot, session)
  invisible()
}

messages_end_with_assistant <- function(messages) {
  if (length(messages) == 0) {
    return(FALSE)
  }
  identical(messages[[length(messages)]]$role, "assistant")
}

GREETING_STATE_KEY <- ".greeting-state"

get_session_greeting_state <- function(session, id) {
  get_session_chat_bookmark_info(session, paste0(id, GREETING_STATE_KEY))
}

set_session_greeting_state <- function(session, id, value) {
  set_session_chat_bookmark_info(
    session,
    paste0(id, GREETING_STATE_KEY),
    value = value
  )
}

has_session_chat_bookmark_info <- function(session, id) {
  return(!is.null(get_session_chat_bookmark_info(session, id)))
}
get_session_chat_bookmark_info <- function(session, id) {
  if (is.null(session)) {
    return(NULL)
  }

  info <- session$userData$shinychat
  key <- session$ns(id)
  return(info[[key]])
}
set_session_chat_bookmark_info <- function(session, id, value) {
  if (is.null(session)) {
    return(NULL)
  }

  if (is.null(session$userData$shinychat)) {
    session$userData$shinychat <- list()
  }
  session$userData$shinychat[[session$ns(id)]] <- value

  invisible(session)
}
