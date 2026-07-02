part <- function(chat_id = "chat", scope = "user1") {
  conversation_partition(chat_id, scope)
}

test_that("InMemoryConversationStore: put and get", {
  store <- InMemoryConversationStore$new()
  rec <- new_conversation_record("Test chat")
  store$put(part(), rec)

  result <- store$get(part(), rec$id)
  expect_equal(result$title, "Test chat")
  expect_equal(result$id, rec$id)
})

test_that("InMemoryConversationStore: list returns newest first", {
  store <- InMemoryConversationStore$new()
  rec1 <- new_conversation_record("First")
  rec1$updated_at <- "2026-01-01T00:00:00Z"
  rec2 <- new_conversation_record("Second")
  rec2$updated_at <- "2026-06-01T00:00:00Z"

  store$put(part(), rec1)
  store$put(part(), rec2)

  metas <- store$list(part())
  expect_length(metas, 2)
  expect_equal(metas[[1]]$title, "Second")
  expect_equal(metas[[2]]$title, "First")
})

test_that("InMemoryConversationStore: delete removes conversation", {
  store <- InMemoryConversationStore$new()
  rec <- new_conversation_record("Test")
  store$put(part(), rec)
  store$delete(part(), rec$id)

  expect_null(store$get(part(), rec$id))
  expect_length(store$list(part()), 0)
})

test_that("InMemoryConversationStore: get returns NULL for missing", {
  store <- InMemoryConversationStore$new()
  expect_null(store$get(part(), "nonexistent"))
})

test_that("InMemoryConversationStore: scopes are isolated", {
  store <- InMemoryConversationStore$new()
  rec <- new_conversation_record("Test")
  store$put(part(scope = "user1"), rec)

  expect_null(store$get(part(scope = "user2"), rec$id))
  expect_length(store$list(part(scope = "user2")), 0)
})

test_that("InMemoryConversationStore partitions by chat id with same scope", {
  store <- InMemoryConversationStore$new()
  chat_a <- conversation_partition("chat-a", "browser-1")
  chat_b <- conversation_partition("chat-b", "browser-1")
  rec <- new_conversation_record("private to chat a")

  store$put(chat_a, rec)

  expect_equal(store$get(chat_a, rec$id)$id, rec$id)
  expect_null(store$get(chat_b, rec$id))
  expect_length(store$list(chat_b), 0)
})

test_that("InMemoryConversationStore partition keys avoid delimiter collisions", {
  store <- InMemoryConversationStore$new()
  partition_a <- conversation_partition("a", "b\rc")
  partition_b <- conversation_partition("a\rb", "c")
  rec <- new_conversation_record("private to a")

  store$put(partition_a, rec)

  expect_equal(store$get(partition_a, rec$id)$id, rec$id)
  expect_null(store$get(partition_b, rec$id))
  expect_length(store$list(partition_b), 0)
})

test_that("resolve_store('auto') in dev mode reuses one process memory store", {
  withr::local_options(shiny.devmode = TRUE)
  withr::local_envvar(TESTTHAT = "false")

  store1 <- resolve_store("auto")
  store2 <- resolve_store("auto")

  expect_true(inherits(store1, "InMemoryConversationStore"))
  expect_true(identical(store1, store2))
})

test_that("resolve_store('memory') returns a fresh memory store", {
  store1 <- resolve_store("memory")
  store2 <- resolve_store("memory")

  expect_true(inherits(store1, "InMemoryConversationStore"))
  expect_true(inherits(store2, "InMemoryConversationStore"))
  expect_false(identical(store1, store2))
})

test_that("ConversationStore: search filters by title", {
  store <- InMemoryConversationStore$new()
  rec1 <- new_conversation_record("Penguin analysis")
  rec2 <- new_conversation_record("Weather data")
  store$put(part(), rec1)
  store$put(part(), rec2)

  results <- store$search(part(), "penguin")
  expect_length(results, 1)
  expect_equal(results[[1]]$title, "Penguin analysis")
})

test_that("InMemoryConversationStore: list does not reserialize on repeat calls", {
  store <- InMemoryConversationStore$new()
  rec <- new_conversation_record("t")
  store$put(part(), rec)
  store$list(part()) # warm cache

  call_count <- 0
  testthat::local_mocked_bindings(
    record_json_size = function(record) {
      call_count <<- call_count + 1
      as.double(
        nchar(jsonlite::toJSON(record, auto_unbox = TRUE), type = "bytes")
      )
    }
  )
  store$list(part())
  store$list(part())
  expect_equal(call_count, 0)
})

test_that("InMemoryConversationStore: put updates warm cache", {
  store <- InMemoryConversationStore$new()
  key <- partition_key(part())
  a <- new_conversation_record("first")
  store$put(part(), a)
  store$list(part()) # warm

  b <- new_conversation_record("second")
  store$put(part(), b)

  cache <- store$.__enclos_env__$private$meta_cache[[key]]
  expect_setequal(vapply(cache, function(m) m$id, character(1)), c(a$id, b$id))
})

