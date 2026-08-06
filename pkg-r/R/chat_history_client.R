get_turns_recorded <- function(client) {
  lapply(client$get_turns(), ellmer::contents_record)
}

set_turns_recorded <- function(client, recorded_turns) {
  replayed <- lapply(
    recorded_turns,
    function(recorded) {
      ellmer::contents_replay(
        normalize_recorded_object(recorded),
        tools = client$get_tools()
      )
    }
  )
  client$set_turns(replayed)
}

# FileConversationStore persists recorded turns via jsonlite::toJSON() and
# reads them back with jsonlite::fromJSON(simplifyVector = FALSE), which
# doesn't round-trip R types faithfully:
#  - a whole-number JSON value (the recorded object's `version = 1`) decodes
#    as an integer rather than a double, and ellmer::check_recorded()
#    compares with identical(recorded$version, 1) -- identical(1L, 1) is
#    FALSE, so replay always errors with "Unsupported version 1".
#  - a JSON array decodes as an R list even when the original prop was an
#    atomic vector (e.g. AssistantTurn@tokens, a numeric triple). ellmer's S7
#    validator then rejects it: "@tokens must be <integer> or <double>, not
#    <list>".
# Recurse through the recorded-object tree (turn -> contents -> nested
# contents) fixing both before replay, regardless of which layer introduced
# the mismatch.
normalize_recorded_object <- function(x) {
  if (!is.list(x)) {
    return(x)
  }
  if (all(c("version", "class", "props") %in% names(x))) {
    x$version <- as.double(x$version)
    x$props <- lapply(x$props, function(value) {
      if (looks_like_scalar_array(value)) restore_scalar_array(value) else value
    })
  }
  lapply(x, normalize_recorded_object)
}

# An unnamed list of only length-1 atomics/NULLs is what a JSON array of
# scalars (or `null`s) becomes under simplifyVector = FALSE -- as opposed to
# a list of nested recorded objects (themselves lists) or a genuine `list`-
# typed prop decoded from a JSON object (which has names).
looks_like_scalar_array <- function(x) {
  is.list(x) &&
    length(x) > 0 &&
    is.null(names(x)) &&
    all(
      vapply(
        x,
        function(el) is.null(el) || (!is.list(el) && length(el) == 1),
        logical(1)
      )
    )
}

restore_scalar_array <- function(x) {
  is_missing <- vapply(x, is.null, logical(1))
  present <- x[!is_missing]
  if (length(present) == 0) {
    return(x)
  }
  na_value <- if (any(vapply(present, is.character, logical(1)))) {
    NA_character_
  } else if (all(vapply(present, is.logical, logical(1)))) {
    NA
  } else {
    NA_real_
  }
  out <- rep(na_value, length(x))
  out[!is_missing] <- unlist(present, use.names = FALSE)
  out
}

get_client_info <- function(client) {
  provider <- client$get_provider()
  list(provider = provider@name, model = provider@model)
}

turn_fallback_markdown <- function(recorded_turn) {
  contents <- recorded_turn$props$contents
  if (!is.list(contents)) {
    return("")
  }

  texts <- vapply(
    contents,
    function(item) {
      if (grepl("ContentText$", item$class %||% "")) {
        item$props$text %||% ""
      } else {
        ""
      }
    },
    character(1)
  )

  paste0(texts, collapse = "")
}
