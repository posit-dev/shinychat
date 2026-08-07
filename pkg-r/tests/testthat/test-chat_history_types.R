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
    n_0001 = list(parent = NULL, turns = list(list(role = "user"))),
    n_0002 = list(parent = "n_0001", turns = list(list(role = "assistant"))),
    n_0003 = list(parent = "n_0002", turns = list(list(role = "user")))
  )
  rec$current_leaf <- "n_0003"

  ids <- record_path_node_ids(rec)
  expect_equal(ids, c("n_0001", "n_0002", "n_0003"))
})

test_that("record_path_node_ids() returns empty for empty record", {
  rec <- new_conversation_record("test")
  expect_equal(record_path_node_ids(rec), character(0))
})

test_that("record_path_turns() flattens turns across nodes on the path", {
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(
      parent = NULL,
      children = list("n_0002"),
      turns = list(list(role = "user", text = "hi")),
      ui = NULL
    ),
    n_0002 = list(
      parent = "n_0001",
      children = list(),
      turns = list(
        list(role = "assistant", text = "checking..."),
        list(role = "assistant", text = "hello")
      ),
      ui = NULL
    )
  )
  rec$current_leaf <- "n_0002"

  turns <- record_path_turns(rec)
  expect_length(turns, 3)
  expect_equal(turns[[1]]$role, "user")
  expect_equal(turns[[2]]$text, "checking...")
  expect_equal(turns[[3]]$text, "hello")
})

test_that("record_turn_count() sums turns across the path", {
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(
      parent = NULL,
      children = list(),
      turns = list(list(role = "user"), list(role = "assistant")),
      ui = NULL
    )
  )
  rec$current_leaf <- "n_0001"
  expect_equal(record_turn_count(rec), 2)
})

test_that("record_turn_count() is 0 for an empty record", {
  rec <- new_conversation_record("test")
  expect_equal(record_turn_count(rec), 0)
})

test_that("record_ui_count() sums ui messages across the path, treating NULL as 0", {
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(
      parent = NULL,
      children = list("n_0002"),
      turns = list(list(role = "user")),
      ui = list(list(role = "user", segments = list()))
    ),
    n_0002 = list(
      parent = "n_0001",
      children = list(),
      turns = list(list(role = "assistant")),
      ui = NULL
    )
  )
  rec$current_leaf <- "n_0002"
  expect_equal(record_ui_count(rec), 1)
})

test_that("record_children_of() returns root nodes sorted by sequence when node_id is NULL", {
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(parent = NULL, children = list("n_0002")),
    n_0002 = list(parent = "n_0001", children = list()),
    n_0003 = list(parent = NULL, children = list("n_0004")),
    n_0004 = list(parent = "n_0003", children = list())
  )
  rec$current_leaf <- "n_0004"

  expect_equal(record_children_of(rec, NULL), c("n_0001", "n_0003"))
})

test_that("record_children_of() returns a node's children as a character vector", {
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(parent = NULL, children = list("n_0002", "n_0003")),
    n_0002 = list(parent = "n_0001", children = list()),
    n_0003 = list(parent = "n_0001", children = list())
  )
  rec$current_leaf <- "n_0002"

  expect_equal(record_children_of(rec, "n_0001"), c("n_0002", "n_0003"))
  expect_equal(record_children_of(rec, "n_0002"), character(0))
})

test_that("record_siblings_of() includes the node itself among its siblings", {
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(parent = NULL, children = list("n_0002", "n_0003")),
    n_0002 = list(parent = "n_0001", children = list()),
    n_0003 = list(parent = "n_0001", children = list())
  )
  rec$current_leaf <- "n_0002"

  expect_equal(record_siblings_of(rec, "n_0002"), c("n_0002", "n_0003"))
  expect_equal(record_siblings_of(rec, "n_0003"), c("n_0002", "n_0003"))
})

test_that("record_siblings_of() returns just itself when it has no siblings", {
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(parent = NULL, children = list("n_0002")),
    n_0002 = list(parent = "n_0001", children = list())
  )
  rec$current_leaf <- "n_0002"

  expect_equal(record_siblings_of(rec, "n_0002"), "n_0002")
})

