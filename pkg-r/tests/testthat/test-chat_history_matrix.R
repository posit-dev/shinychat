# Cross-language behavior matrix for HistoryController.
#
# Scenarios are defined once in tests/shared/history-behavior-matrix.json
# (repo root) and consumed by both this file and
# pkg-py/tests/test_history_matrix.py. R reads a vendored copy at
# fixtures/history-behavior-matrix.json because `R CMD check` builds this
# package into an isolated tarball that doesn't contain anything outside
# pkg-r/ — the vendored copy is kept in sync with the source by
# `make history-matrix-sync`, and CI fails the build if it drifts (see
# .github/workflows/verify-js-built.yaml).
#
# Only scenarios whose operation has a matching signature in both languages
# belong here (e.g. rename(conv_id, title), delete(conv_id)). Operations that
# take language-specific input shapes (e.g. on_response's turn data) aren't a
# good fit for this generic harness — see
# docs/plans/2026-07-01-chat-history-principal-review.md for scope notes.
#
# Each scenario gets its own "expect" block of plain field-equality checks
# against `ctrl$record`, plus an optional hand-written custom check (below)
# for anything that isn't a plain equality. Custom checks are ordinary code,
# not a data-driven DSL, specifically so failures are easy to trace back to a
# real assertion.

matrix <- jsonlite::fromJSON(
  test_path("fixtures", "history-behavior-matrix.json"),
  simplifyVector = FALSE
)

matrix_seed <- function(ctrl, setup) {
  turns <- setup$turns %||% 0
  if (turns > 0) {
    user_turn <- list(
      class = "ellmer::UserTurn",
      version = 1,
      props = list(
        contents = list(list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = "Hello")
        ))
      )
    )
    asst_turn <- list(
      class = "ellmer::AssistantTurn",
      version = 1,
      props = list(
        contents = list(list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = "Hi there")
        ))
      )
    )
    ctrl$on_response(list(user_turn, asst_turn))
  }
  stopifnot(!is.null(ctrl$record))
  ctrl$record$id
}

matrix_resolve_args <- function(args, active_id) {
  lapply(args, function(a) if (identical(a, "$active_id")) active_id else a)
}

check_rename_updates_title_and_marks_user_source <- function(ctrl, ctx) {
  expect_equal(ctrl$record$updated_at, ctx$before_updated_at)
}

check_delete_active_conversation_clears_controller_record <- function(
  ctrl,
  ctx
) {
  expect_null(ctrl$record)
  remaining <- ctx$store$list("matrix-scope")
  remaining_ids <- vapply(remaining, `[[`, character(1L), "id")
  expect_false(ctx$active_id %in% remaining_ids)
}

matrix_custom_checks <- list(
  rename_updates_title_and_marks_user_source = check_rename_updates_title_and_marks_user_source,
  delete_active_conversation_clears_controller_record = check_delete_active_conversation_clears_controller_record
)

for (matrix_case in matrix) {
  local({
    case <- matrix_case
    test_that(paste("history matrix:", case$name), {
      store <- InMemoryConversationStore$new()
      ctrl <- HistoryController$new(
        chat_id = "matrix-test",
        client = mock_chat_client(),
        options = history_options(store = store, title = NULL),
        session = shiny::MockShinySession$new()
      )
      ctrl$scope <- "matrix-scope"

      active_id <- matrix_seed(ctrl, case$setup)
      before_updated_at <- ctrl$record$updated_at

      args <- matrix_resolve_args(case$operation$args, active_id)
      do.call(ctrl[[case$operation$method]], args)

      for (field in names(case$expect)) {
        expect_equal(ctrl$record[[field]], case$expect[[field]])
      }

      check <- matrix_custom_checks[[case$name]]
      if (!is.null(check)) {
        check(
          ctrl,
          list(
            store = store,
            active_id = active_id,
            before_updated_at = before_updated_at
          )
        )
      }
    })
  })
}
