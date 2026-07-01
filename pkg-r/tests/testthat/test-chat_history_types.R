test_that("new_conversation_id() produces valid IDs", {
  id1 <- new_conversation_id()
  id2 <- new_conversation_id()
  expect_match(id1, "^c_[0-9a-f]{23}$")
  expect_match(id2, "^c_[0-9a-f]{23}$")
  expect_false(identical(id1, id2))
})

test_that("new_conversation_record() creates valid empty record", {
  rec <- new_conversation_record("Test chat")
  expect_equal(rec$schema_version, 1L)
  expect_match(rec$id, "^c_")
  expect_equal(rec$title, "Test chat")
  expect_null(rec$title_source)
  expect_equal(rec$response_count, 0L)
  expect_equal(rec$nodes, list())
  expect_null(rec$current_leaf)
  expect_equal(rec$values, list())
  expect_equal(rec$client_info, list())
  # Timestamps are ISO 8601 UTC
  expect_match(rec$created_at, "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$")
  expect_identical(rec$created_at, rec$updated_at)
})

test_that("new_conversation_record() accepts client_info", {
  rec <- new_conversation_record(
    "Test",
    client_info = list(provider = "openai", model = "gpt-4o")
  )
  expect_equal(rec$client_info$provider, "openai")
})

test_that("record_path_node_ids() walks parent chain", {
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(parent = NULL, turn = list(role = "user")),
    n_0002 = list(parent = "n_0001", turn = list(role = "assistant")),
    n_0003 = list(parent = "n_0002", turn = list(role = "user"))
  )
  rec$current_leaf <- "n_0003"

  ids <- record_path_node_ids(rec)
  expect_equal(ids, c("n_0001", "n_0002", "n_0003"))
})

test_that("record_path_node_ids() returns empty for empty record", {
  rec <- new_conversation_record("test")
  expect_equal(record_path_node_ids(rec), character(0))
})

test_that("record_path_turns() extracts turns along path", {
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(parent = NULL, turn = list(role = "user", text = "hi")),
    n_0002 = list(
      parent = "n_0001",
      turn = list(role = "assistant", text = "hello")
    )
  )
  rec$current_leaf <- "n_0002"

  turns <- record_path_turns(rec)
  expect_length(turns, 2)
  expect_equal(turns[[1]]$role, "user")
  expect_equal(turns[[2]]$role, "assistant")
})

test_that("extend_record_linear() appends new turns as nodes", {
  rec <- new_conversation_record("test")

  turns <- list(
    list(role = "user", text = "hi"),
    list(role = "assistant", text = "hello")
  )
  rec <- extend_record_linear(rec, turns)

  expect_equal(names(rec$nodes), c("n_0001", "n_0002"))
  expect_null(rec$nodes$n_0001$parent)
  expect_equal(rec$nodes$n_0002$parent, "n_0001")
  expect_equal(rec$current_leaf, "n_0002")
})

test_that("extend_record_linear() is idempotent for same turns", {
  rec <- new_conversation_record("test")
  turns <- list(list(role = "user", text = "hi"))
  rec <- extend_record_linear(rec, turns)

  rec2 <- extend_record_linear(rec, turns)
  expect_equal(length(rec2$nodes), 1)
})

test_that("extend_record_linear() appends only new turns", {
  rec <- new_conversation_record("test")
  turns1 <- list(list(role = "user", text = "hi"))
  rec <- extend_record_linear(rec, turns1)

  turns2 <- list(
    list(role = "user", text = "hi"),
    list(role = "assistant", text = "hello")
  )
  rec <- extend_record_linear(rec, turns2)
  expect_equal(length(rec$nodes), 2)
  expect_equal(rec$current_leaf, "n_0002")
})
