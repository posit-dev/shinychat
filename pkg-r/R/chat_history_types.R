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

new_conversation_meta <- function(id, title, created_at, updated_at) {
  list(
    id = id,
    title = title,
    created_at = created_at,
    updated_at = updated_at
  )
}

record_meta <- function(record) {
  new_conversation_meta(
    id = record$id,
    title = record$title,
    created_at = record$created_at,
    updated_at = record$updated_at
  )
}

new_conversation_record <- function(title, client_info = list()) {
  now <- utcnow_iso()
  list(
    schema_version = 1L,
    id = new_conversation_id(),
    title = title,
    title_source = "fallback",
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
  lapply(ids, function(id) {
    turn <- record$nodes[[id]]$turn
    # Turns are stored as JSON strings (via serializeJSON) to preserve types
    # across the jsonlite::toJSON/fromJSON round-trip used by FileConversationStore.
    if (is.character(turn)) jsonlite::unserializeJSON(turn) else turn
  })
}

extend_record_linear <- function(record, recorded_turns) {
  existing_count <- length(record_path_node_ids(record))
  new_turns <- recorded_turns[seq_along(recorded_turns) > existing_count]
  if (length(new_turns) == 0) {
    return(record)
  }

  existing_nums <- as.integer(
    sub("^n_", "", grep("^n_\\d+$", names(record$nodes), value = TRUE))
  )
  seq_start <- if (length(existing_nums) == 0) 1L else max(existing_nums) + 1L

  for (i in seq_along(new_turns)) {
    node_id <- sprintf("n_%04d", seq_start + i - 1L)
    record$nodes[[node_id]] <- list(
      parent = record$current_leaf,
      turn = jsonlite::serializeJSON(new_turns[[i]])
    )
    record$current_leaf <- node_id
  }

  record$updated_at <- utcnow_iso()
  record
}