test_that("InMemoryConversationStore: put does not create cache for cold scope", {
  store <- InMemoryConversationStore$new()
  key <- partition_key(part())
  rec <- new_conversation_record("cold")
  store$put(part(), rec)
  expect_null(store$.__enclos_env__$private$meta_cache[[key]])
})

test_that("InMemoryConversationStore: delete updates warm cache", {
  store <- InMemoryConversationStore$new()
  key <- partition_key(part())
  rec <- new_conversation_record("t")
  store$put(part(), rec)
  store$list(part()) # warm
  store$delete(part(), rec$id)

  expect_length(store$.__enclos_env__$private$meta_cache[[key]], 0)
})

test_that("FileConversationStore: put and get round-trip via JSON", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)
  rec <- new_conversation_record("Test chat")
  store$put(part(), rec)

  result <- store$get(part(), rec$id)
  expect_equal(result$title, "Test chat")
  expect_equal(result$id, rec$id)
  expect_equal(result$schema_version, 1L)
})

test_that("FileConversationStore: response_count round-trips via JSON", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)
  rec <- new_conversation_record("Test chat")
  rec$response_count <- 2L
  store$put(part(), rec)

  result <- store$get(part(), rec$id)
  expect_equal(result$response_count, 2L)
})

test_that("FileConversationStore: files are written to disk", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)
  rec <- new_conversation_record("Persisted")
  store$put(part(), rec)

  chat_dir <- list.dirs(dir, recursive = FALSE)
  expect_length(chat_dir, 1)
  scope_dir <- list.dirs(chat_dir, recursive = FALSE)
  expect_length(scope_dir, 1)
  conv_dir <- list.dirs(scope_dir, recursive = FALSE)
  expect_length(conv_dir, 1)
  expect_true(file.exists(file.path(conv_dir, "record.json")))
})

test_that("FileConversationStore partitions by chat id on disk", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)
  chat_a <- conversation_partition("chat-a", "browser-1")
  chat_b <- conversation_partition("chat-b", "browser-1")
  rec <- new_conversation_record("private to chat a")

  store$put(chat_a, rec)

  expect_equal(store$get(chat_a, rec$id)$id, rec$id)
  expect_null(store$get(chat_b, rec$id))
  expect_length(store$list(chat_b), 0)
  expect_length(list.dirs(dir, recursive = FALSE), 1)
})

test_that("FileConversationStore: put errors when atomic rename fails", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)
  rec <- new_conversation_record("Persisted")

  partition <- part()

  # Warm the store's write-state cache and create a real record.json first,
  # then swap record.json for a directory so the *next* put()'s
  # file_move() collides without re-reading (and erroring on) record.json.
  store$put(partition, rec)
  cdir <- file.path(
    dir,
    sanitize_scope(partition$chat_id),
    sanitize_scope(partition$scope),
    rec$id
  )
  unlink(file.path(cdir, "record.json"))
  dir.create(file.path(cdir, "record.json"))

  expect_error(
    store$put(partition, rec),
    "Failed to write conversation"
  )
})

test_that("FileConversationStore: list returns newest first", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)
  rec1 <- new_conversation_record("First")
  rec1$updated_at <- "2026-01-01T00:00:00Z"
  rec2 <- new_conversation_record("Second")
  rec2$updated_at <- "2026-06-01T00:00:00Z"

  store$put(part(), rec1)
  store$put(part(), rec2)

  metas <- store$list(part())
  expect_length(metas, 2)
  expect_equal(metas[[1]]$title, "Second")
})

test_that("FileConversationStore: delete removes file", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)
  rec <- new_conversation_record("To delete")
  store$put(part(), rec)
  store$delete(part(), rec$id)

  expect_null(store$get(part(), rec$id))
  expect_length(store$list(part()), 0)
})

test_that("FileConversationStore: total_size is 0 for missing scope", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)
  expect_equal(store$total_size(part()), 0L)
})

test_that("FileConversationStore: total_size grows with put", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)

  rec <- new_conversation_record("Test")
  store$put(part(), rec)
  size1 <- store$total_size(part())
  expect_gt(size1, 0)

  rec2 <- new_conversation_record("Test2")
  store$put(part(), rec2)
  expect_gt(store$total_size(part()), size1)
})

test_that("FileConversationStore: total_size shrinks with delete", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)

  rec1 <- new_conversation_record("A")
  rec2 <- new_conversation_record("B")
  store$put(part(), rec1)
  store$put(part(), rec2)
  total <- store$total_size(part())

  store$delete(part(), rec1$id)
  expect_lt(store$total_size(part()), total)
})

