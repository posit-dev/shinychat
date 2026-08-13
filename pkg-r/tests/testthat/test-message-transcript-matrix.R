matrix_path <- testthat::test_path(
  "fixtures",
  "message-transcript-matrix.json"
)
matrix <- jsonlite::fromJSON(matrix_path, simplifyVector = FALSE)

send_for <- function(operation) {
  error <- operation$send_error
  if (is.null(error)) {
    return(NULL)
  }
  function() {
    rlang::abort(error)
  }
}

apply_operation <- function(transcript, operation) {
  send <- send_for(operation)
  if (identical(operation$type, "message")) {
    transcript$append(operation, send = send)
  } else if (identical(operation$type, "stream_start")) {
    transcript$start(operation, stream_id = operation$stream_id, send = send)
  } else if (identical(operation$type, "stream_chunk")) {
    transcript$chunk(
      operation$content,
      operation$content_type,
      html_deps = operation$html_deps,
      operation = operation$operation,
      stream_id = operation$stream_id,
      send = send
    )
  } else if (identical(operation$type, "stream_end")) {
    transcript$settle(stream_id = operation$stream_id, send = send)
  } else if (identical(operation$type, "stream_abort")) {
    transcript$abort(operation$stream_id)
  } else if (identical(operation$type, "clear")) {
    transcript$clear(send = send)
  } else if (identical(operation$type, "replay")) {
    transcript$replace(operation$messages, send = send)
  } else {
    rlang::abort(paste("Unknown matrix operation:", operation$type))
  }
}

run_operations <- function(transcript, operations) {
  for (operation in operations) {
    apply_operation(transcript, operation)
  }
  invisible(transcript)
}

for (matrix_case in matrix) {
  local({
    case <- matrix_case
    test_that(paste("message transcript matrix:", case$name), {
      transcript <- ChatTranscript$new()

      if (!is.null(case$error)) {
        expect_error(
          run_operations(transcript, case$operations),
          case$error,
          fixed = TRUE
        )
      } else {
        run_operations(transcript, case$operations)
      }

      expect_identical(transcript$read(), case$expected)
    })
  })
}
