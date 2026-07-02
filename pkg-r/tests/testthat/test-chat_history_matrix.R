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
  n <- if (turns > 0) (setup$conversations %||% 1) else 0
  ids <- character(0)
  for (i in seq_len(n)) {
    user_turn <- list(
      class = "ellmer::UserTurn",
      version = 1,
      props = list(
        contents = list(
          list(
            class = "ellmer::ContentText",
            version = 1,
            props = list(text = "Hello")
          )
        )
      )
    )
    asst_turn <- list(
      class = "ellmer::AssistantTurn",
      version = 1,
      props = list(
        contents = list(
          list(
            class = "ellmer::ContentText",
            version = 1,
            props = list(text = "Hi there")
          )
        )
      )
    )
    ctrl$on_response(list(user_turn, asst_turn))
    stopifnot(!is.null(ctrl$record))
    ids <- c(ids, ctrl$record$id)
    if (i < n) ctrl$new_chat()
  }
  stopifnot(!is.null(ctrl$record))
  result <- list(active_id = ctrl$record$id)
  if (length(ids) >= 2) {
    result$first_id <- ids[[1]]
  }
  result
}

matrix_resolve_args <- function(args, ids) {
  subs <- setNames(unname(ids), paste0("$", names(ids)))
  lapply(args, function(a) {
    if (is.character(a) && a %in% names(subs)) subs[[a]] else a
  })
}

check_rename_updates_title_and_marks_user_source <- function(ctrl, ctx) {
  expect_equal(ctrl$record$updated_at, ctx$before_updated_at)
  stored <- ctx$store$get(ctrl$partition, ctx$active_id)
  expect_equal(stored$title, "New Title")
}

check_delete_active_conversation_clears_controller_record <- function(
  ctrl,
  ctx
) {
  expect_null(ctrl$record)
  remaining <- ctx$store$list(ctrl$partition)
  remaining_ids <- vapply(remaining, `[[`, character(1L), "id")
  expect_false(ctx$active_id %in% remaining_ids)
}

check_rename_empty_title_is_noop <- function(ctrl, ctx) {
  expect_equal(ctrl$record$title, ctx$before_title)
}

check_rename_nonexistent_conversation_id_is_noop <- function(ctrl, ctx) {
  expect_equal(ctrl$record$title, ctx$before_title)
}

check_switch_to_same_active_id_is_noop <- function(ctrl, ctx) {
  expect_equal(ctrl$record$updated_at, ctx$before_updated_at)
}

check_new_chat_clears_active_record <- function(ctrl, ctx) {
  expect_null(ctrl$record)
  stored <- ctx$store$get(ctrl$partition, ctx$active_id)
  expect_false(is.null(stored))
}

check_switch_to_inactive_conversation_loads_target_record <- function(
  ctrl,
  ctx
) {
  expect_equal(ctrl$record$id, ctx$first_id)
  expect_false(identical(ctrl$record$id, ctx$active_id))
}

check_rename_inactive_conversation_updates_store_leaves_active_record <- function(
  ctrl,
  ctx
) {
  expect_equal(ctrl$record$id, ctx$active_id)
  stored <- ctx$store$get(ctrl$partition, ctx$first_id)
  expect_false(is.null(stored))
  expect_equal(stored$title, "Renamed Inactive")
  expect_equal(stored$title_source, "user")
}

check_delete_inactive_conversation_leaves_active_record_and_removes_from_store <- function(
  ctrl,
  ctx
) {
  expect_equal(ctrl$record$id, ctx$active_id)
  remaining <- ctx$store$list(ctrl$partition)
  remaining_ids <- vapply(remaining, `[[`, character(1L), "id")
  expect_false(ctx$first_id %in% remaining_ids)
}

matrix_custom_checks <- list(
  rename_updates_title_and_marks_user_source = check_rename_updates_title_and_marks_user_source,
  delete_active_conversation_clears_controller_record = check_delete_active_conversation_clears_controller_record,
  rename_empty_title_is_noop = check_rename_empty_title_is_noop,
  rename_nonexistent_conversation_id_is_noop = check_rename_nonexistent_conversation_id_is_noop,
  switch_to_same_active_id_is_noop = check_switch_to_same_active_id_is_noop,
  new_chat_clears_active_record = check_new_chat_clears_active_record,
  switch_to_inactive_conversation_loads_target_record = check_switch_to_inactive_conversation_loads_target_record,
  rename_inactive_conversation_updates_store_leaves_active_record = check_rename_inactive_conversation_updates_store_leaves_active_record,
  delete_inactive_conversation_leaves_active_record_and_removes_from_store = check_delete_inactive_conversation_leaves_active_record_and_removes_from_store
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
      ctrl$partition <- conversation_partition("matrix-test", "matrix-scope")

      ids <- matrix_seed(ctrl, case$setup)
      before_updated_at <- ctrl$record$updated_at
      before_title <- ctrl$record$title

      args <- matrix_resolve_args(case$operation$args, ids)
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
            active_id = ids$active_id,
            first_id = ids$first_id,
            before_updated_at = before_updated_at,
            before_title = before_title
          )
        )
      }
    })
  })
}
