int_to_hex <- function(n, width = 13L) {
  hex_chars <- c(0:9, letters[1:6])
  digits <- character(0)
  while (n > 0) {
    digits <- c(hex_chars[(n %% 16) + 1], digits)
    n <- floor(n / 16)
  }
  hex <- paste0(digits, collapse = "")
  if (nchar(hex) < width) {
    hex <- paste0(strrep("0", width - nchar(hex)), hex)
  }
  hex
}

new_conversation_id <- function() {
  ms <- floor(as.numeric(Sys.time()) * 1000)
  timestamp_hex <- int_to_hex(ms, width = 13L)
  random_hex <- paste0(
    sprintf("%02x", sample.int(256L, 5L, replace = TRUE) - 1L),
    collapse = ""
  )
  paste0("c_", timestamp_hex, random_hex)
}

utcnow_iso <- function() {
  format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
}

# size_bytes must stay double, never integer -- narrowing overflows R's
# 32-bit integer range at ~2GB (see chat_history.R max_store_mb handling).
new_conversation_meta <- function(
  id,
  title,
  created_at,
  updated_at,
  size_bytes
) {
  list(
    id = id,
    title = title,
    created_at = created_at,
    updated_at = updated_at,
    size_bytes = size_bytes
  )
}

# `size_bytes` is the caller's storage footprint for this record (e.g.
# on-disk bytes, in-memory JSON size) -- required because it depends on the
# backend's storage format, not derivable from the record itself.
record_meta <- function(record, size_bytes) {
  new_conversation_meta(
    id = record$id,
    title = record$title,
    created_at = record$created_at,
    updated_at = record$updated_at,
    size_bytes = size_bytes
  )
}

MIN_SCHEMA_VERSION <- 1L
MAX_SCHEMA_VERSION <- 1L

# NULL means the record predates schema_version and is treated as version 1L.
check_schema_version <- function(version) {
  version <- if (is.null(version)) 1L else version
  is_scalar_integer <- is.integer(version) &&
    length(version) == 1L &&
    !is.na(version)
  if (
    !is_scalar_integer ||
      version < MIN_SCHEMA_VERSION ||
      version > MAX_SCHEMA_VERSION
  ) {
    version_label <- paste(capture.output(dput(version)), collapse = " ")
    rlang::abort(
      paste0(
        "Unsupported conversation record schema version: ",
        version_label,
        " (supported: ",
        MIN_SCHEMA_VERSION,
        "-",
        MAX_SCHEMA_VERSION,
        ")"
      ),
      class = "shinychat_error_unsupported_schema_version"
    )
  }
  as.integer(version)
}

new_conversation_record <- function(title, client_info = list(), id = NULL) {
  now <- utcnow_iso()
  list(
    schema_version = 1L,
    id = id %||% new_conversation_id(),
    title = title,
    # NULL = timestamp-based title, no explicit source yet -- either LLM
    # titling hasn't finished (or was never enabled) or nothing has renamed
    # it. Distinct from "llm"/"user", which are always explicit and final.
    title_source = NULL,
    # Completed-response count for this conversation, incremented once per
    # genuinely-new on_response() call. Drives the "title after the second
    # response" trigger in HistoryController$on_response -- not derived from
    # turn/node counts, since those vary by client and tool-call structure.
    response_count = 0L,
    created_at = now,
    updated_at = now,
    client_info = client_info,
    nodes = list(),
    current_leaf = NULL,
    values = list(),
    bookmark_state_id = NULL
  )
}

record_path_node_ids <- function(record) {
  if (is.null(record$current_leaf)) {
    return(character(0))
  }

  ids <- character(0)
  current <- record$current_leaf
  seen <- character(0)
  while (!is.null(current)) {
    if (current %in% seen) {
      rlang::abort("Cycle detected in conversation node graph")
    }
    seen <- c(seen, current)
    ids <- c(current, ids)
    current <- record$nodes[[current]]$parent
  }
  ids
}

record_path_turns <- function(record) {
  ids <- record_path_node_ids(record)
  unlist(
    lapply(ids, function(id) record$nodes[[id]]$turns),
    recursive = FALSE
  )
}

record_turn_count <- function(record) {
  ids <- record_path_node_ids(record)
  sum(vapply(ids, function(id) length(record$nodes[[id]]$turns), integer(1)))
}

record_ui_count <- function(record) {
  ids <- record_path_node_ids(record)
  sum(vapply(
    ids,
    function(id) length(record$nodes[[id]]$ui),
    integer(1)
  ))
}