test_that("record_subtree_leaf() returns the node itself when it has no children", {
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(parent = NULL, children = list())
  )
  rec$current_leaf <- "n_0001"

  expect_equal(record_subtree_leaf(rec, "n_0001"), "n_0001")
})

test_that("record_subtree_leaf() walks the last-child chain to a leaf", {
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(parent = NULL, children = list("n_0002")),
    n_0002 = list(parent = "n_0001", children = list("n_0003", "n_0004")),
    n_0003 = list(parent = "n_0002", children = list()),
    n_0004 = list(parent = "n_0002", children = list())
  )
  rec$current_leaf <- "n_0004"

  # Last child at each level: n_0001 -> n_0002 -> n_0004 (not n_0003)
  expect_equal(record_subtree_leaf(rec, "n_0001"), "n_0004")
})

test_that("record_subtree_leaf() follows selected_child, falling back to newest", {
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(parent = NULL, children = list("n_0002")),
    n_0002 = list(parent = "n_0001", children = list("n_0003", "n_0004")),
    n_0003 = list(parent = "n_0002", children = list()),
    n_0004 = list(parent = "n_0002", children = list())
  )
  # Remember the older child n_0003 as the selected path.
  rec <- record_set_current_leaf(rec, "n_0003")
  expect_equal(rec$nodes[["n_0002"]]$selected_child, "n_0003")
  expect_equal(record_subtree_leaf(rec, "n_0001"), "n_0003")
  # Clearing the memory falls back to the newest child (n_0004).
  rec$nodes[["n_0002"]]$selected_child <- NULL
  expect_equal(record_subtree_leaf(rec, "n_0002"), "n_0004")
})

test_that("record_subtree_leaf() remembers descendant across sibling navigation", {
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(parent = NULL, children = list("n_0002", "n_0005")),
    n_0002 = list(parent = "n_0001", children = list("n_0003", "n_0004")),
    n_0003 = list(parent = "n_0002", children = list()),
    n_0004 = list(parent = "n_0002", children = list()),
    n_0005 = list(parent = "n_0001", children = list("n_0006", "n_0007")),
    n_0006 = list(parent = "n_0005", children = list()),
    n_0007 = list(parent = "n_0005", children = list())
  )
  # Land inside branch n_0002 on the older leaf n_0003 (not the newest).
  rec <- record_set_current_leaf(rec, "n_0003")
  # Navigate to sibling n_0005: no memory yet, so its newest leaf n_0007.
  rec <- record_set_current_leaf(rec, record_subtree_leaf(rec, "n_0005"))
  expect_equal(rec$current_leaf, "n_0007")
  # Navigate back to n_0002: returns to n_0003, the last-viewed descendant.
  rec <- record_set_current_leaf(rec, record_subtree_leaf(rec, "n_0002"))
  expect_equal(rec$current_leaf, "n_0003")
})

test_that("record_path_sibling_metadata() is empty when no node on the path has siblings", {
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(parent = NULL, children = list("n_0002")),
    n_0002 = list(parent = "n_0001", children = list())
  )
  rec$current_leaf <- "n_0002"

  expect_equal(record_path_sibling_metadata(rec), list())
})

test_that("record_path_sibling_metadata() reports 0-based index and total for branched path nodes", {
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(parent = NULL, children = list("n_0002")),
    n_0002 = list(parent = "n_0001", children = list()),
    n_0003 = list(parent = NULL, children = list("n_0004")),
    n_0004 = list(parent = "n_0003", children = list())
  )
  rec$current_leaf <- "n_0004"

  meta <- record_path_sibling_metadata(rec)
  expect_equal(meta$n_0003$index, 1L)
  expect_equal(meta$n_0003$total, 2L)
  expect_null(meta$n_0004)
})

test_that("record_node_id_for_message_index() resolves a flat index to the owning node", {
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(
      parent = NULL,
      children = list("n_0002"),
      ui = list(list(role = "user"))
    ),
    n_0002 = list(
      parent = "n_0001",
      children = list(),
      ui = list(list(role = "assistant"), list(role = "assistant"))
    )
  )
  rec$current_leaf <- "n_0002"

  expect_equal(record_node_id_for_message_index(rec, 0), "n_0001")
  expect_equal(record_node_id_for_message_index(rec, 1), "n_0002")
  expect_equal(record_node_id_for_message_index(rec, 2), "n_0002")
})

