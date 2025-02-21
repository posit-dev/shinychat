# TODO - barret; Explore if auto_bookmark should be used to stop the url from updating automatically
# TODO - barret; Explore using session state instead of the environment!

#' Set the chat client
#'
#' @description
#' Adds hooks to the Shiny chat given the LLM client. By default, the chat set enable bookmarking.
#'
#' @param id The ID of the chat element
#' @param ... Used for future parameter expansion.
#' @param bookmark A character value determines how to handle bookmarking for the chat component. For the values to work, it requires that the App author has enabled bookmarking in their App. To enable bookmarking, you can call `shiny::enableBookmarking()` or set the parameter in `shinyApp(enableBookmarking = "url")`.
#'
#' Updating the URL:
#' * `"auto"` (default): The bookmark value will be updated when the chat client is done responding.
#' * `"manual"`: The bookmark value will only update when `session$doBookmark()` is called by the App author.
### * `"none"`: The bookmark value will not be updated for any change in the chat client.
#'
#' Restoring from a bookmark:
#' * `"auto"` (default) and `"manual"`: The chat client will be restored if  will be restored from the URL when the chat client is done responding."`
### * `"none"`: The bookmark value will not be updated for any change in the chat client.
#'
#' A warning will be issued if the bookmarking feature is not enabled.
#'
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
#'   # Let the UI know about the client
#'   set_chat_client("chat", chat_client, bookmark = "auto")
#'
#'   observeEvent(input$chat_user_input, {
#'     stream <- chat_client$stream_async(input$chat_user_input)
#'     chat_append("chat", stream)
#'   })
#' }
#'
#' # Enable bookmarking!
#' shinyApp(ui, server, enableBookmarking = "url")
#' @export
set_chat_client <- function(
  id,
  client,
  ...,
  bookmark = c("auto", "manual"), # If more parameters are added, a third value of `"none"` can be used
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
  if (is.null(session)) {
    rlang::abort(
      "A `session` must be provided. Be sure to call `set_chat_client()` where a session context is available."
    )
  }

  # if (isTRUE(bookmark)) {
  set_chat_client_bookmark(
    id,
    client,
    auto_update = match.arg(bookmark, several.ok = FALSE) == "auto",
    session = session
  )

  # Don't return anything, even by chance
  invisible(NULL)
}

bookmark_domains <- list2env(list())

#' @importFrom rlang %||%
set_chat_client_bookmark <- function(
  id,
  client,
  ...,
  auto_update = TRUE,
  session = getDefaultReactiveDomain()
) {
  rlang::check_dots_empty()

  stopifnot(is.character(id) && length(id) == 1)
  session_client_hash <- paste0(domain_token(session), "-", session$ns(id))

  # Verify bookmark store is not "none"
  bookmarkStore <- shiny::getShinyOption("bookmarkStore", "none")
  if (bookmarkStore == "none") {
    rlang::abort(
      paste0(
        "Error: Shiny bookmarking is not enabled. ",
        "Please enable bookmarking in your Shiny app either by calling ",
        "`shiny::enableBookmarking()` or by setting the parameter in ",
        "`shiny::shinyApp(enableBookmarking = \"url\")`"
      )
    )
  }

  excluded_names <- session$getBookmarkExclude()
  ns_user_input <- paste0(id, "_user_input")
  if (!(ns_user_input %in% excluded_names)) {
    session$setBookmarkExclude(c(excluded_names, ns_user_input))
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

    turns_list <- lapply(turns, function(turn) {
      list(
        role = turn@role,
        # Convert everything to a single markdown string (including images!)
        contents = ellmer::contents_markdown(turn),
        tokens = turn@tokens
      )
    })
    state$values[[id]] <- turns_list
  })

  # Restore
  cancel_on_restore <- session$onRestore(function(state) {
    turns_obj <- state$values[[id]]
    if (is.null(turns_obj)) return()

    turn_list <-
      if (inherits(turns_obj, "data.frame")) {
        # Restore url jsonlite::fromJSON() object that has been _simplified_ into a data.frame()
        turns_df <- turns_obj
        if (nrow(turns_df) == 0) return()

        # Turn a data.frame into a list of row information, where the row info is a named lists
        # Similar to `purrr::pmap(turns_df, list)`
        unname(rlang::exec(Map, !!!as.list(turns_df), list))
      } else {
        # Restore `enableBookmarking("server")` object which is not _simplified_ by `jsonlite::fromJSON()`
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
            # TODO-barret-q; Should this instead be a warning and then remove the turns from this point on?
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
    # Set the UI
    # TODO-barret-future; In shinychat, make this a single/internal custom message call to send all the messages at once (and then scroll)
    lapply(turn_list, function(turn_info) {
      chat_append(
        id,
        turn_info$contents,
        role = turn_info$role
      )
    })
  })

  # Update URL
  # Only perform once per session (independent of chat `id`)
  if (auto_update && !has_session_auto_bookmark(session)) {
    # Enable session auto bookmarking if at least one chat wants it
    set_session_auto_bookmark(session, TRUE)
    # Clean up domain info in bookmark_domains
    session$onSessionEnded(function() {
      set_session_auto_bookmark(session, NULL)
    })

    # Update the query string when bookmarked
    shiny::onBookmarked(function(url) {
      shiny::updateQueryString(url)
    })
  }

  # Only allow for bookmarks for each chat once. Last bookmark method would win if all values were to be computed.
  # Remove previous `on*()` methods under same hash (.. odd author behavior)
  previous_info <- get_bookmark_info(session_client_hash)
  if (!is.null(previous_info)) {
    for (cancel_session_registration in previous_info$callbacks_to_cancel) {
      try({
        cancel_session_registration()
      })
    }
  }

  # Set callbacks to cancel if `set_chat_client(id, client)` is called again with the same id
  set_bookmark_info(
    session_client_hash,
    list(
      callbacks_to_cancel = c(
        cancel_on_bookmark,
        cancel_on_restore
      )
    )
  )
  # Cleanup bookmark environment when session ends
  session$onSessionEnded(function() {
    set_bookmark_info(session_client_hash, NULL)
  })
}

chat_update_bookmark <- function(
  id,
  stream_promise,
  session = shiny::getDefaultReactiveDomain()
) {
  if (!has_session_auto_bookmark(session)) {
    # No auto bookmark set. Return early!
    return(stream_promise)
  }

  # Bookmark has been flagged for `id`
  # When the stream ends, update the URL!
  promises::then(stream_promise, function(stream) {
    # Force a bookmark update when the stream ends!
    session$doBookmark()
  })
}


has_session_auto_bookmark <- function(session) {
  has_bookmark_info(domain_token(session))
}
set_session_auto_bookmark <- function(session, value) {
  set_bookmark_info(domain_token(session), value)
}
get_session_auto_bookmark <- function(session) {
  get_bookmark_info(domain_token(session))
}

has_bookmark_info <- function(hash) {
  !is.null(bookmark_domains[[hash]])
}
set_bookmark_info <- function(hash, value) {
  bookmark_domains[[hash]] <- value
}
get_bookmark_info <- function(hash) {
  bookmark_domains[[hash]]
}


domain_token <- function(domain = shiny::getDefaultReactiveDomain()) {
  if (is.null(domain)) {
    return("global")
  } else {
    return(domain$token)
  }
}
