ChatTranscript <- R6::R6Class(
  "ChatTranscript",
  public = list(
    initialize = function() {
      private$messages <- list()
      private$active_stream <- NULL
      private$active_stream_id <- NULL
    },

    read = function() {
      copy_messages(private$messages)
    },

    append = function(message, send = NULL) {
      if (!is.null(private$active_stream)) {
        rlang::abort(
          "Cannot append a complete message while a stream is active"
        )
      }
      next_message <- normalize_transcript_message(message)
      next_messages <- c(copy_messages(private$messages), list(next_message))

      private$transition(next_messages, NULL, NULL, send)
    },

    start = function(message, stream_id, send = NULL) {
      if (!is.null(private$active_stream)) {
        rlang::abort("Cannot start a stream while another stream is active")
      }
      next_active_stream <- normalize_transcript_message(message)

      private$transition(
        copy_messages(private$messages),
        next_active_stream,
        stream_id,
        send
      )
    },

    chunk = function(
      content,
      content_type,
      stream_id,
      html_deps = NULL,
      operation = "append",
      send = NULL
    ) {
      if (is.null(private$active_stream)) {
        rlang::abort("Cannot apply a stream chunk without an active stream")
      }
      private$assert_active_stream(stream_id)
      if (!operation %in% c("append", "replace")) {
        rlang::abort("`operation` must be either \"append\" or \"replace\".")
      }

      segment <- normalize_transcript_segment(
        list(
          content = content,
          content_type = content_type
        )
      )
      dependencies <- normalize_transcript_dependencies(html_deps)
      next_active_stream <- copy_message(private$active_stream)

      if (identical(operation, "replace")) {
        next_active_stream$segments <- list(segment)
        next_active_stream$htmlDeps <- NULL
        next_active_stream <- set_optional_field(
          next_active_stream,
          "htmlDeps",
          dependencies
        )
      } else {
        last_segment <- length(next_active_stream$segments)
        if (
          last_segment > 0 &&
            identical(
              next_active_stream$segments[[last_segment]]$content_type,
              segment$content_type
            )
        ) {
          next_active_stream$segments[[last_segment]]$content <- paste0(
            next_active_stream$segments[[last_segment]]$content,
            segment$content
          )
        } else {
          next_active_stream$segments <- c(
            next_active_stream$segments,
            list(segment)
          )
        }
        next_active_stream <- set_optional_field(
          next_active_stream,
          "htmlDeps",
          c(next_active_stream$htmlDeps %||% list(), dependencies)
        )
      }

      private$transition(
        copy_messages(private$messages),
        next_active_stream,
        stream_id,
        send
      )
    },

    settle = function(stream_id, send = NULL) {
      if (is.null(private$active_stream)) {
        rlang::abort("Cannot end a stream without an active stream")
      }
      private$assert_active_stream(stream_id)
      next_messages <- c(
        copy_messages(private$messages),
        list(copy_message(private$active_stream))
      )

      private$transition(next_messages, NULL, NULL, send)
    },

    abort = function(stream_id) {
      if (!identical(private$active_stream_id, stream_id)) {
        return(invisible(NULL))
      }
      private$active_stream <- NULL
      private$active_stream_id <- NULL
      invisible(NULL)
    },

    is_active = function(stream_id) {
      !is.null(private$active_stream) &&
        identical(private$active_stream_id, stream_id)
    },

    clear = function(send = NULL) {
      private$transition(list(), NULL, NULL, send)
    },

    replace = function(messages, send = NULL) {
      next_messages <- normalize_transcript_messages(messages)

      private$transition(next_messages, NULL, NULL, send)
    }
  ),
  private = list(
    messages = NULL,
    active_stream = NULL,
    active_stream_id = NULL,

    assert_active_stream = function(stream_id) {
      if (!identical(private$active_stream_id, stream_id)) {
        rlang::abort("Cannot write to a stream that is not active")
      }
    },

    transition = function(
      next_messages,
      next_active_stream,
      next_active_stream_id,
      send
    ) {
      validate_transcript_state(next_messages, next_active_stream)
      validate_send_callback(send)
      if (!is.null(send)) {
        send()
      }
      private$messages <- next_messages
      private$active_stream <- next_active_stream
      private$active_stream_id <- next_active_stream_id

      invisible(NULL)
    }
  )
)

get_chat_transcript <- function(session, id) {
  key <- paste0(id, ".transcript")
  transcript <- get_session_chat_bookmark_info(session, key)
  if (is.null(transcript)) {
    transcript <- ChatTranscript$new()
    set_session_chat_bookmark_info(session, key, transcript)
  }
  transcript
}

normalize_transcript_messages <- function(messages) {
  if (!is.list(messages)) {
    rlang::abort("Transcript messages must be a list.")
  }
  lapply(messages, normalize_transcript_message)
}

normalize_transcript_message <- function(message) {
  if (!is.list(message)) {
    rlang::abort("A transcript message must be a list.")
  }

  role <- normalize_transcript_string(message$role, "`role`")
  segments <- message$segments
  if (is.null(segments) || !is.list(segments)) {
    rlang::abort("A transcript message must contain a list of `segments`.")
  }

  normalized <- list(
    role = role,
    segments = lapply(segments, normalize_transcript_segment)
  )
  normalized <- set_optional_field(
    normalized,
    "attachments",
    normalize_transcript_attachments(message$attachments)
  )
  normalized <- set_optional_field(
    normalized,
    "htmlDeps",
    normalize_transcript_dependencies(message$htmlDeps)
  )
  normalized
}

normalize_transcript_segment <- function(segment) {
  if (!is.list(segment)) {
    rlang::abort("A transcript segment must be a list.")
  }

  list(
    content = normalize_transcript_string(segment$content, "`content`"),
    content_type = normalize_transcript_string(
      segment$content_type,
      "`content_type`"
    )
  )
}

normalize_transcript_string <- function(value, field) {
  if (!is.character(value) || length(value) != 1L || is.na(value)) {
    rlang::abort(paste0(field, " must be a single string."))
  }
  value
}

normalize_transcript_attachments <- function(attachments) {
  normalize_transcript_collection(attachments, "`attachments`")
}

normalize_transcript_dependencies <- function(html_deps) {
  normalize_transcript_collection(html_deps, "`html_deps`")
}

normalize_transcript_collection <- function(value, field) {
  if (is.null(value) || length(value) == 0) {
    return(NULL)
  }
  if (!is.list(value)) {
    rlang::abort(paste0(field, " must be a list."))
  }
  copy_value(value)
}

validate_transcript_state <- function(messages, active_stream) {
  normalize_transcript_messages(messages)
  if (!is.null(active_stream)) {
    normalize_transcript_message(active_stream)
  }
  invisible(NULL)
}

validate_send_callback <- function(send) {
  if (!is.null(send) && !is.function(send)) {
    rlang::abort("`send` must be a function or NULL.")
  }
  invisible(NULL)
}

set_optional_field <- function(message, field, value) {
  if (!is.null(value) && length(value) > 0) {
    message[[field]] <- value
  }
  message
}

copy_messages <- function(messages) {
  lapply(messages, copy_message)
}

copy_message <- function(message) {
  if (is.null(message)) {
    return(NULL)
  }
  copy_value(message)
}

copy_value <- function(value) {
  if (!is.list(value)) {
    return(value)
  }
  lapply(value, copy_value)
}
