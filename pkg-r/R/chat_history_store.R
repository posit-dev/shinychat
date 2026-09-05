# A storage partition combines the resolved/namespaced chat id with the owner
# scope used by a `ConversationStore`. Not exported: custom `ConversationStore`
# implementations only ever receive a partition from the framework and read
# its `chat_id`/`scope` fields -- they never need to construct one. The
# `shinychat_conversation_partition` class is only checked by partition_key(),
# a private helper used by the built-in stores.
conversation_partition <- function(chat_id, scope) {
  structure(
    list(
      chat_id = as.character(chat_id)[[1L]],
      scope = as.character(scope)[[1L]]
    ),
    class = "shinychat_conversation_partition"
  )
}

partition_key <- function(partition) {
  if (!inherits(partition, "shinychat_conversation_partition")) {
    rlang::abort("`partition` must be a shinychat conversation partition.")
  }
  rlang::hash(list(chat_id = partition$chat_id, scope = partition$scope))
}

#' Abstract base class for conversation storage backends
#'
#' Subclass this to plug a custom persistence backend into
#' [chat_enable_history()] via `history_options(store = )`. All methods
#' are partitioned by a `conversation_partition()` (chat id + owner scope);
#' implementations should not need to know about users, sessions, or Shiny
#' beyond that.
#'
#' A conversation record is a list with fields `schema_version`, `id`,
#' `title`, `title_source` (`"llm"`, `"user"`, or `NULL`), `response_count`,
#' `created_at`, `updated_at` (ISO 8601 strings), `client_info`, `nodes` (a
#' named list of turn nodes forming the conversation tree), `current_leaf`
#' (id of the most recent node, or `NULL`), `values` (the app state dict
#' captured by `on_save`), and `bookmark_state_id`. A conversation meta list
#' is the lightweight summary returned by `list()`: `id`, `title`,
#' `created_at`, `updated_at`, and `size_bytes` (the backend's storage
#' footprint for that conversation, e.g. on-disk bytes).
#'
#' `schema_version` compatibility is enforced by the framework's
#' `HistoryController`, not by this class -- it calls `check_schema_version()`
#' on every record it reads from a store and every record it is about to
#' write, so a custom store doesn't need to check it itself.
#' @export
ConversationStore <- R6::R6Class(
  "ConversationStore",
  public = list(
    #' @description Must be implemented by subclasses. All conversations in
    #'   `partition`, newest-first by `created_at`.
    #' @param partition A `conversation_partition()`.
    #' @returns A list of conversation meta lists.
    list = function(partition) {
      rlang::abort("ConversationStore$list() must be implemented by subclass")
    },
    #' @description Must be implemented by subclasses. The full conversation
    #'   record for `id` in `partition`.
    #' @param partition A `conversation_partition()`.
    #' @param id A conversation id, as found in the `id` field of a
    #'   conversation meta list.
    #' @returns The conversation record, or `NULL` if missing.
    get = function(partition, id) {
      rlang::abort("ConversationStore$get() must be implemented by subclass")
    },
    #' @description Must be implemented by subclasses. Upsert `record` into
    #'   `partition`. A rename is just mutating `record$title` and calling
    #'   `put()` again.
    #' @param partition A `conversation_partition()`.
    #' @param record A conversation record, in the same shape returned by
    #'   `get()`.
    #' @returns `NULL`, invisibly.
    put = function(partition, record) {
      rlang::abort("ConversationStore$put() must be implemented by subclass")
    },
    #' @description Must be implemented by subclasses. Remove the
    #'   conversation `id` from `partition`. Missing ids are a no-op.
    #' @param partition A `conversation_partition()`.
    #' @param id A conversation id, as found in the `id` field of a
    #'   conversation meta list.
    #' @returns `NULL`, invisibly.
    delete = function(partition, id) {
      rlang::abort("ConversationStore$delete() must be implemented by subclass")
    },
    #' @description Case-insensitive substring match of `query` against
    #'   title, over `list(partition)`. Backends don't need to override this
    #'   unless they have a more efficient search path.
    #' @param partition A `conversation_partition()`.
    #' @param query A search string.
    #' @returns A list of conversation meta lists whose title matches `query`.
    search = function(partition, query) {
      all <- self$list(partition)
      query_lower <- tolower(query)
      Filter(
        function(m) grepl(query_lower, tolower(m$title), fixed = TRUE),
        all
      )
    },
    #' @description Total bytes used by all conversations in `partition`,
    #'   derived from `list()`'s per-record `size_bytes`. Backends don't need
    #'   to override this unless they have a cheaper way to compute it.
    #' @param partition A `conversation_partition()`.
    #' @returns The total size in bytes, as a double.
    total_size = function(partition) {
      sum(vapply(self$list(partition), function(m) m$size_bytes, double(1L)))
    }
  )
)

