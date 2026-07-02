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
#' @export
ConversationStore <- R6::R6Class(
  "ConversationStore",
  public = list(
    #' @description Must be implemented by subclasses. All conversations in
    #'   `partition`, newest-first by `updated_at`.
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
      timestamps <- vapply(metas, function(m) m$updated_at, character(1))
      metas <- metas[order(timestamps, decreasing = TRUE)]
      private$meta_cache[[key]] <- metas
      metas
    },
    get = function(partition, id) {
      key <- partition_key(partition)
      private$data[[key]][[id]]
    },
    put = function(partition, record) {
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
        timestamps <- vapply(cache, function(m) m$updated_at, character(1))
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
  as.double(nchar(jsonlite::toJSON(record, auto_unbox = TRUE), type = "bytes"))
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

      ws <- list(turn_seq_map = list(), ui_node_len = list(), next_turn_seq = 0L)

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
        for (line in readLines(ui_file, warn = FALSE)) {
          if (!nzchar(line)) next
          entry <- tryCatch(
            jsonlite::fromJSON(line, simplifyVector = FALSE),
            error = function(e) NULL
          )
          if (!is.null(entry)) {
            ws$ui_node_len[[entry$node_id]] <- length(entry$data)
          }
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
              size_bytes <- sum(vapply(
                list.files(d, full.names = TRUE),
                function(f) as.double(file.size(f)),
                double(1)
              ))
              record_meta(raw, size_bytes = size_bytes)
            },
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
      timestamps <- vapply(metas, function(m) m$updated_at, character(1))
      metas <- metas[order(timestamps, decreasing = TRUE)]
      private$meta_cache[[key]] <- metas
      metas
    },

    get = function(partition, id) {
      cdir <- safe_conv_path(private$partition_dir(partition), id)
      record_file <- file.path(cdir, "record.json")
      if (!file.exists(record_file)) {
        return(NULL)
      }
      raw <- jsonlite::fromJSON(record_file, simplifyVector = FALSE)

      turns_map <- list()
      turns_file <- file.path(cdir, "turns.jsonl")
      if (file.exists(turns_file)) {
        for (line in readLines(turns_file, warn = FALSE)) {
          if (!nzchar(line)) next
          entry <- tryCatch(
            jsonlite::fromJSON(line, simplifyVector = FALSE),
            error = function(e) NULL
          )
          if (!is.null(entry)) {
            turns_map[[as.character(entry$seq)]] <- entry$data
          }
        }
      }

      ui_map <- list()
      ui_file <- file.path(cdir, "ui.jsonl")
      if (file.exists(ui_file)) {
        for (line in readLines(ui_file, warn = FALSE)) {
          if (!nzchar(line)) next
          entry <- tryCatch(
            jsonlite::fromJSON(line, simplifyVector = FALSE),
            error = function(e) NULL
          )
          if (!is.null(entry)) {
            ui_map[[entry$node_id]] <- entry$data
          }
        }
      }

      nodes <- list()
      for (nid in names(raw$nodes)) {
        node_data <- raw$nodes[[nid]]
        turn_ids_present <- Filter(
          function(tid) !is.null(turns_map[[as.character(tid)]]),
          node_data$turn_ids
        )
        turns <- lapply(turn_ids_present, function(tid) turns_map[[as.character(tid)]])
        nodes[[nid]] <- list(
          parent = node_data$parent,
          children = node_data$children,
          turns = turns,
          ui = ui_map[[nid]]
        )
      }

      list(
        schema_version = raw$schema_version,
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

    put = function(partition, record) {
      key <- partition_key(partition)
      cdir <- safe_conv_path(private$partition_dir(partition), record$id)
      dir.create(cdir, recursive = TRUE, showWarnings = FALSE)

      ws <- private$get_or_init_write_state(partition, record$id, cdir)

      new_turns_lines <- character(0)
      new_ui_lines <- character(0)
      record_nodes <- list()

      for (nid in names(record$nodes)) {
        node <- record$nodes[[nid]]

        if (is.null(ws$turn_seq_map[[nid]])) {
          turn_ids <- list()
          for (turn_data in node$turns) {
            seq <- ws$next_turn_seq
            ws$next_turn_seq <- ws$next_turn_seq + 1L
            turn_ids <- c(turn_ids, seq)
            new_turns_lines <- c(
              new_turns_lines,
              as.character(jsonlite::toJSON(
                list(seq = seq, data = turn_data),
                auto_unbox = TRUE,
                null = "null"
              ))
            )
          }
          ws$turn_seq_map[[nid]] <- turn_ids
        }

        ui_len <- length(node$ui)
        if (!is.null(node$ui) && !identical(ui_len, ws$ui_node_len[[nid]])) {
          new_ui_lines <- c(
            new_ui_lines,
            as.character(jsonlite::toJSON(
              list(node_id = nid, data = node$ui),
              auto_unbox = TRUE,
              null = "null"
            ))
          )
          ws$ui_node_len[[nid]] <- ui_len
        }

        record_nodes[[nid]] <- list(
          parent = node$parent,
          children = node$children,
          turn_ids = ws$turn_seq_map[[nid]]
        )
      }

      turns_file <- file.path(cdir, "turns.jsonl")
      if (length(new_turns_lines) > 0) {
        cat(paste0(new_turns_lines, collapse = "\n"), "\n", file = turns_file, sep = "", append = TRUE)
      } else if (!file.exists(turns_file)) {
        file.create(turns_file)
      }

      ui_file <- file.path(cdir, "ui.jsonl")
      if (length(new_ui_lines) > 0) {
        cat(paste0(new_ui_lines, collapse = "\n"), "\n", file = ui_file, sep = "", append = TRUE)
      } else if (!file.exists(ui_file)) {
        file.create(ui_file)
      }

      private$write_state[[private$ws_key(partition, record$id)]] <- ws

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
      json <- jsonlite::toJSON(record_data, auto_unbox = TRUE, null = "null")
      tmp <- tempfile(tmpdir = cdir, fileext = ".json.tmp")
      on.exit(unlink(tmp), add = TRUE)
      writeLines(json, tmp)
      ok <- file_move(tmp, file.path(cdir, "record.json"))
      if (!isTRUE(ok)) {
        rlang::abort(paste0("Failed to write conversation: ", cdir))
      }

      cache <- private$meta_cache[[key]]
      if (!is.null(cache)) {
        size_bytes <- sum(vapply(
          list.files(cdir, full.names = TRUE),
          function(f) as.double(file.size(f)),
          double(1)
        ))
        cache <- Filter(function(m) m$id != record$id, cache)
        cache <- c(list(record_meta(record, size_bytes = size_bytes)), cache)
        timestamps <- vapply(cache, function(m) m$updated_at, character(1))
        cache <- cache[order(timestamps, decreasing = TRUE)]
        private$meta_cache[[key]] <- cache
      }

      invisible(NULL)
    },

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
  switch(
    store,
    auto = {
      if (shiny::in_devmode()) {
        cli::cli_inform(
          "Chat history: using in-memory storage (dev mode). History is lost on restart. To persist across restarts, use {.code history_options(store = \"file\")}.",
          .frequency = "once",
          .frequency_id = "shinychat_store_auto_memory"
        )
        auto_dev_memory_store()
      } else {
        cli::cli_inform(
          "Chat history: using file-based storage. To use in-memory storage instead, use {.code history_options(store = \"memory\")}.",
          .frequency = "once",
          .frequency_id = "shinychat_store_auto_file"
        )
        FileConversationStore$new()
      }
    },
    memory = InMemoryConversationStore$new(),
    file = FileConversationStore$new()
  )
}
