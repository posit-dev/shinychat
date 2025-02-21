# TODO - barret; Explore if auto_bookmark should be used to stop the url from updating automatically

#' Set the chat client
#'
#' @description
#' Adds hooks to the Shiny chat given the LLM client. By default, the chat set enable bookmarking.
#'
#' @section Bookmarking:
#'
#' \pkg{shinychat} will not enable bookmarking by default. To enable bookmarking, you can call `shiny::enableBookmarking()` or set the parameter in `shinyApp(enableBookmarking = "url")`.
#'
#' To
#'
#' @param id The ID of the chat element
#' @param ... Used for future parameter expansion.
#' @param bookmark A logical that determines if bookmarking hooks should be added for the chat component. If `TRUE` (default), the bookmark value will be updated when the chat client is done responding. On session restore, the bookmark value will attempt to restore from the URL.
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
#'   set_chat_client("chat", chat_client, bookmark = TRUE)
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
  bookmark = TRUE,
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

  if (isTRUE(bookmark)) {
    set_chat_client_bookmark(id, client, session = session)
  }

  # Don't return anything, even by chance
  invisible(NULL)
}

bookmark_domains <- list2env(list())

#' @importFrom rlang %||%
set_chat_client_bookmark <- function(
  id,
  client,
  ...,
  session = getDefaultReactiveDomain()
) {
  rlang::check_dots_empty()

  stopifnot(is.character(id) && length(id) == 1)
  domain_token_value <- domain_token(session)
  domain_hash <- paste0(domain_token_value, "-", session$ns(id))

  # Only allow for bookmarks for each chat once
  # TODO-barret on second set chat client call, disable all reactive callbacks already registered
  if (!is.null(bookmark_domains[[domain_hash]])) {
    rlang::abort(
      "Error: A bookmark for this chat already exists. Be sure to only set the client once."
    )
  }
  bookmark_domains[[domain_hash]] <- TRUE

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

  excluded_names <- domain$getBookmarkExclude()
  ns_user_input <- paste0(id, "_user_input")
  if (!(ns_user_input %in% excluded_names)) {
    session$setBookmarkExclude(c(excluded_names, ns_user_input))
  }

  # Save
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
  session$onRestore(function(state) {
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
            # TODO-barret; Should this instead be a warning and then remove the turns from this point on?
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
    # TODO-barret; In shinychat, make this a single/internal custom message call to send all the messages at once (and then scroll)
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
  if (is.null(bookmark_domains[[domain_token_value]])) {
    bookmark_domains[[domain_token_value]] <- TRUE
    # Update the query string when bookmarked
    shiny::onBookmarked(function(url) {
      shiny::updateQueryString(url)
    })
  }

  # TODO-barret on session ended, clean up domain info in bookmark_domains
}

chat_update_bookmark <- function(
  id,
  stream_promise,
  session = shiny::getDefaultReactiveDomain()
) {
  # Capture the session from when the call was made
  domain_token_value <- domain_token(session)

  if (is.null(bookmark_domains[[domain_token_value]])) {
    # No auto bookmark set. Return early!
    return(stream_promise)
  }

  # Bookmark has been flagged for `id`
  # When the stream ends, update the URL!
  promises::then(stream_promise, function(stream) {
    shiny::withReactiveDomain(session, {
      # Force a bookmark update when the stream ends!
      session$doBookmark()
    })
  })
}

domain_token <- function(domain = shiny::getDefaultReactiveDomain()) {
  if (is.null(domain)) {
    return("global")
  } else {
    return(domain$token)
  }
}