test_that("record_node_id_for_message_index() errors when the index is out of range", {
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(
      parent = NULL,
      children = list(),
      ui = list(list(role = "user"))
    )
  )
  rec$current_leaf <- "n_0001"

  expect_error(record_node_id_for_message_index(rec, 1), "out of range")
  expect_error(record_node_id_for_message_index(rec, -1), "out of range")
})

test_that("record_node_id_for_message_index() counts NULL-ui nodes as one message", {
  # A node with NULL ui still renders one fabricated message on restore
  # (replay_ui's fallback), so it occupies one client message slot here too --
  # the mapping must not skip it, or client indices would disagree.
  rec <- new_conversation_record("test")
  rec$nodes <- list(
    n_0001 = list(
      parent = NULL,
      children = list("n_0002"),
      ui = list(list(role = "user"))
    ),
    n_0002 = list(parent = "n_0001", children = list("n_0003"), ui = NULL),
    n_0003 = list(
      parent = "n_0002",
      children = list(),
      ui = list(list(role = "assistant"))
    )
  )
  rec$current_leaf <- "n_0003"

  expect_equal(record_node_id_for_message_index(rec, 0), "n_0001")
  expect_equal(record_node_id_for_message_index(rec, 1), "n_0002")
  expect_equal(record_node_id_for_message_index(rec, 2), "n_0003")
})

user_turn_fixture <- function(text) {
  list(
    class = "ellmer::UserTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = text)
        )
      )
    )
  )
}

assistant_turn_fixture <- function(text) {
  list(
    class = "ellmer::AssistantTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = text)
        )
      )
    )
  )
}

tool_request_content_fixture <- function(
  id = "t1",
  name = "get_weather",
  arguments = list()
) {
  list(
    class = "ellmer::ContentToolRequest",
    version = 1,
    props = list(id = id, name = name, arguments = arguments, extra = list())
  )
}

tool_result_content_fixture <- function(
  id = "t1",
  name = "get_weather",
  arguments = list(),
  value = "ok"
) {
  list(
    class = "ellmer::ContentToolResult",
    version = 1,
    props = list(
      value = value,
      extra = list(),
      request = tool_request_content_fixture(
        id = id,
        name = name,
        arguments = arguments
      )
    )
  )
}

tool_request_turn_fixture <- function(text) {
  list(
    class = "ellmer::AssistantTurn",
    version = 1,
    props = list(
      contents = list(
        list(
          class = "ellmer::ContentText",
          version = 1,
          props = list(text = text)
        ),
        tool_request_content_fixture()
      )
    )
  )
}

tool_result_turn_fixture <- function(value = "Sunny, 75F") {
  list(
    class = "ellmer::UserTurn",
    version = 1,
    props = list(contents = list(tool_result_content_fixture(value = value)))
  )
}

test_that("extend_record_linear() appends new turn groups as nodes", {
  rec <- new_conversation_record("test")
  turns <- list(user_turn_fixture("hi"), assistant_turn_fixture("hello"))

  rec <- extend_record_linear(
    rec,
    turns,
    transcript = list(),
    transcript_offset = 0,
    tools = list()
  )

  expect_equal(names(rec$nodes), c("n_0001", "n_0002"))
  expect_null(rec$nodes$n_0001$parent)
  expect_equal(rec$nodes$n_0002$parent, "n_0001")
  expect_equal(rec$current_leaf, "n_0002")
})

test_that("extend_record_linear() groups a tool-call round into a single node", {
  rec <- new_conversation_record("test")
  turns <- list(
    user_turn_fixture("what's the weather?"),
    tool_request_turn_fixture("Let me check."),
    tool_result_turn_fixture(),
    assistant_turn_fixture("It's sunny and 75F!")
  )

  rec <- extend_record_linear(
    rec,
    turns,
    transcript = list(),
    transcript_offset = 0,
    tools = list()
  )

  expect_equal(names(rec$nodes), c("n_0001", "n_0002"))
  expect_length(rec$nodes$n_0001$turns, 1)
  expect_length(rec$nodes$n_0002$turns, 3)
})

