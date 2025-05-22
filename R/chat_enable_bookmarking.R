#' Add Shiny bookmarking for shinychat
#'
#' @description
#' Adds hooks to the Shiny chat given the LLM client.
#'
#' If either `bookmark_on_input` or `bookmark_on_response` is `TRUE`, the Shiny
#' App's bookmark will be automatically updated without showing a modal to the
#' user.
#'
#' @param id The ID of the chat element
#' @param client The \pkg{ellmer} LLM chat client.
#' @param ... Used for future parameter expansion.
#' @param bookmark_on_input A logical value determines if the bookmark should be updated when the user submits a message. Default is `TRUE`.
#' @param bookmark_on_response A logical value determines if the bookmark should be updated when the response stream completes. Default is `TRUE`.
#' @param session The Shiny session object
#' @returns Returns nothing (\code{invisible(NULL)}).
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
#'   chat_enable_bookmarking("chat", chat_client)
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
chat_enable_bookmarking <- function(
  id,
  client,
  ...,
  bookmark_on_input = TRUE,
  bookmark_on_response = TRUE,
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
      "A `session` must be provided. Be sure to call `chat_enable_bookmarking()` where a session context is available."
    )
  }

  # Verify bookmark store is not disabled. Bookmark options: "disable", "url", "server"
  bookmark_store <- shiny::getShinyOption("bookmarkStore", "disable")
  # TODO: Q - I feel this should be removed. Since we are only adding hooks, it doesn't matter if it's enabled or not. If the user diables chat, it would be very annoying to receive error messages for code they may not own.
  if (bookmark_store == "disable") {
    rlang::abort(
      paste0(
        "Error: Shiny bookmarking is not enabled. ",
        "Please enable bookmarking in your Shiny app either by calling ",
        "`shiny::enableBookmarking(\"server\")` or by setting the parameter in ",
        "`shiny::shinyApp(enableBookmarking = \"server\")`"
      )
    )
  }

  # Exclude works with bookmark names
  excluded_names <- session$getBookmarkExclude()
  id_user_input <- paste0(id, "_user_input")
  if (!(id_user_input %in% excluded_names)) {
    session$setBookmarkExclude(c(excluded_names, id_user_input))
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

  # Restore
  cancel_on_restore_client <-
    session$onRestore(function(state) {
      client_state <- state$values[[id]]
      if (is.null(client_state)) return()

      client_set_state(client, client_state)

      # Set the UI
      chat_clear(id)
      client_set_ui(client, id = id)
    })

  # Update URL
  cancel_bookmark_on_input <-
    if (bookmark_on_input) {
      shiny::observeEvent(session$input[[id_user_input]], {
        # On user submit
        session$doBookmark()
      })
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
      # Update the query string when bookmarked
      shiny::onBookmarked(function(url) {
        shiny::updateQueryString(url)
      })
  }

  # Set callbacks to cancel if `chat_enable_bookmarking(id, client)` is called again with the same id
  # Only allow for bookmarks for each chat once. Last bookmark method would win if all values were to be computed.
  # Remove previous `on*()` methods under same hash (.. odd author behavior)
  previous_info <- get_session_chat_bookmark_info(session, id)
  if (!is.null(previous_info)) {
    for (cancel_session_registration in previous_info$callbacks_to_cancel) {
      try({
        cancel_session_registration()
      })
    }
  }

  # Store callbacks to cancel in case a new call to `chat_enable_bookmarking(id, client)` is called with the same id
  set_session_chat_bookmark_info(
    session,
    id,
    value = list(
      callbacks_to_cancel = c(
        cancel_on_bookmark_client,
        cancel_on_restore_client,
        cancel_bookmark_on_input,
        cancel_update_bookmark
      )
    )
  )

  # Don't return anything, even by chance
  invisible(NULL)
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
      session$doBookmark()
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


has_session_chat_bookmark_info <- function(session, id) {
  return(!is.null(get_session_chat_bookmark_info(session, id)))
}
get_session_chat_bookmark_info <- function(session, id) {
  info <- session$userData$shinychat
  key <- session$ns(id)
  return(info[[key]])
}
set_session_chat_bookmark_info <- function(session, id, value) {
  if (is.null(session$userData$shinychat)) {
    session$userData$shinychat <- list()
  }
  session$userData$shinychat[[session$ns(id)]] <- value

  invisible(session)
}