InMemoryConversationStore <- R6::R6Class(
  "InMemoryConversationStore",
  inherit = ConversationStore,
  private = list(
    data = NULL,
    meta_cache = NULL
  ),
  public = list(
    initialize = function() {
      private$data <- list()
      private$meta_cache <- list()
    },
    list = function(partition) {
      key <- partition_key(partition)
      cached <- private$meta_cache[[key]]
      if (!is.null(cached)) {
        return(cached)
      }

      partition_data <- private$data[[key]]
      if (is.null(partition_data) || length(partition_data) == 0) {
        private$meta_cache[[key]] <- list()
        return(list())
      }
      metas <- lapply(partition_data, function(r) {
        record_meta(r, size_bytes = record_json_size(r))
      })
      timestamps <- vapply(metas, function(m) m$created_at, character(1))
      metas <- metas[order(timestamps, decreasing = TRUE)]
      private$meta_cache[[key]] <- metas
      metas
    },
    get = function(partition, id) {
      key <- partition_key(partition)
      private$data[[key]][[id]]
    },
    put = function(partition, record) {
      check_schema_version(record$schema_version)

      key <- partition_key(partition)
      if (is.null(private$data[[key]])) {
        private$data[[key]] <- list()
      }
      private$data[[key]][[record$id]] <- record

      # Only touched-record work -- mirrors FileConversationStore.put(), so
      # a warm cache stays warm without resumming/reserializing everything
      # in a partition (the cost evict_if_needed would otherwise pay every turn).
      cache <- private$meta_cache[[key]]
      if (!is.null(cache)) {
        cache <- Filter(function(m) m$id != record$id, cache)
        cache <- c(
          list(record_meta(record, size_bytes = record_json_size(record))),
          cache
        )
        timestamps <- vapply(cache, function(m) m$created_at, character(1))
        cache <- cache[order(timestamps, decreasing = TRUE)]
        private$meta_cache[[key]] <- cache
      }
      invisible(NULL)
    },
    delete = function(partition, id) {
      key <- partition_key(partition)
      private$data[[key]][[id]] <- NULL

      cache <- private$meta_cache[[key]]
      if (!is.null(cache)) {
        private$meta_cache[[key]] <- Filter(function(m) m$id != id, cache)
      }
      invisible(NULL)
    }
  )
)

record_json_size <- function(record) {
  as.double(nchar(jsonlite::serializeJSON(record), type = "bytes"))
}

history_json <- function(value) {
  as.character(jsonlite::toJSON(
    value,
    auto_unbox = TRUE,
    null = "null",
    digits = 17,
    # Unclass shinychat_block segments (and any other classed values hiding
    # at any depth) so asJSON dispatch doesn't fail on them.
    force = TRUE
  ))
}

history_json_digest <- function(value) {
  rlang::hash(history_json(value))
}

history_warn_malformed_jsonl <- function(path, line_number, reason) {
  rlang::warn(paste0(
    "Skipping malformed JSONL line ",
    path,
    ":",
    line_number,
    ": ",
    reason
  ))
}

history_parse_jsonl_line <- function(line, path, line_number) {
  tryCatch(
    jsonlite::fromJSON(line, simplifyVector = FALSE),
    error = function(e) {
      history_warn_malformed_jsonl(path, line_number, conditionMessage(e))
      NULL
    }
  )
}

history_append_jsonl <- function(path, lines) {
  if (length(lines) > 0) {
    cat(
      paste0(lines, collapse = "\n"),
      "\n",
      file = path,
      sep = "",
      append = TRUE
    )
  } else if (!file.exists(path)) {
    file.create(path)
  }
  invisible(NULL)
}

history_rollback_jsonl <- function(path, existed, size) {
  if (!existed) {
    unlink(path)
    return(invisible(NULL))
  }
  con <- file(path, open = "r+b")
  on.exit(close(con), add = TRUE)
  seek(con, where = size, origin = "start")
  truncate(con)
  invisible(NULL)
}

