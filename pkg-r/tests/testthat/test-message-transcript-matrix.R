matrix_path <- testthat::test_path(
  "fixtures",
  "message-transcript-matrix.json"
)
matrix <- jsonlite::fromJSON(matrix_path, simplifyVector = FALSE)

run_operations <- function(operations) {
  transcript <- ChatTranscript$new()

  for (operation in operations) {
    if (identical(operation$type, "message")) {
      transcript$append(operation)
    } else if (identical(operation$type, "stream_start")) {
      transcript$start(operation)
    } else if (identical(operation$type, "stream_chunk")) {
      transcript$chunk(
        operation$content,
        operation$content_type,
        html_deps = operation$html_deps,
        operation = operation$operation
      )
    } else if (identical(operation$type, "stream_end")) {
      transcript$settle()
    } else if (identical(operation$type, "clear")) {
      transcript$clear()
    } else if (identical(operation$type, "replay")) {
      transcript$replace(operation$messages)
    } else {
      rlang::abort(paste("Unknown matrix operation:", operation$type))
    }
  }

  transcript$read()
}

for (matrix_case in matrix) {
  local({
    case <- matrix_case
    test_that(paste("message transcript matrix:", case$name), {
      if (!is.null(case$error)) {
        expect_error(run_operations(case$operations), case$error, fixed = TRUE)
      } else {
        expect_identical(run_operations(case$operations), case$expected)
      }
    })
  })
}
