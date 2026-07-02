TITLE_SYSTEM_PROMPT <- paste(
  "You title chat conversations.",
  "Reply with ONLY a title for the conversation excerpt the user provides:",
  "at most 6 words, no quotes, no trailing punctuation."
)
MAX_TITLE_LEN <- 80L
MAX_FALLBACK_LEN <- 50L

fallback_title <- function(recorded_turns) {
  for (turn in recorded_turns) {
    if (!grepl("UserTurn$", turn$class %||% "")) {
      next
    }

    text <- turn_fallback_markdown(turn)
    text <- trimws(text)
    if (!nzchar(text)) {
      next
    }

    if (nchar(text) <= MAX_FALLBACK_LEN) {
      return(text)
    }
    return(paste0(substr(text, 1, MAX_FALLBACK_LEN - 3L), "..."))
  }
  "New chat"
}

generate_title <- function(title_fn, client, recorded_turns) {
  if (!is.null(title_fn)) {
    return(
      promises::promise_resolve(
        tryCatch(
          {
            result <- title_fn(recorded_turns)
            normalize_title(result)
          },
          error = function(e) {
            rlang::warn("Title generation failed", parent = e)
            NULL
          }
        )
      )
    )
  }

  tryCatch(
    {
      titler <- client$clone()
      titler$set_turns(list())
      tryCatch(titler$set_tools(list()), error = function(e) NULL)
      titler$set_system_prompt(TITLE_SYSTEM_PROMPT)

      excerpt_turns <- head(recorded_turns, 2)
      excerpt <- vapply(
        excerpt_turns,
        function(t) {
          role <- sub("^ellmer::", "", sub("Turn$", "", t$class %||% "unknown"))
          text <- substr(turn_fallback_markdown(t), 1, 500)
          paste0(tolower(role), ": ", text)
        },
        character(1)
      )
      excerpt_text <- paste(excerpt, collapse = "\n\n")

      titler$chat_async(excerpt_text, echo = "none") |>
        promises::then(normalize_title) |>
        promises::catch(function(e) {
          rlang::warn("Title generation failed", parent = e)
          NULL
        })
    },
    error = function(e) {
      rlang::warn("Title generation failed", parent = e)
      promises::promise_resolve(NULL)
    }
  )
}

normalize_title <- function(title) {
  if (is.null(title) || !nzchar(trimws(as.character(title)))) {
    return(NULL)
  }
  title <- paste(
    strsplit(trimws(as.character(title)), "\\s+")[[1]],
    collapse = " "
  )
  if (nchar(title) > MAX_TITLE_LEN) {
    title <- paste0(substr(title, 1, MAX_TITLE_LEN - 3L), "...")
  }
  title
}