history_write_temp_record <- function(json, path) {
  writeLines(json, path)
  invisible(NULL)
}

CONV_ID_RE <- "^[A-Za-z0-9_-]{1,80}$"

sanitize_scope <- function(scope) {
  sanitized <- gsub("[^A-Za-z0-9_-]", "_", scope)
  sanitized <- substr(sanitized, 1, 40)
  hash <- substr(rlang::hash(scope), 1, 12)
  paste0(sanitized, "-", hash)
}

safe_conv_path <- function(scope_dir, conv_id) {
  if (!grepl(CONV_ID_RE, conv_id)) {
    rlang::abort(paste0("Invalid conversation ID: ", conv_id))
  }
  file.path(scope_dir, conv_id)
}

resolve_history_dir <- function() {
  connect_dir <- Sys.getenv("CONNECT_CONTENT_DATA_DIR", "")
  if (nzchar(connect_dir)) {
    return(file.path(connect_dir, "shinychat-conversations"))
  }

  # server.bookmark.dir is how Posit Connect supplies a persistent dir
  bookmark_fn <- shiny::getShinyOption("server.bookmark.dir", NULL)
  if (is.function(bookmark_fn)) {
    dir <- tryCatch(
      bookmark_fn("shinychat-conversations"),
      error = function(e) NULL
    )
    if (!is.null(dir)) return(dir)
  }

  file.path(".shinychat", "conversations")
}

