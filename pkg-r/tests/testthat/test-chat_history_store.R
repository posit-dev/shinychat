test_that("InMemoryConversationStore: put and get", {
  store <- InMemoryConversationStore$new()
  rec <- new_conversation_record("Test chat")
  store$put("user1", rec)

  result <- store$get("user1", rec$id)
  expect_equal(result$title, "Test chat")
  expect_equal(result$id, rec$id)
})

test_that("InMemoryConversationStore: list returns newest first", {
  store <- InMemoryConversationStore$new()
  rec1 <- new_conversation_record("First")
  rec1$updated_at <- "2026-01-01T00:00:00Z"
  rec2 <- new_conversation_record("Second")
  rec2$updated_at <- "2026-06-01T00:00:00Z"

  store$put("user1", rec1)
  store$put("user1", rec2)

  metas <- store$list("user1")
  expect_length(metas, 2)
  expect_equal(metas[[1]]$title, "Second")
  expect_equal(metas[[2]]$title, "First")
})

test_that("InMemoryConversationStore: delete removes conversation", {
  store <- InMemoryConversationStore$new()
  rec <- new_conversation_record("Test")
  store$put("user1", rec)
  store$delete("user1", rec$id)

  expect_null(store$get("user1", rec$id))
  expect_length(store$list("user1"), 0)
})

test_that("InMemoryConversationStore: get returns NULL for missing", {
  store <- InMemoryConversationStore$new()
  expect_null(store$get("user1", "nonexistent"))
})

test_that("InMemoryConversationStore: scopes are isolated", {
  store <- InMemoryConversationStore$new()
  rec <- new_conversation_record("Test")
  store$put("user1", rec)

  expect_null(store$get("user2", rec$id))
  expect_length(store$list("user2"), 0)
})

test_that("ConversationStore: search filters by title", {
  store <- InMemoryConversationStore$new()
  rec1 <- new_conversation_record("Penguin analysis")
  rec2 <- new_conversation_record("Weather data")
  store$put("user1", rec1)
  store$put("user1", rec2)

  results <- store$search("user1", "penguin")
  expect_length(results, 1)
  expect_equal(results[[1]]$title, "Penguin analysis")
})

test_that("FileConversationStore: put and get round-trip via JSON", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)
  rec <- new_conversation_record("Test chat")
  store$put("user1", rec)

  result <- store$get("user1", rec$id)
  expect_equal(result$title, "Test chat")
  expect_equal(result$id, rec$id)
  expect_equal(result$schema_version, 1L)
})

test_that("FileConversationStore: files are written to disk", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)
  rec <- new_conversation_record("Persisted")
  store$put("user1", rec)

  scope_dir <- list.dirs(dir, recursive = FALSE)
  expect_length(scope_dir, 1)
  json_files <- list.files(scope_dir, pattern = "\\.json$")
  expect_length(json_files, 1)
})

test_that("FileConversationStore: list returns newest first", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)
  rec1 <- new_conversation_record("First")
  rec1$updated_at <- "2026-01-01T00:00:00Z"
  rec2 <- new_conversation_record("Second")
  rec2$updated_at <- "2026-06-01T00:00:00Z"

  store$put("user1", rec1)
  store$put("user1", rec2)

  metas <- store$list("user1")
  expect_length(metas, 2)
  expect_equal(metas[[1]]$title, "Second")
})

test_that("FileConversationStore: delete removes file", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)
  rec <- new_conversation_record("To delete")
  store$put("user1", rec)
  store$delete("user1", rec$id)

  expect_null(store$get("user1", rec$id))
  expect_length(store$list("user1"), 0)
})

test_that("FileConversationStore: total_size is 0 for missing scope", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)
  expect_equal(store$total_size("user1"), 0L)
})

test_that("FileConversationStore: total_size grows with put", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)

  rec <- new_conversation_record("Test")
  store$put("user1", rec)
  size1 <- store$total_size("user1")
  expect_gt(size1, 0)

  rec2 <- new_conversation_record("Test2")
  store$put("user1", rec2)
  expect_gt(store$total_size("user1"), size1)
})

test_that("FileConversationStore: total_size shrinks with delete", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)

  rec1 <- new_conversation_record("A")
  rec2 <- new_conversation_record("B")
  store$put("user1", rec1)
  store$put("user1", rec2)
  total <- store$total_size("user1")

  store$delete("user1", rec1$id)
  expect_lt(store$total_size("user1"), total)
})

test_that("InMemoryConversationStore: total_size is 0 for missing scope", {
  store <- InMemoryConversationStore$new()
  expect_equal(store$total_size("user1"), 0L)
})

test_that("InMemoryConversationStore: total_size grows with put", {
  store <- InMemoryConversationStore$new()

  rec <- new_conversation_record("Test")
  store$put("user1", rec)
  size1 <- store$total_size("user1")
  expect_gt(size1, 0)

  rec2 <- new_conversation_record("Test2")
  store$put("user1", rec2)
  expect_gt(store$total_size("user1"), size1)
})

test_that("InMemoryConversationStore: total_size shrinks with delete", {
  store <- InMemoryConversationStore$new()

  rec1 <- new_conversation_record("A")
  rec2 <- new_conversation_record("B")
  store$put("user1", rec1)
  store$put("user1", rec2)
  total <- store$total_size("user1")

  store$delete("user1", rec1$id)
  expect_lt(store$total_size("user1"), total)
})

test_that("sanitize_scope() is safe for filesystem", {
  scope <- sanitize_scope("user@example.com/admin")
  expect_false(grepl("[^A-Za-z0-9_-]", scope))
  expect_true(nchar(scope) <= 53) # 40 + 1 + 12
})

test_that("safe_conv_path() rejects path traversal", {
  expect_error(safe_conv_path(tempdir(), "../../../etc/passwd"))
  expect_error(safe_conv_path(tempdir(), ""))
})
