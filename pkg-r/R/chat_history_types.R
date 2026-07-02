messages_input_value <- function(value) {
  if (!is.list(value)) {
    rlang::abort(paste0(
      "Expected a list from shinychat.messages, got ",
      class(value)[1]
    ))
  }
  lapply(value, function(m) {
    message <- list(
      role = m$role,
      segments = lapply(m$segments, function(s) {
        list(content = s$content, content_type = s$content_type)
      })
    )
    if (!is.null(m$htmlDeps)) {
      message$htmlDeps <- m$htmlDeps
    }
    if (!is.null(m$attachments) && length(m$attachments) > 0) {
      validate_attachments(m$attachments)
      message$attachments <- m$attachments
    }
    message
  })
}

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

new_conversation_record <- function(title, client_info = list()) {
  now <- utcnow_iso()
  list(
    schema_version = 1L,
    id = new_conversation_id(),
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

extend_record_linear <- function(record, recorded_turns, ui_messages, ui_offset, tools) {
  existing_turn_count <- record_turn_count(record)
  new_turns_recorded <- recorded_turns[seq_along(recorded_turns) > existing_turn_count]

  new_turns_live <- lapply(new_turns_recorded, ellmer::contents_replay, tools = tools)
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
    record$current_leaf <- node_id
    new_node_ids <- c(new_node_ids, node_id)
  }

  user_node_ids <- new_node_ids[
    vapply(
      seq_along(live_groups),
      function(i) identical(ellmer_turn_effective_role(live_groups[[i]][[1]]), "user"),
      logical(1)
    )
  ]

  fallback <- if (length(new_node_ids) > 0) {
    new_node_ids[length(new_node_ids)]
  } else {
    record$current_leaf
  }

  if (!is.null(fallback)) {
    new_messages <- ui_messages[seq_along(ui_messages) > ui_offset]
    for (message in new_messages) {
      if (identical(message$role, "user") && length(user_node_ids) > 0) {
        target <- user_node_ids[[1]]
        user_node_ids <- user_node_ids[-1]
      } else {
        target <- fallback
      }
      record$nodes[[target]]$ui <- c(record$nodes[[target]]$ui, list(message))
    }
  }

  record$updated_at <- utcnow_iso()
  record
}