#' File-based conversation storage backend
#'
#' Uses temporary records and journal rollback to protect against ordinary I/O
#' failures, but does not fsync files or directories. This store also does not
#' coordinate concurrent access across processes; callers must serialize reads
#' and writes for each conversation.
#' @export
FileConversationStore <- R6::R6Class(
  "FileConversationStore",
  inherit = ConversationStore,
  private = list(
    dir = NULL,
    meta_cache = NULL,
    write_state = NULL,

    partition_dir = function(partition) {
      if (is.null(private$dir)) {
        private$dir <- resolve_history_dir()
      }
      file.path(
        private$dir,
        sanitize_scope(partition$chat_id),
        sanitize_scope(partition$scope)
      )
    },

    ws_key = function(partition, id) paste0(partition_key(partition), ":", id),

    get_or_init_write_state = function(partition, id, cdir) {
      key <- private$ws_key(partition, id)
      cached <- private$write_state[[key]]
      if (!is.null(cached)) {
        return(cached)
      }

      ws <- list(
        turn_seq_map = list(),
        ui_node_digest = list(),
        next_turn_seq = 0L
      )

      turns_file <- file.path(cdir, "turns.jsonl")
      if (file.exists(turns_file)) {
        lines <- readLines(turns_file, warn = FALSE)
        ws$next_turn_seq <- length(lines[nzchar(lines)])
      }

      record_file <- file.path(cdir, "record.json")
      if (file.exists(record_file)) {
        raw <- jsonlite::fromJSON(record_file, simplifyVector = FALSE)
        for (nid in names(raw$nodes)) {
          turn_ids <- raw$nodes[[nid]]$turn_ids
          if (length(turn_ids) > 0) {
            ws$turn_seq_map[[nid]] <- turn_ids
          }
        }
      }

      ui_file <- file.path(cdir, "ui.jsonl")
      if (file.exists(ui_file)) {
        for (line_number in seq_along(
          lines <- readLines(ui_file, warn = FALSE)
        )) {
          line <- lines[[line_number]]
          if (!nzchar(line)) {
            next
          }
          entry <- history_parse_jsonl_line(line, ui_file, line_number)
          if (
            is.null(entry) ||
              !is.list(entry) ||
              !is.character(entry$node_id) ||
              length(entry$node_id) != 1L ||
              !is.list(entry$data)
          ) {
            if (!is.null(entry)) {
              history_warn_malformed_jsonl(
                ui_file,
                line_number,
                "expected node_id and data"
              )
            }
            next
          }
          ws$ui_node_digest[[entry$node_id]] <- history_json_digest(entry$data)
        }
      }

      private$write_state[[key]] <- ws
      ws
    }
  ),
  public = list(
    #' @description Create a new file-based conversation store.
    #' @param dir Directory to store conversations under. Defaults to
    #'   `NULL`, which resolves a redeploy-safe location at first use (see
    #'   `resolve_history_dir()`).
    initialize = function(dir = NULL) {
      private$dir <- dir
      private$meta_cache <- list()
      private$write_state <- list()
    },

    #' @description All conversations in `partition`, newest-first by
    #'   `created_at`, read from one `record.json` per conversation directory
    #'   on disk.
    #' @param partition A `conversation_partition()`.
    #' @returns A list of conversation meta lists.
    list = function(partition) {
      key <- partition_key(partition)
      cached <- private$meta_cache[[key]]
      if (!is.null(cached)) {
        return(cached)
      }

      pdir <- private$partition_dir(partition)
      if (!dir.exists(pdir)) {
        private$meta_cache[[key]] <- list()
        return(list())
      }

      conv_dirs <- list.dirs(pdir, full.names = TRUE, recursive = FALSE)
      metas <- Filter(
        Negate(is.null),
        lapply(conv_dirs, function(d) {
          record_file <- file.path(d, "record.json")
          if (!file.exists(record_file)) {
            return(NULL)
          }
          tryCatch(
            {
              raw <- jsonlite::fromJSON(record_file, simplifyVector = FALSE)
              check_schema_version(raw$schema_version)
              size_bytes <- sum(vapply(
                list.files(d, full.names = TRUE),
                function(f) as.double(file.size(f)),
                double(1)
              ))
              record_meta(raw, size_bytes = size_bytes)
            },
            # An unsupported schema version is skipped like any other
            # unreadable record, rather than failing the whole partition --
            # one incompatible conversation (e.g. written by a newer
            # shinychat) shouldn't hide every other conversation in the list.
            error = function(e) {
              rlang::warn(paste0(
                "Skipping unreadable conversation ",
                basename(d),
                ": ",
                conditionMessage(e)
              ))
              NULL
            }
          )
        })
      )
      timestamps <- vapply(metas, function(m) m$created_at, character(1))
      metas <- metas[order(timestamps, decreasing = TRUE)]
      private$meta_cache[[key]] <- metas
      metas
    },

    #' @description The full conversation record for `id` in `partition`,
    #'   reassembled from `record.json`, `turns.jsonl`, and `ui.jsonl`.
    #' @param partition A `conversation_partition()`.
    #' @param id A conversation id, as found in the `id` field of a
    #'   conversation meta list.
    #' @returns The conversation record, or `NULL` if missing.
    get = function(partition, id) {
      cdir <- safe_conv_path(private$partition_dir(partition), id)
      record_file <- file.path(cdir, "record.json")
      if (!file.exists(record_file)) {
        return(NULL)
      }
      raw <- jsonlite::fromJSON(record_file, simplifyVector = FALSE)
      schema_version <- check_schema_version(raw$schema_version)

      turns_map <- list()
      turns_file <- file.path(cdir, "turns.jsonl")
      if (file.exists(turns_file)) {
        lines <- readLines(turns_file, warn = FALSE)
        for (line_number in seq_along(lines)) {
          line <- lines[[line_number]]
          if (!nzchar(line)) {
            next
          }
          entry <- history_parse_jsonl_line(line, turns_file, line_number)
          if (
            is.null(entry) ||
              !is.list(entry) ||
              !is.numeric(entry$seq) ||
              length(entry$seq) != 1L ||
              is.na(entry$seq) ||
              !is.character(entry$data) ||
              length(entry$data) != 1L
          ) {
            if (!is.null(entry)) {
              history_warn_malformed_jsonl(
                turns_file,
                line_number,
                "expected seq and serialized data"
              )
            }
            next
          }
          turn <- tryCatch(
            jsonlite::unserializeJSON(entry$data),
            error = function(e) {
              history_warn_malformed_jsonl(
                turns_file,
                line_number,
                conditionMessage(e)
              )
              NULL
            }
          )
          if (!is.null(turn)) {
            turns_map[[as.character(entry$seq)]] <- turn
          }
        }
      }

      ui_map <- list()
      ui_file <- file.path(cdir, "ui.jsonl")
      if (file.exists(ui_file)) {
        lines <- readLines(ui_file, warn = FALSE)
        for (line_number in seq_along(lines)) {
          line <- lines[[line_number]]
          if (!nzchar(line)) {
            next
          }
          entry <- history_parse_jsonl_line(line, ui_file, line_number)
          if (
            is.null(entry) ||
              !is.list(entry) ||
              !is.character(entry$node_id) ||
              length(entry$node_id) != 1L ||
              !is.list(entry$data)
          ) {
            if (!is.null(entry)) {
              history_warn_malformed_jsonl(
                ui_file,
                line_number,
                "expected node_id and data"
              )
            }
            next
          }
          ui_map[[entry$node_id]] <- entry$data
        }
      }

      nodes <- list()
      for (nid in names(raw$nodes)) {
        node_data <- raw$nodes[[nid]]
        turn_ids_present <- Filter(
          function(tid) !is.null(turns_map[[as.character(tid)]]),
          node_data$turn_ids
        )
        turns <- lapply(turn_ids_present, function(tid) {
          turns_map[[as.character(tid)]]
        })
        nodes[[nid]] <- list(
          parent = node_data$parent,
          children = node_data$children,
          turns = turns,
          ui = ui_map[[nid]],
          selected_child = node_data$selected_child
        )
      }

      list(
        schema_version = schema_version,
        id = raw$id,
        title = raw$title,
        title_source = raw$title_source,
        response_count = raw$response_count,
        created_at = raw$created_at,
        updated_at = raw$updated_at,
        client_info = raw$client_info,
        current_leaf = raw$current_leaf,
        nodes = nodes,
        values = raw$values,
        bookmark_state_id = raw$bookmark_state_id
      )
    },

    #' @description Upsert `record` into `partition`, appending new turns and
    #'   UI data to `turns.jsonl`/`ui.jsonl` and rewriting `record.json`.
    #' @param partition A `conversation_partition()`.
    #' @param record A conversation record, in the same shape returned by
    #'   `get()`.
    #' @returns `NULL`, invisibly.
    put = function(partition, record) {
      check_schema_version(record$schema_version)

      key <- partition_key(partition)
      cdir <- safe_conv_path(private$partition_dir(partition), record$id)
      record_file <- file.path(cdir, "record.json")
      # Check the on-disk schema version before creating any directory or
      # touching any file -- a rejection here must leave the filesystem
      # untouched.
      if (file.exists(record_file) && !dir.exists(record_file)) {
        existing_raw <- jsonlite::fromJSON(record_file, simplifyVector = FALSE)
        check_schema_version(existing_raw$schema_version)
      }
      dir.create(cdir, recursive = TRUE, showWarnings = FALSE)

      ws_key <- private$ws_key(partition, record$id)
      had_write_state <- !is.null(private$write_state[[ws_key]])
      ws <- private$get_or_init_write_state(partition, record$id, cdir)
      staged_ws <- unserialize(serialize(ws, NULL))

      new_turns_lines <- character(0)
      new_ui_lines <- character(0)
      record_nodes <- list()

      for (nid in names(record$nodes)) {
        node <- record$nodes[[nid]]

        if (is.null(staged_ws$turn_seq_map[[nid]])) {
          turn_ids <- list()
          for (turn_data in node$turns) {
            seq <- staged_ws$next_turn_seq
            staged_ws$next_turn_seq <- staged_ws$next_turn_seq + 1L
            turn_ids <- c(turn_ids, seq)
            new_turns_lines <- c(
              new_turns_lines,
              history_json(
                list(
                  seq = seq,
                  data = jsonlite::serializeJSON(turn_data, digits = 17)
                )
              )
            )
          }
          staged_ws$turn_seq_map[[nid]] <- turn_ids
        }

        if (!is.null(node$ui)) {
          ui_digest <- history_json_digest(node$ui)
          if (!identical(ui_digest, staged_ws$ui_node_digest[[nid]])) {
            new_ui_lines <- c(
              new_ui_lines,
              history_json(list(node_id = nid, data = node$ui))
            )
            staged_ws$ui_node_digest[[nid]] <- ui_digest
          }
        }

        record_nodes[[nid]] <- list(
          parent = node$parent,
          children = node$children,
          turn_ids = staged_ws$turn_seq_map[[nid]],
          selected_child = node$selected_child
        )
      }

      record_data <- list(
        schema_version = record$schema_version,
        id = record$id,
        title = record$title,
        title_source = record$title_source,
        response_count = record$response_count,
        created_at = record$created_at,
        updated_at = record$updated_at,
        client_info = record$client_info,
        current_leaf = record$current_leaf,
        nodes = record_nodes,
        values = record$values,
        bookmark_state_id = record$bookmark_state_id
      )
      json <- history_json(record_data)

      turns_file <- file.path(cdir, "turns.jsonl")
      ui_file <- file.path(cdir, "ui.jsonl")
      snapshots <- lapply(
        list(turns_file, ui_file),
        function(path) {
          existed <- file.exists(path)
          list(
            path = path,
            existed = existed,
            size = if (existed) file.size(path) else 0
          )
        }
      )
      tmp <- tempfile(tmpdir = cdir, fileext = ".json.tmp")
      committed <- FALSE
      on.exit(
        {
          if (!committed) {
            for (snapshot in rev(snapshots)) {
              history_rollback_jsonl(
                snapshot$path,
                snapshot$existed,
                snapshot$size
              )
            }
            unlink(tmp)
            if (!had_write_state) {
              private$write_state[[ws_key]] <- NULL
            }
          }
        },
        add = TRUE
      )

      # Write and validate the replacement record before appending journals.
      history_write_temp_record(json, tmp)
      history_append_jsonl(turns_file, new_turns_lines)
      history_append_jsonl(ui_file, new_ui_lines)
      ok <- file_move(tmp, record_file)
      if (!isTRUE(ok)) {
        rlang::abort(paste0("Failed to write conversation: ", cdir))
      }
      committed <- TRUE
      private$write_state[[ws_key]] <- staged_ws

      cache <- private$meta_cache[[key]]
      if (!is.null(cache)) {
        size_bytes <- sum(vapply(
          list.files(cdir, full.names = TRUE),
          function(f) as.double(file.size(f)),
          double(1)
        ))
        cache <- Filter(function(m) m$id != record$id, cache)
        cache <- c(list(record_meta(record, size_bytes = size_bytes)), cache)
        timestamps <- vapply(cache, function(m) m$created_at, character(1))
        cache <- cache[order(timestamps, decreasing = TRUE)]
        private$meta_cache[[key]] <- cache
      }

      invisible(NULL)
    },

    #' @description Remove the conversation `id` from `partition` by deleting
    #'   its directory. Missing ids are a no-op.
    #' @param partition A `conversation_partition()`.
    #' @param id A conversation id, as found in the `id` field of a
    #'   conversation meta list.
    #' @returns `NULL`, invisibly.
    delete = function(partition, id) {
      key <- partition_key(partition)
      cdir <- safe_conv_path(private$partition_dir(partition), id)
      if (dir.exists(cdir)) {
        unlink(cdir, recursive = TRUE)
      }
      private$write_state[[private$ws_key(partition, id)]] <- NULL

      cache <- private$meta_cache[[key]]
      if (!is.null(cache)) {
        private$meta_cache[[key]] <- Filter(function(m) m$id != id, cache)
      }
      invisible(NULL)
    }
  )
)

