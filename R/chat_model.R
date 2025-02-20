# # Default call
# shinychat::set_chat_model("chat", chat_session)
# # Not `set_model` as there's no object context

# # Error if `shiny::getShinyOption("bookmarkStore")` is `"none"`.
# #   * Provide example in docs on how to exclude some input in the example app.
# #     # Escape bookmarking all inputs
# #     shiny::setBookmarkExclude("big_object")
# # Error if model is not a ellmer model. Provide error message on submitting GH issue for extension

# # Sets onBookmark callback
# # Sets onRestore callback
# # Updates the url on user input / server output change

#' @export
set_chat_model <- function(
  id,
  model,
  ...,
  bookmark = TRUE
) {
  rlang::check_dots_empty()
  stopifnot(is.character(id) && length(id) == 1)

  rlang::check_installed("ellmer")
  if (!(inherits(model, "R6") && inherits(model, "Chat"))) {
    rlang::abort(
      "`model` must be an `ellmer::Chat()` object. If you would like to have {shinychat} support your own package, please submit an Issue at https://github.com/posit-dev/shinychat"
    )
  }

  if (isTRUE(bookmark)) {
    set_chat_model_bookmark(id, model)
  }

  return()
}

bookmark_domains <- list2env(list())

#' @importFrom rlang %||%
set_chat_model_bookmark <- function(id, model) {
  domain_token_value <- domain_token()
  domain_hash <- paste0(domain_token_value, "-", id)

  str(
    list(
      domain_hash = domain_hash,
      bookmark_domains = as.list(bookmark_domains)
    )
  )

  # Only allow for bookmarks for each chat once
  if (!is.null(bookmark_domains[[domain_hash]])) {
    rlang::abort(
      "Error: A bookmark for this chat already exists. Be sure to only set the model once."
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

  # Save
  shiny::onBookmark(function(state) {
    print("shiny::onBookmark")

    # TODO-barret-q: Why isn't this value set until a response has arrived?
    if (id %in% names(state$values)) {
      rlang::abort(
        paste0(
          "Bookmark value with id (`\"",
          id,
          "\"`)) already exists. Please remove it or use a different id."
        )
      )
    }

    turns <- model$get_turns()
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
  # Might need to be `onRestored`, idk yet
  shiny::onRestore(function(state) {
    print("shiny::onRestore")

    turns_df <- state$values[[id]]
    if (is.null(turns_df)) return()
    if (nrow(turns_df) == 0) return()

    print("Restoring turns!")
    str(turns_df)

    # Turn a data.frame into a list of row information, where the row info is a named lists
    # Similar to `purrr::pmap(turns_df, list)`
    turn_list <- unname(rlang::exec(Map, !!!as.list(turns_df), list))

    str(list(turn_list = turn_list))

    # Verify turn fields available
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

    # Set the model
    model$set_turns(turns)
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
    print("Setting onBookmarked")
    shiny::onBookmarked(function(url) {
      print("onBookmarked!")
      str(url)
      shiny::updateQueryString(url)
    })
  }

  # TODO-barret on session ended, clean up domain info
}

chat_update_bookmark <- function(id, stream_promise) {
  # Capture the session from when the call was made
  session = shiny::getDefaultReactiveDomain()
  domain_token_value <- domain_token(session)

  if (is.null(bookmark_domains[[domain_token_value]])) {
    # No auto bookmark set. Return early!
    return(stream_promise)
  }

  # Bookmark has been flagged for `id`

  print("adding promise")

  promises::then(stream_promise, function(stream) {
    shiny::withReactiveDomain(session, {
      # Force a bookmark update when the stream ends!
      print("session$doBookmark()!")
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