test_that("InMemoryConversationStore: total_size is 0 for missing scope", {
  store <- InMemoryConversationStore$new()
  expect_equal(store$total_size(part()), 0L)
})

test_that("InMemoryConversationStore: total_size grows with put", {
  store <- InMemoryConversationStore$new()

  rec <- new_conversation_record("Test")
  store$put(part(), rec)
  size1 <- store$total_size(part())
  expect_gt(size1, 0)

  rec2 <- new_conversation_record("Test2")
  store$put(part(), rec2)
  expect_gt(store$total_size(part()), size1)
})

test_that("InMemoryConversationStore: total_size shrinks with delete", {
  store <- InMemoryConversationStore$new()

  rec1 <- new_conversation_record("A")
  rec2 <- new_conversation_record("B")
  store$put(part(), rec1)
  store$put(part(), rec2)
  total <- store$total_size(part())

  store$delete(part(), rec1$id)
  expect_lt(store$total_size(part()), total)
})

test_that("FileConversationStore persists turns and ui across multiple put()s without rewriting old data", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)

  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(
      parent = NULL,
      children = list(),
      turns = list(list(class = "ellmer::UserTurn", version = 1, props = list(contents = list()))),
      ui = list(list(role = "user", segments = list(list(content = "hi", content_type = "markdown"))))
    )
  )
  rec$current_leaf <- "n_0001"
  store$put(part(), rec)

  chat_dir <- list.dirs(dir, recursive = FALSE)[1]
  scope_dir <- list.dirs(chat_dir, recursive = FALSE)[1]
  conv_dir <- file.path(scope_dir, rec$id)
  expect_true(dir.exists(conv_dir))
  expect_true(file.exists(file.path(conv_dir, "turns.jsonl")))
  expect_true(file.exists(file.path(conv_dir, "ui.jsonl")))
  turns_lines_after_first_put <- length(readLines(file.path(conv_dir, "turns.jsonl")))
  expect_equal(turns_lines_after_first_put, 1)

  # Extend with a second node; the first node's turns/ui must not be rewritten.
  rec$nodes$n_0002 <- list(
    parent = "n_0001",
    children = list(),
    turns = list(list(class = "ellmer::AssistantTurn", version = 1, props = list(contents = list()))),
    ui = list(list(role = "assistant", segments = list(list(content = "hello", content_type = "markdown"))))
  )
  rec$nodes$n_0001$children <- list("n_0002")
  rec$current_leaf <- "n_0002"
  store$put(part(), rec)

  turns_lines_after_second_put <- length(readLines(file.path(conv_dir, "turns.jsonl")))
  expect_equal(turns_lines_after_second_put, 2)

  fetched <- store$get(part(), rec$id)
  expect_length(fetched$nodes, 2)
  expect_equal(fetched$nodes$n_0001$ui[[1]]$segments[[1]]$content, "hi")
  expect_equal(fetched$nodes$n_0002$ui[[1]]$segments[[1]]$content, "hello")
})

test_that("FileConversationStore re-appends a node's ui when it grows across saves", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)

  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(
      parent = NULL,
      children = list(),
      turns = list(list(class = "ellmer::AssistantTurn", version = 1, props = list(contents = list()))),
      ui = list(list(role = "assistant", segments = list(list(content = "partial", content_type = "markdown"))))
    )
  )
  rec$current_leaf <- "n_0001"
  store$put(part(), rec)

  # Same node grows its ui (a streamed reply attaching more content).
  rec$nodes$n_0001$ui <- c(
    rec$nodes$n_0001$ui,
    list(list(role = "assistant", segments = list(list(content = "more", content_type = "markdown"))))
  )
  store$put(part(), rec)

  fetched <- store$get(part(), rec$id)
  expect_length(fetched$nodes$n_0001$ui, 2)
  expect_equal(fetched$nodes$n_0001$ui[[2]]$segments[[1]]$content, "more")
})

test_that("FileConversationStore preserves schema_version and children on round trip", {
  dir <- withr::local_tempdir()
  store <- FileConversationStore$new(dir = dir)

  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(
      parent = NULL,
      children = list("n_0002"),
      turns = list(list(class = "ellmer::UserTurn", version = 1, props = list(contents = list()))),
      ui = NULL
    ),
    n_0002 = list(
      parent = "n_0001",
      children = list(),
      turns = list(list(class = "ellmer::AssistantTurn", version = 1, props = list(contents = list()))),
      ui = NULL
    )
  )
  rec$current_leaf <- "n_0002"
  store$put(part(), rec)

  fetched <- store$get(part(), rec$id)
  expect_equal(fetched$schema_version, 1)
  expect_equal(fetched$nodes$n_0001$children, list("n_0002"))
  expect_null(fetched$nodes$n_0001$ui)
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
