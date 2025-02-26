#' Add Shiny bookmarking for shinychat
#'
#' @description
#' Adds hooks to the Shiny chat given the LLM client.
#'
#' If either `update_on_input` or `update_on_response` is `TRUE`, the Shiny
#' App's bookmark will be automatically updated without showing a modal to the
#' user.
#'
#' @param id The ID of the chat element
#' @param client The \pkg{ellmer} LLM chat client.
#' @param ... Used for future parameter expansion.
#' @param update_on_input A logical value determines if the bookmark should be updated when the user submits a message. Default is `TRUE`.
#' @param update_on_response A logical value determines if the bookmark should be updated when the response stream completes. Default is `TRUE`.
#' @param session The Shiny session object
#' @returns Returns nothing (\code{invisible(NULL)}).
#'
#' @examplesIf interactive()
#' library(shiny)
#' library(bslib)
#' library(shinychat)
#'
#' ui <- page_fillable(
#'   chat_ui("chat", fill = TRUE)
#' )
#'
#' server <- function(input, output, session) {
#'   chat_client <- ellmer::chat_ollama(
#'     system_prompt = "Important: Always respond in a limerick",
#'     model = "qwen2.5-coder:1.5b",
#'     echo = TRUE
#'   )
#'   # Update bookmark to chat on user submission and completed response
#'   chat_bookmark("chat", chat_client)
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
chat_bookmark <- function(
  id,
  client,
  ...,
  update_on_input = TRUE,
  update_on_response = TRUE,
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
  update_on_input <- rlang::is_true(update_on_input)
  update_on_response <- rlang::is_true(update_on_response)

  if (is.null(session)) {
    rlang::abort(
      "A `session` must be provided. Be sure to call `chat_bookmark()` where a session context is available."
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
  cancel_on_bookmark <- session$onBookmark(function(state) {
    if (id %in% names(state$values)) {
      rlang::abort(
        paste0(
          "Bookmark value with id (`\"",
          id,
          "\"`)) already exists. Please remove it or use a different id."
        )
      )
    }

    turns <- client$get_turns()
    if (length(turns) == 0) return()

    if (shiny::getShinyOption("bookmarkStore", "server") == "server") {
      # `.rds` file will be used for serialization. Saving client as is
      state$values[[id]] <- client
    } else {
      # URL will be destination for serialization
      turns_list <- lapply(turns, function(turn) {
        list(
          role = turn@role,
          # Convert everything to a single markdown string (including images!)
          contents = ellmer::contents_markdown(turn),
          tokens = turn@tokens
        )
      })
      state$values[[id]] <- turns_list
    }
  })

  # Restore
  cancel_on_restore <- session$onRestore(function(state) {
    turns_obj <- state$values[[id]]
    if (is.null(turns_obj)) return()

    if (shiny::getShinyOption("bookmarkStore", "server") == "server") {
      # Restore client from `.rds` file
      restored_client <- turns_obj

      # Go through each property trying to set it to the other?
      client$set_turns(restored_client$get_turns())
    } else {
      # Restore from URL

      turn_list <-
        if (inherits(turns_obj, "data.frame")) {
          # Restore url jsonlite::fromJSON() object that has been _simplified_ into a data.frame()
          turns_df <- turns_obj
          if (nrow(turns_df) == 0) return()

          # Turn a data.frame into a list of row information, where the row info is a named lists
          # Similar to `purrr::pmap(turns_df, list)`
          unname(rlang::exec(Map, !!!as.list(turns_df), list))
        } else {
          turns_obj
        }

      # Verify turn fields are available
      Map(
        turn_info = turn_list,
        i = seq_along(turn_list),
        f = function(turn_info, i) {
          turn_info_names <- names(turn_info)
          for (col_name in c("role", "contents", "tokens")) {
            if (!(col_name %in% turn_info_names)) {
              rlang::abort(
                paste0(
                  "Restored turn ",
                  i,
                  "/",
                  length(turn_list),
                  " does not have a '",
                  col_name,
                  "' field."
                )
              )
            }
          }
        }
      )

      # Upgrade
      # Note: Character `contents=` values will be auto upgraded by ellmer to a `ellmer::ContentText` objects
      turns <- lapply(turn_list, function(turn_info) {
        rlang::exec(ellmer::Turn, !!!turn_info)
      })

      # Set the client
      client$set_turns(turns)
    }

    # Set the UI
    # TODO-barret-future; In shinychat, make this a single/internal custom message call to send all the messages at once (and then scroll)
    lapply(client$get_turns(), function(turn) {
      chat_append(
        id,
        # Use `contents_markdown()` as it handles image serialization
        ellmer::contents_markdown(turn),
        #  turn_info$contents,
        role = turn@role
      )
    })
  })

  # Update URL
  cancel_update_on_input <-
    if (update_on_input) {
      observeEvent(session$input[[id_user_input]], {
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
    enable = update_on_response
  )

  cancel_update_bookmark <- NULL
  if (update_on_input || update_on_response) {
    cancel_update_bookmark <-
      # Update the query string when bookmarked
      shiny::onBookmarked(function(url) {
        shiny::updateQueryString(url)
      })
  }

  # Set callbacks to cancel if `chat_bookmark(id, client)` is called again with the same id
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

  # Store callbacks to cancel in case a new call to `chat_bookmark(id, client)` is called with the same id
  set_session_chat_bookmark_info(
    session,
    id,
    value = list(
      callbacks_to_cancel = c(
        cancel_on_bookmark,
        cancel_on_restore,
        cancel_update_on_input,
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
ON_RESPONSE_KEY <- ".on-response"
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
  init_bookmark_obj(session)
  info <- session$userData$shinychat
  key <- session$ns(id)
  return(info[[key]])
}
set_session_chat_bookmark_info <- function(session, id, value) {
  init_bookmark_obj(session)

  session$userData$shinychat[[session$ns(id)]] <- value

  invisible(session)
}
init_bookmark_obj <- function(session) {
  if (is.null(session$userData$shinychat)) {
    session$userData$shinychat <- list()
  }

  invisible(session)
}