record_children_of <- function(record, node_id) {
  if (is.null(node_id)) {
    roots <- names(record$nodes)[
      vapply(record$nodes, function(n) is.null(n$parent), logical(1))
    ]
    if (length(roots) == 0) {
      return(character(0))
    }
    return(roots[order(as.integer(sub("^n_", "", roots)))])
  }
  children <- record$nodes[[node_id]]$children
  if (length(children) == 0) {
    return(character(0))
  }
  unlist(children, use.names = FALSE)
}

record_siblings_of <- function(record, node_id) {
  record_children_of(record, record$nodes[[node_id]]$parent)
}

record_subtree_leaf <- function(record, node_id) {
  children <- record_children_of(record, node_id)
  if (length(children) == 0) {
    return(node_id)
  }
  selected <- record$nodes[[node_id]]$selected_child
  next_id <- if (!is.null(selected) && selected %in% children) {
    selected
  } else {
    children[[length(children)]]
  }
  record_subtree_leaf(record, next_id)
}

# Move the active leaf and record, at every node on the new path, which child
# leads toward it. record_subtree_leaf() replays those pointers so navigating
# back into a sibling subtree returns to the last-viewed descendant. Off-path
# nodes are untouched, so each subtree keeps its own remembered position.
record_set_current_leaf <- function(record, node_id) {
  record$current_leaf <- node_id
  path <- record_path_node_ids(record)
  n <- length(path)
  for (i in seq_along(path)) {
    record$nodes[[path[[i]]]]$selected_child <- if (i < n) {
      path[[i + 1L]]
    } else {
      NULL
    }
  }
  record
}

record_path_sibling_metadata <- function(record) {
  result <- list()
  for (nid in record_path_node_ids(record)) {
    siblings <- record_siblings_of(record, nid)
    if (length(siblings) > 1) {
      result[[nid]] <- list(
        index = match(nid, siblings) - 1L,
        total = length(siblings)
      )
    }
  }
  result
}

# Client-facing message count for a node. Mirrors replay_ui()'s NULL-ui
# fallback: a missing/empty `ui` still renders one fabricated message, so index
# math (record_node_id_for_message_index, send_sibling_metadata) stays aligned
# with what the client reports.
record_ui_message_count <- function(node) {
  if (length(node$ui) > 0) length(node$ui) else 1L
}

record_node_id_for_message_index <- function(record, index) {
  if (index < 0) {
    rlang::abort(paste0("Message index ", index, " out of range"))
  }
  cumulative <- 0L
  for (nid in record_path_node_ids(record)) {
    n_ui <- record_ui_message_count(record$nodes[[nid]])
    if (index < cumulative + n_ui) {
      return(nid)
    }
    cumulative <- cumulative + n_ui
  }
  rlang::abort(paste0("Message index ", index, " out of range"))
}

extend_record_linear <- function(
  record,
  recorded_turns,
  tools
) {
  existing_turn_count <- record_turn_count(record)
  new_turns_recorded <- recorded_turns[
    seq_along(recorded_turns) > existing_turn_count
  ]

  new_turns_live <- lapply(
    new_turns_recorded,
    ellmer::contents_replay,
    tools = tools
  )
  live_groups <- group_ellmer_turns(new_turns_live)

  new_groups <- list()
  cursor <- 0L
  for (i in seq_along(live_groups)) {
    size <- length(live_groups[[i]])
    new_groups[[i]] <- new_turns_recorded[(cursor + 1L):(cursor + size)]
    cursor <- cursor + size
  }

  existing_nums <- as.integer(
    sub("^n_", "", grep("^n_\\d+$", names(record$nodes), value = TRUE))
  )
  seq_start <- if (length(existing_nums) == 0) 1L else max(existing_nums) + 1L

  new_node_ids <- character(0)
  for (i in seq_along(new_groups)) {
    node_id <- sprintf("n_%04d", seq_start + i - 1L)
    record$nodes[[node_id]] <- list(
      parent = record$current_leaf,
      children = list(),
      turns = new_groups[[i]],
      ui = NULL
    )
    if (!is.null(record$current_leaf)) {
      record$nodes[[record$current_leaf]]$children <- c(
        record$nodes[[record$current_leaf]]$children,
        node_id
      )
    }
    record <- record_set_current_leaf(record, node_id)
    new_node_ids <- c(new_node_ids, node_id)
  }

  record$updated_at <- utcnow_iso()
  record
}