auto_dev_memory_store_env <- new.env(parent = emptyenv())

auto_dev_memory_store <- function() {
  store <- auto_dev_memory_store_env[["store"]]
  if (is.null(store)) {
    store <- InMemoryConversationStore$new()
    auto_dev_memory_store_env[["store"]] <- store
  }
  store
}

resolve_store <- function(store) {
  if (inherits(store, "ConversationStore")) {
    return(store)
  }

  store <- match.arg(store, c("auto", "memory", "file"))
  quiet <- getOption(
    "shinychat.history_options.store_auto.quiet",
    default = identical(Sys.getenv("TESTTHAT"), "true")
  )
  quiet_hint <- c(
    i = "Set {.code options(shinychat.history_options.store_auto.quiet = TRUE)} to silence this message."
  )
  switch(
    store,
    auto = {
      if (shiny::in_devmode()) {
        if (!quiet) {
          cli::cli_inform(
            c(
              "Chat history: using in-memory storage (dev mode). History is lost on restart. To persist across restarts, use {.code history_options(store = \"file\")}.",
              quiet_hint
            ),
            .frequency = "once",
            .frequency_id = "shinychat_store_auto_memory"
          )
        }
        auto_dev_memory_store()
      } else {
        if (!quiet) {
          cli::cli_inform(
            c(
              "Chat history: using file-based storage. To use in-memory storage instead, use {.code history_options(store = \"memory\")}.",
              quiet_hint
            ),
            .frequency = "once",
            .frequency_id = "shinychat_store_auto_file"
          )
        }
        FileConversationStore$new()
      }
    },
    memory = InMemoryConversationStore$new(),
    file = FileConversationStore$new()
  )
}