test_that("extend_record_linear() is idempotent for the same turns and messages", {
  rec <- new_conversation_record("test")
  turns <- list(user_turn_fixture("hi"))
  rec <- extend_record_linear(
    rec,
    turns,
    transcript = list(),
    transcript_offset = 0,
    tools = list()
  )

  rec2 <- extend_record_linear(
    rec,
    turns,
    transcript = list(),
    transcript_offset = 0,
    tools = list()
  )
  expect_equal(length(rec2$nodes), 1)
})

test_that("extend_record_linear() appends only new turn groups", {
  rec <- new_conversation_record("test")
  turns1 <- list(user_turn_fixture("hi"))
  rec <- extend_record_linear(
    rec,
    turns1,
    transcript = list(),
    transcript_offset = 0,
    tools = list()
  )

  turns2 <- list(user_turn_fixture("hi"), assistant_turn_fixture("hello"))
  rec <- extend_record_linear(
    rec,
    turns2,
    transcript = list(),
    transcript_offset = 0,
    tools = list()
  )
  expect_equal(length(rec$nodes), 2)
  expect_equal(rec$current_leaf, "n_0002")
})

test_that("extend_record_linear() attaches a user message to the matching new user-turn node", {
  rec <- new_conversation_record("test")
  turns <- list(user_turn_fixture("hi"), assistant_turn_fixture("hello"))
  transcript <- list(
    list(
      role = "user",
      segments = list(list(content = "hi", content_type = "markdown"))
    ),
    list(
      role = "assistant",
      segments = list(list(content = "hello", content_type = "markdown"))
    )
  )

  rec <- extend_record_linear(
    rec,
    turns,
    transcript = transcript,
    transcript_offset = 0,
    tools = list()
  )

  expect_equal(rec$nodes$n_0001$ui, list(transcript[[1]]))
  expect_equal(rec$nodes$n_0002$ui, list(transcript[[2]]))
})

test_that("extend_record_linear() attaches non-user messages to the last new node", {
  rec <- new_conversation_record("test")
  turns <- list(
    user_turn_fixture("weather?"),
    tool_request_turn_fixture("checking"),
    tool_result_turn_fixture(),
    assistant_turn_fixture("sunny")
  )
  transcript <- list(
    list(
      role = "user",
      segments = list(list(content = "weather?", content_type = "markdown"))
    ),
    list(
      role = "assistant",
      segments = list(list(content = "[tool card]", content_type = "html"))
    ),
    list(
      role = "assistant",
      segments = list(list(content = "sunny", content_type = "markdown"))
    )
  )

  rec <- extend_record_linear(
    rec,
    turns,
    transcript = transcript,
    transcript_offset = 0,
    tools = list()
  )

  expect_equal(rec$nodes$n_0001$ui, list(transcript[[1]]))
  expect_equal(rec$nodes$n_0002$ui, transcript[2:3])
})

test_that("extend_record_linear() attaches a late-arriving message to the current leaf when no new node is created", {
  rec <- new_conversation_record("test")
  turns <- list(user_turn_fixture("hi"))
  rec <- extend_record_linear(
    rec,
    turns,
    transcript = list(
      list(
      role = "user",
      segments = list(list(content = "hi", content_type = "markdown"))
      )
    ),
    transcript_offset = 0,
    tools = list()
  )

  # Same turns (no new node), but one more ui message arrived (e.g. the
  # client caught up after a streamed reply settled).
  late_message <- list(
    role = "assistant",
    segments = list(list(content = "hello", content_type = "markdown"))
  )
  rec <- extend_record_linear(
    rec,
    turns,
    transcript = list(
      list(
        role = "user",
        segments = list(list(content = "hi", content_type = "markdown"))
      ),
      late_message
    ),
    transcript_offset = 1,
    tools = list()
  )

  expect_equal(length(rec$nodes), 1)
  expect_equal(
    rec$nodes$n_0001$ui,
    list(
      list(
        role = "user",
        segments = list(list(content = "hi", content_type = "markdown"))
      ),
      late_message
    )
  )
})

test_that("extend_record_linear() records children pointers", {
  rec <- new_conversation_record("test")
  turns <- list(user_turn_fixture("hi"), assistant_turn_fixture("hello"))
  rec <- extend_record_linear(
    rec,
    turns,
    transcript = list(),
    transcript_offset = 0,
    tools = list()
  )

  expect_equal(rec$nodes$n_0001$children, list("n_0002"))
  expect_equal(rec$nodes$n_0002$children, list())
})
