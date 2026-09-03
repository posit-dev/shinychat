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
#' Note: The `client`'s chat state and the greeting content are both
#' saved/restored automatically. If the `client`'s state doesn't properly
#' capture the chat's UI (i.e., a transformation is applied in-between
#' receiving and displaying the message), you may need to implement your own
#' `session$onRestore()` (and possibly `session$onBookmark`) handler to restore
#' any additional state.
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
  to_exclude <- setdiff(
    paste0(
      id,
      c(
        "_user_input",
        "_cancel",
        "_slash_command",
        "_greeting_requested",
        "_greeting_dismissed"
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
    })

  cancel_on_bookmark_greeting <-
    session$onBookmark(function(state) {
      g <- get_session_greeting_state(session, id)
      if (!is.null(g) && is.character(g$content) && nzchar(g$content)) {
        state$values[[paste0(id, "_greeting")]] <- g
      }
    })

  cancel_set_ui <- NULL
  if (restore_ui) {
    cancel_set_ui <- shiny::observe(label = "set_ui", {
      client_set_ui(client, id = id)
      cancel_set_ui$destroy()
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

      # Set the UI
      shiny::withReactiveDomain(session, {
        client_set_ui(client, id = id)
      })
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
          session$doBookmark()
        }
      )
    } else {
      NULL
    }

  # Enable (or disable) session auto bookmarking if at least one chat wants it
  set_session_bookmark_on_response(
    session,
    id,
    enable = bookmark_on_response
  )

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
    if (!is.null(cancel_bookmark_on_input)) cancel_bookmark_on_input$destroy()
  }

  invisible(cancel_all)
}

# Method currently hooked into `chat_append_stream()` and `markdown_stream()`
# When the incoming stream ends, possibly update the URL given the `id`
chat_update_bookmark <- function(
  id,
  stream_promise,
  session = shiny::getDefaultReactiveDomain()
) {
  if (!has_session_bookmark_on_response(session, id)) {
    # No auto bookmark set. Return early!
    return(stream_promise)
  }

  # Bookmark has been flagged for `id`.
  # When the stream ends, update the URL.
  prom <-
    promises::then(stream_promise, function(stream) {
      # Force a bookmark update when the stream ends!
      shiny::isolate(session$doBookmark())
    })

  return(prom)
}

# These methods exist to set flags within the session.
# These flags will determine if the session should be bookmarked when a response has completed.
# `chat_update_bookmark()` will check if the flag is set and update the URL if it is.
ON_RESPONSE_KEY <- ".bookmark-on-response"
has_session_bookmark_on_response <- function(session, id) {
  has_session_chat_bookmark_info(
    session,
    paste0(id, ON_RESPONSE_KEY)
  )
}
set_session_bookmark_on_response <- function(session, id, enable) {
  set_session_chat_bookmark_info(
    session,
    paste0(id, ON_RESPONSE_KEY),
    value = if (enable) TRUE else NULL
  )
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
