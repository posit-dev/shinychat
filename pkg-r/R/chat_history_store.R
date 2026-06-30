#' Abstract base class for conversation storage backends
#' @export
ConversationStore <- R6::R6Class(
  "ConversationStore",
  public = list(
    list = function(scope) {
      rlang::abort("ConversationStore$list() must be implemented by subclass")
    },
    get = function(scope, id) {
      rlang::abort("ConversationStore$get() must be implemented by subclass")
    },
    put = function(scope, record) {
      rlang::abort("ConversationStore$put() must be implemented by subclass")
    },
    delete = function(scope, id) {
      rlang::abort("ConversationStore$delete() must be implemented by subclass")
    },
    search = function(scope, query) {
      all <- self$list(scope)
      query_lower <- tolower(query)
      Filter(
        function(m) grepl(query_lower, tolower(m$title), fixed = TRUE),
        all
      )
    },
    # Derived from list()'s per-record size_bytes -- backends don't need to
    # override this unless they have a cheaper way to compute it.
    total_size = function(scope) {
      sum(vapply(self$list(scope), function(m) m$size_bytes, double(1L)))
    }
  )
)

InMemoryConversationStore <- R6::R6Class(
  "InMemoryConversationStore",
  inherit = ConversationStore,
  private = list(
    data = NULL
  ),
  public = list(
    initialize = function() {
      private$data <- list()
    },
    list = function(scope) {
      scope_data <- private$data[[scope]]
      if (is.null(scope_data) || length(scope_data) == 0) {
        return(list())
      }
      metas <- lapply(scope_data, function(r) {
        record_meta(r, size_bytes = record_json_size(r))
      })
      timestamps <- vapply(metas, function(m) m$updated_at, character(1))
      metas[order(timestamps, decreasing = TRUE)]
    },
    get = function(scope, id) {
      private$data[[scope]][[id]]
    },
    put = function(scope, record) {
      if (is.null(private$data[[scope]])) {
        private$data[[scope]] <- list()
      }
      private$data[[scope]][[record$id]] <- record
      invisible(NULL)
    },
    delete = function(scope, id) {
      private$data[[scope]][[id]] <- NULL
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
  file.path(scope_dir, paste0(conv_id, ".json"))
}

resolve_history_dir <- function() {
  connect_dir <- Sys.getenv("CONNECT_CONTENT_DATA_DIR", "")
  if (nzchar(connect_dir)) {
    return(file.path(connect_dir, "shinychat-conversations"))
  }

  # Try Shiny's bookmark save dir (Connect-aware)
  bookmark_fn <- shiny::getShinyOption("server.bookmark.dir", NULL)
  if (is.function(bookmark_fn)) {
    dir <- tryCatch(
      bookmark_fn("shinychat-conversations"),
      error = function(e) NULL
    )
    if (!is.null(dir)) return(dir)
  }

  # Local fallback
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

    scope_dir = function(scope) {
      if (is.null(private$dir)) {
        private$dir <- resolve_history_dir()
      }
      file.path(private$dir, sanitize_scope(scope))
    }
  ),
  public = list(
    initialize = function(dir = NULL) {
      private$dir <- dir
      private$meta_cache <- list()
    },

    list = function(scope) {
      cached <- private$meta_cache[[scope]]
      if (!is.null(cached)) {
        return(cached)
      }

      sdir <- private$scope_dir(scope)
      if (!dir.exists(sdir)) {
        private$meta_cache[[scope]] <- list()
        return(list())
      }

      files <- list.files(sdir, pattern = "\\.json$", full.names = TRUE)
      metas <- Filter(
        Negate(is.null),
        lapply(files, function(f) {
          tryCatch(
            record_meta(
              jsonlite::fromJSON(f, simplifyVector = FALSE),
              size_bytes = as.double(file.size(f))
            ),
            error = function(e) {
              rlang::warn(
                paste0(
                  "Skipping unreadable conversation file ",
                  basename(f),
                  ": ",
                  conditionMessage(e)
                )
              )
              NULL
            }
          )
        })
      )
      timestamps <- vapply(metas, function(m) m$updated_at, character(1))
      metas <- metas[order(timestamps, decreasing = TRUE)]
      private$meta_cache[[scope]] <- metas
      metas
    },

    get = function(scope, id) {
      path <- safe_conv_path(private$scope_dir(scope), id)
      if (!file.exists(path)) {
        return(NULL)
      }
      jsonlite::fromJSON(path, simplifyVector = FALSE)
    },

    put = function(scope, record) {
      sdir <- private$scope_dir(scope)
      dir.create(sdir, recursive = TRUE, showWarnings = FALSE)

      path <- safe_conv_path(sdir, record$id)
      json <- jsonlite::toJSON(record, auto_unbox = TRUE, null = "null")
      tmp <- tempfile(tmpdir = sdir, fileext = ".json.tmp")
      on.exit(unlink(tmp), add = TRUE)
      writeLines(json, tmp)
      ok <- suppressWarnings(file.rename(tmp, path))
      if (!isTRUE(ok)) {
        rlang::abort(paste0("Failed to write conversation: ", path))
      }

      # Update cache
      cache <- private$meta_cache[[scope]]
      if (!is.null(cache)) {
        cache <- Filter(function(m) m$id != record$id, cache)
        cache <- c(
          list(record_meta(record, size_bytes = as.double(file.size(path)))),
          cache
        )
        timestamps <- vapply(cache, function(m) m$updated_at, character(1))
        cache <- cache[order(timestamps, decreasing = TRUE)]
        private$meta_cache[[scope]] <- cache
      }

      invisible(NULL)
    },

    delete = function(scope, id) {
      path <- safe_conv_path(private$scope_dir(scope), id)
      unlink(path)

      cache <- private$meta_cache[[scope]]
      if (!is.null(cache)) {
        private$meta_cache[[scope]] <- Filter(function(m) m$id != id, cache)
      }
      invisible(NULL)
    }
  )
)

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
        InMemoryConversationStore$new()
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
