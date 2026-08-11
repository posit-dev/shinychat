extract_state_id <- function(url) {
  m <- regmatches(
    url,
    regexpr("[?&]_state_id_=([A-Za-z0-9_-]+)", url, perl = TRUE)
  )
  if (length(m) == 0 || !nzchar(m)) {
    return(NULL)
  }
  sub("^[^=]+=", "", m)
}

delete_bookmark_state <- function(state_id) {
  if (!grepl("^[A-Za-z0-9_-]+$", state_id)) {
    return(invisible())
  }
  for (state_path in bookmark_state_paths(state_id)) {
    if (dir.exists(state_path)) {
      unlink(state_path, recursive = TRUE)
    }
  }
  invisible()
}

get_reported_messages <- function(session, chat_id) {
  value <- shiny::isolate(session$input[[paste0(chat_id, "_messages")]])
  if (is.null(value)) list() else value
}

bookmark_state_paths <- function(state_id) {
  app_dir <- shiny::getShinyOption("appDir", default = getwd())
  paths <- file.path(app_dir, "shiny_bookmarks", state_id)

  legacy_dir <- shiny::getShinyOption("bookmarkSaveDir", default = NULL)
  if (!is.null(legacy_dir)) {
    paths <- c(paths, file.path(legacy_dir, state_id))
  }

  unique(paths)
}

HistoryController <- R6::R6Class(
  "HistoryController",
  public = list(
    partition = NULL,
    record = NULL,
    ui_offset = 0,
    is_replaying = FALSE,
    suppress_next_save = FALSE,
    on_active_id_change = NULL,
    on_response_saved = NULL,
    on_pre_switch = NULL,
    on_evict = NULL,

    initialize = function(
      chat_id,
      client,
      options,
      session
    ) {
      title <- options$title
      private$store <- resolve_store(options$store)
      private$chat_id <- chat_id
      private$client <- client
      private$title_fn <- if (is.function(title)) title else NULL
      private$title_enabled <- !is.null(title)
      private$session <- session
      private$max_store_bytes <- if (!is.null(options$max_store_mb)) {
        # Bytes must stay a double: as.integer() overflows R's 32-bit integer
        # range at max_store_mb >= 2048, yielding NA.
        as.double(options$max_store_mb * 1024 * 1024)
      } else {
        NULL
      }
    },

    on_response = function(recorded_turns) {
      # These two flags guard the *restore* transaction, which the count-based
      # check below does not: replay_ui() clears the client and re-sends the
      # stored messages, and the client's echo of that replay would otherwise
      # trigger a save. is_replaying suppresses saves during the replay window;
      # suppress_next_save swallows the first post-replay echo. (Python drops
      # these and relies on its count guard alone, but R's replay re-sends UI
      # to the client, so it suppresses the resulting echo explicitly.)
      if (self$is_replaying) {
        return(invisible())
      }
      if (self$suppress_next_save) {
        self$suppress_next_save <- FALSE
        return(invisible())
      }
      if (is.null(self$partition)) {
        rlang::abort("History controller partition not set")
      }

      messages <- get_reported_messages(private$session, private$chat_id)

      first_save <- is.null(self$record)
      if (!first_save) {
        if (
          length(recorded_turns) <= record_turn_count(self$record) &&
            length(messages) <= record_ui_count(self$record)
        ) {
          return(invisible())
        }
      }

      if (first_save) {
        self$record <- new_conversation_record(
          title = fallback_title(recorded_turns),
          client_info = get_client_info(private$client)
        )
      }

      self$record <- extend_record_linear(
        self$record,
        recorded_turns,
        ui_messages = messages,
        ui_offset = self$ui_offset,
        tools = private$client$get_tools()
      )
      self$ui_offset <- length(messages)
      self$record$response_count <- (self$record$response_count %||% 0L) + 1L
      self$record$values <- private$capture_app_state()

      private$store$put(self$partition, self$record)
      private$evict_if_needed()

      if (!is.null(self$on_response_saved)) {
        self$on_response_saved(self$record)
      }

      if (first_save) {
        if (!is.null(self$on_active_id_change)) {
          self$on_active_id_change(self$record$id)
        }
      }

      self$send_history_update()
      self$send_sibling_metadata()

      # Wait for the second response before titling: gives the LLM/custom
      # title_fn more context than a single exchange, and avoids spending a
      # call on conversations abandoned after one message. response_count
      # (not turn/node counts) drives this, since a single response's node
      # count isn't fixed -- e.g. tool round-trips add extra nodes.
      if (
        private$title_enabled &&
          is.null(self$record$title_source) &&
          identical(self$record$response_count, 2L)
      ) {
        private$retitle(recorded_turns)
      }
    },

    switch_to = function(conv_id) {
      if (!is.null(self$record) && identical(conv_id, self$record$id)) {
        return(invisible())
      }

      target <- private$store$get(self$partition, conv_id)
      if (is.null(target)) {
        rlang::abort(paste0("Conversation not found: ", conv_id))
      }

      self$save_current()

      if (!is.null(self$on_pre_switch)) {
        skip <- self$on_pre_switch(target)
        if (isTRUE(skip)) return(invisible())
      }

      set_turns_recorded(private$client, record_path_turns(target))
      self$replay_ui(target)
      self$restore_app_state(target$values %||% list())
      self$record <- target
      self$send_sibling_metadata()
      if (!is.null(self$on_active_id_change)) {
        self$on_active_id_change(target$id)
      }
      self$send_history_update()
    },

    new_chat = function() {
      self$save_current()
      private$client$set_turns(list())
      chat_clear(private$chat_id, session = private$session)
      self$record <- NULL
      self$ui_offset <- 0
      if (!is.null(self$on_active_id_change)) {
        self$on_active_id_change(NULL)
      }
      self$send_history_update()
    },

    rename = function(conv_id, title) {
      title <- paste(strsplit(trimws(title), "\\s+")[[1L]], collapse = " ")
      title <- substr(title, 1L, MAX_TITLE_LEN)
      if (!nzchar(title)) {
        return(invisible())
      }

      if (!is.null(self$record) && identical(conv_id, self$record$id)) {
        self$record$title <- title
        self$record$title_source <- "user"
        private$store$put(self$partition, self$record)
      } else {
        target <- private$store$get(self$partition, conv_id)
        if (!is.null(target)) {
          target$title <- title
          target$title_source <- "user"
          private$store$put(self$partition, target)
        }
      }
      self$send_history_update()
    },

    delete = function(conv_id) {
      if (!is.null(self$on_evict)) {
        self$on_evict(conv_id)
      }
      private$store$delete(self$partition, conv_id)

      if (!is.null(self$record) && identical(conv_id, self$record$id)) {
        self$record <- NULL
        self$ui_offset <- 0
        if (!is.null(self$on_active_id_change)) {
          self$on_active_id_change(NULL)
        }
        private$client$set_turns(list())
        chat_clear(private$chat_id, session = private$session)
      }
      self$send_history_update()
    },

    replay_ui = function(record) {
      self$is_replaying <- TRUE
      self$suppress_next_save <- TRUE
      clear_replay_on_exit <- TRUE
      on.exit(
        {
          if (clear_replay_on_exit) {
            self$is_replaying <- FALSE
          }
        },
        add = TRUE
      )

      chat_clear(private$chat_id, session = private$session)

      restored_count <- 0L
      shiny::withReactiveDomain(private$session, {
        for (node_id in record_path_node_ids(record)) {
          node <- record$nodes[[node_id]]
          stored <- node$ui
          if (is.null(stored)) {
            last_turn <- node$turns[[length(node$turns)]]
            last_turn_live <- ellmer::contents_replay(
              last_turn,
              tools = private$client$get_tools()
            )
            stored <- list(
              list(
                role = ellmer_turn_effective_role(last_turn_live),
                segments = list(
                  list(
                    content = turn_fallback_markdown(last_turn),
                    content_type = "markdown"
                  )
                )
              )
            )
          }
          for (message in stored) {
            restore_history_message(
              private$chat_id,
              message,
              session = private$session
            )
            restored_count <- restored_count + 1L
          }
        }
      })

      # ui_offset must reflect the messages the client will report for the
      # restored conversation. The client's echo of this replay is async and
      # hasn't arrived yet at this synchronous point, so count what was
      # actually just sent instead of reading session$input.
      self$ui_offset <- restored_count

      private$session$onFlushed(
        function() {
          self$is_replaying <- FALSE
        },
        once = TRUE
      )
      clear_replay_on_exit <- FALSE
    },

    get_record = function(partition, id) {
      private$store$get(partition, id)
    },

    save_current = function() {
      if (is.null(self$record) || is.null(self$partition)) {
        return(invisible())
      }

      recorded_turns <- get_turns_recorded(private$client)
      messages <- get_reported_messages(private$session, private$chat_id)
      self$record <- extend_record_linear(
        self$record,
        recorded_turns,
        ui_messages = messages,
        ui_offset = self$ui_offset,
        tools = private$client$get_tools()
      )
      self$ui_offset <- length(messages)
      self$record$values <- private$capture_app_state()
      private$store$put(self$partition, self$record)
    },

    restore_app_state = function(values) {
      if (!is.null(private$on_restore)) {
        private$on_restore(values %||% list())
      }
    },

    get_client = function() private$client,

    add_save_callback = function(fn) {
      old <- private$on_save
      private$on_save <- if (is.null(old)) {
        fn
      } else {
        function(values) {
          values <- call_on_save(old, values)
          call_on_save(fn, values)
        }
      }
      invisible(self)
    },

    add_restore_callback = function(fn) {
      old <- private$on_restore
      private$on_restore <- if (is.null(old)) {
        fn
      } else {
        function(values) {
          old(values)
          fn(values)
        }
      }
      invisible(self)
    },

    send_navigate = function(url, active_id, reload = FALSE) {
      send_chat_action(
        private$chat_id,
        list(
          type = "history_navigate",
          url = url,
          active_id = active_id,
          reload = isTRUE(reload)
        ),
        session = private$session
      )
    },

    send_history_update = function() {
      metas <- if (!is.null(self$partition)) {
        private$store$list(self$partition)
      } else {
        list()
      }

      send_chat_action(
        private$chat_id,
        list(
          type = "history_update",
          enabled = TRUE,
          conversations = metas,
          active_id = self$record$id %||% NULL
        ),
        session = private$session
      )
    },

    send_sibling_metadata = function() {
      if (is.null(self$record)) {
        return(invisible())
      }
      sibling_meta <- record_path_sibling_metadata(self$record)
      if (length(sibling_meta) == 0) {
        return(invisible())
      }
      data <- list()
      msg_idx <- 0L
      for (nid in record_path_node_ids(self$record)) {
        n_ui <- record_ui_message_count(self$record$nodes[[nid]])
        if (!is.null(sibling_meta[[nid]])) {
          data[[as.character(msg_idx)]] <- sibling_meta[[nid]]
        }
        msg_idx <- msg_idx + n_ui
      }
      if (length(data) > 0) {
        send_chat_action(
          private$chat_id,
          list(type = "update_siblings", data = data),
          session = private$session
        )
      }
    },

    handle_navigate = function(message_index, direction) {
      if (!direction %in% c("prev", "next")) {
        return(invisible())
      }
      if (is.null(self$record)) {
        return(invisible())
      }

      node_id <- record_node_id_for_message_index(self$record, message_index)
      siblings <- record_siblings_of(self$record, node_id)
      current_pos <- match(node_id, siblings)

      if (identical(direction, "prev")) {
        if (current_pos == 1L) {
          return(invisible())
        }
        target <- siblings[[current_pos - 1L]]
      } else {
        if (current_pos == length(siblings)) {
          return(invisible())
        }
        target <- siblings[[current_pos + 1L]]
      }

      leaf <- record_subtree_leaf(self$record, target)
      self$record <- record_set_current_leaf(self$record, leaf)
      set_turns_recorded(private$client, record_path_turns(self$record))
      self$replay_ui(self$record)
      # Unlike switch_to()'s replay_ui() call (which leaves suppress_next_save
      # set so the next on_response() swallows a stale in-flight response from
      # before the switch), handle_navigate() clears it immediately: there's
      # no new completion in flight here, and leaving it set would silently
      # drop the save of the next real response the user gets after
      # navigating -- a more likely and severe failure than the narrow race
      # this guards against in switch_to().
      self$suppress_next_save <- FALSE
      self$send_sibling_metadata()
      private$store$put(self$partition, self$record)
      self$send_history_update()
    },

    handle_edit = function(message_index, content, attachments = NULL) {
      if (is.null(self$record)) {
        return(invisible())
      }

      node_id <- record_node_id_for_message_index(self$record, message_index)
      fork_parent <- self$record$nodes[[node_id]]$parent

      # Branching happens implicitly: truncating current_leaf here means the
      # next extend_record_linear() (from the resubmit's on_response) creates
      # a sibling under fork_parent, not a child of the old leaf.
      self$record <- record_set_current_leaf(self$record, fork_parent)
      set_turns_recorded(private$client, record_path_turns(self$record))
      self$replay_ui(self$record)
      # See handle_navigate()'s identical reset for why this is required.
      self$suppress_next_save <- FALSE
      self$send_sibling_metadata()

      if (!is.null(attachments)) {
        # sendMessageEdit() always sends `attachments` (defaulting to `[]`),
        # which jsonlite deserializes to a non-NULL, length-0 list() -- so an
        # empty-but-present list must still force attachment_mode = "set"
        # below, rather than falling to the else branch and leaving whatever
        # happens to be staged in the main compose box untouched.
        #
        # Same validate-then-normalize pattern as Python's handle_edit --
        # never trust client-side validation alone, and reconstruct a
        # canonical record per attachment so any extra client-sent fields are
        # dropped before echoing them back through update_input.
        validate_attachments(attachments)
        attachments <- lapply(attachments, function(a) {
          list(
            mime = a[["mime"]],
            data_url = a[["data_url"]],
            name = a[["name"]],
            size = a[["size"]]
          )
        })
        update_chat_user_input(
          private$chat_id,
          value = content,
          submit = TRUE,
          attachments = attachments,
          attachment_mode = "set",
          session = private$session
        )
      } else {
        update_chat_user_input(
          private$chat_id,
          value = content,
          submit = TRUE,
          session = private$session
        )
      }
    }
  ),

  private = list(
    store = NULL,
    chat_id = NULL,
    client = NULL,
    title_fn = NULL,
    title_enabled = NULL,
    session = NULL,
    title_task = NULL,
    on_save = NULL,
    on_restore = NULL,
    max_store_bytes = NULL,

    capture_app_state = function() {
      values <- list()
      if (!is.null(private$on_save)) {
        values <- call_on_save(private$on_save, values)
      }
      values
    },

    evict_one = function(conv_id) {
      if (!is.null(self$on_evict)) {
        self$on_evict(conv_id)
      }
      private$store$delete(self$partition, conv_id)
    },

    evict_if_needed = function() {
      max_bytes <- private$max_store_bytes
      if (is.null(max_bytes) || is.null(self$partition)) {
        return(invisible())
      }
      metas <- private$store$list(self$partition)
      total <- sum(vapply(metas, function(m) m$size_bytes, double(1L)))
      if (total <= max_bytes) {
        return(invisible())
      }
      for (meta in rev(metas)) {
        if (!is.null(self$record) && identical(meta$id, self$record$id)) {
          next
        }
        total <- total - meta$size_bytes
        private$evict_one(meta$id)
        if (total <= max_bytes) break
      }
      if (total > max_bytes) {
        cli::cli_warn(
          paste0(
            "Chat history for this conversation exceeds {.arg max_store_mb} ",
            "on its own; all other conversations in this history partition were evicted ",
            "but the store remains over budget."
          ),
          .frequency = "once",
          .frequency_id = paste0(
            "shinychat_history_over_budget_",
            private$chat_id
          )
        )
      }
      invisible()
    },

    retitle = function(recorded_turns) {
      target_id <- self$record$id
      title_promise <- generate_title(
        private$title_fn,
        private$client,
        recorded_turns
      )
      promises::then(title_promise, function(title) {
        if (is.null(title)) {
          return()
        }
        if (is.null(self$record) || !identical(self$record$id, target_id)) {
          return()
        }
        if (identical(self$record$title_source, "user")) {
          return()
        }

        self$record$title <- title
        self$record$title_source <- "llm"
        private$store$put(self$partition, self$record)
        self$send_history_update()
      })
    }
  )
)

#' Configure chat history options
#'
#' @param restore_mode How a previous conversation is reloaded when the page
#'   opens. `"browser"` (the default) stores the active conversation ID in
#'   `localStorage` so it survives page reloads. `"url"` stores the ID as a
#'   plain `?shinychat_conversation_id=<id>` query parameter so the active
#'   conversation is visible in the address bar and users can share or bookmark
#'   specific conversations; no server bookmarking configuration is required.
#'   `"bookmark"` participates in Shiny server bookmarking: after every LLM
#'   response a fresh server bookmark is minted and the address bar updates to
#'   `?_state_id_=...`. Requires `bookmarkStore = "server"` in the Shiny app
#'   options. On in-session conversation switches, navigates to the target
#'   conversation's bookmark URL if one exists.
#'   `"none"` disables automatic restore entirely.
#' @param store Storage backend: `"auto"` (default: memory in dev, file in
#'   production), `"memory"`, `"file"`, or a [ConversationStore] R6 instance.
#'   `"auto"` emits a once-per-session message announcing which backend was
#'   chosen; set `options(shinychat.history_options.store_auto.quiet = TRUE)`
#'   to silence it.
#' @param scope Storage namespace for conversations. A string, a
#'   `function(session)` returning a string, or `NULL` (default: uses
#'   `session$user` if authenticated, otherwise a per-browser token).
#'   Pass a shared string to allow multiple users to share history — for
#'   example `session$groups[[1]]` to scope by group, or a constant like
#'   `"global"` to share across all users.
#' @param title Title generation strategy. `"auto"` (default) for LLM-generated
#'   titles, a `function(recorded_turns)` for custom titles, or `NULL` to skip
#'   LLM titling (the conversation keeps its initial timestamp-based name).
#' @param max_store_mb Maximum total storage in megabytes per chat history
#'   partition. Oldest conversations are evicted when the limit is exceeded.
#'   Defaults to `100`.
#' @returns A configuration object for use with [chat_enable_history()].
#' @export
history_options <- function(
  restore_mode = c("browser", "url", "none", "bookmark"),
  store = "auto",
  scope = NULL,
  title = "auto",
  max_store_mb = 100
) {
  restore_mode <- match.arg(restore_mode)
  structure(
    list(
      restore_mode = restore_mode,
      store = store,
      scope = scope,
      title = title,
      max_store_mb = max_store_mb
    ),
    class = "chat_history_config"
  )
}

#' Enable conversation history for a chat
#'
#' @param id The chat element ID.
#' @param client An [ellmer::Chat] object.
#' @param ... Reserved for future use.
#' @param on_save An optional `function(values)` called whenever the active
#'   conversation is saved. Receives a named list; add any per-conversation
#'   state you want to persist and return the modified list. Fired on each LLM
#'   response and when the user switches conversations. Multiple callbacks may
#'   be registered; they are called in registration order.
#' @param on_restore An optional `function(values)` called when a conversation
#'   is loaded — on page-load restore and on in-session switches. Use it to
#'   sync auxiliary UI state (tabs, model selectors, etc.) to match the restored
#'   conversation. Call the appropriate `updateXxx()` functions here. Receives
#'   the `values` list captured by `on_save`. Multiple callbacks may be
#'   registered; they are called in registration order.
#'
#'   **Note:** This callback does not fire when `restore_mode = "bookmark"`.
#'   In that mode Shiny's native bookmark restore cycle handles app state;
#'   use `session$onRestore()` directly if needed.
#' @param options A [history_options()] object controlling storage, identity,
#'   titling, and restore behaviour.
#' @param restore_ui Whether to render the active conversation into the chat
#'   UI and fire `on_restore` on registration. Default is `TRUE`. Set to
#'   `FALSE` when re-registering history after a client swap (where the UI
#'   already reflects the conversation).
#' @param session The Shiny session.
#' @returns Invisibly, a function that cancels all history registrations.
#' @export
chat_enable_history <- function(
  id,
  client,
  ...,
  on_save = NULL,
  on_restore = NULL,
  options = history_options(),
  restore_ui = TRUE,
  session = shiny::getDefaultReactiveDomain()
) {
  rlang::check_dots_empty()
  if (!inherits(options, "chat_history_config")) {
    rlang::abort('`options` must be a `history_options()` object.')
  }
  restore_mode <- options$restore_mode
  scope_opt <- options$scope
  check_ellmer_chat(client)

  if (is.null(session)) {
    rlang::abort(
      "A session is required. Call chat_enable_history() within a server function."
    )
  }
  resolved_id <- resolve_id(id, session)

  controller <- HistoryController$new(
    chat_id = id,
    client = client,
    options = options,
    session = session
  )

  if (!is.null(on_save)) {
    controller$add_save_callback(on_save)
  }
  if (!is.null(on_restore)) {
    controller$add_restore_callback(on_restore)
  }

  # Read back via session by the message_response_effect observer and the
  # on_save/on_restore hooks in chat_app().
  set_session_chat_bookmark_info(
    session,
    paste0(id, ".history-controller"),
    controller
  )

  history_inputs <- paste0(
    id,
    c(
      "_history_browser_token",
      "_history_current_id",
      "_history_url_id",
      "_history_select",
      "_history_new",
      "_history_rename",
      "_history_delete",
      "_message_edit",
      "_message_navigate",
      # Carries StoredMessage-like list objects, which aren't
      # JSON-serializable for Shiny's bookmark input.json.
      "_messages"
    )
  )
  excluded <- session$getBookmarkExclude()
  to_add <- setdiff(history_inputs, excluded)
  if (length(to_add) > 0) {
    session$setBookmarkExclude(c(excluded, to_add))
  }

  token_input <- paste0(id, "_history_browser_token")
  current_id_input <- paste0(id, "_history_current_id")
  url_id_input <- paste0(id, "_history_url_id")

  scope_val <- shiny::reactive(label = "history_scope", {
    # When restore_mode needs localStorage inputs ("browser" or "url"), the
    # active conversation ID is sent from the client inside
    # initializedPromise.then() — AFTER Shiny's first reactive flush. If the
    # scope resolves immediately (from session$user or a caller-supplied
    # scope_opt), the init observer fires in that first flush and reads
    # current_id / url_id as NULL, permanently missing the active conversation.
    #
    # The browser token is dispatched in the same microtask as current_id and
    # url_id. Requiring it here delays scope resolution until that second flush,
    # ensuring all three inputs have arrived before the init observer runs.
    if (
      restore_mode %in%
        c("browser", "url") &&
        (!is.null(scope_opt) || !is.null(session$user))
    ) {
      shiny::req(session$input[[token_input]])
    }
    if (is.character(scope_opt)) {
      return(scope_opt)
    }
    if (is.function(scope_opt)) {
      return(scope_opt(session))
    }
    su <- session$user
    if (!is.null(su)) {
      return(as.character(su))
    }
    token <- session$input[[token_input]]
    shiny::req(token)
    token
  })

  if (identical(restore_mode, "url")) {
    controller$on_active_id_change <- function(conv_id) {
      url <- if (!is.null(conv_id)) {
        paste0("?shinychat_conversation_id=", conv_id)
      } else {
        NULL
      }
      controller$send_navigate(url, conv_id)
    }
  }

  # --- Bookmark mode ---
  if (identical(restore_mode, "bookmark")) {
    bm_store_check <- shiny::getShinyOption(
      "bookmarkStore",
      default = "disable"
    )
    if (!identical(bm_store_check, "server")) {
      rlang::abort(
        "restore_mode = 'bookmark' requires bookmarkStore = 'server' in the Shiny app options."
      )
    }

    controller$on_response_saved <- function(record) {
      captured_id <- record$id
      cancel_bm <- session$onBookmarked(function(url) {
        new_state_id <- extract_state_id(url)
        if (is.null(new_state_id)) {
          return()
        }
        if (
          is.null(controller$record) ||
            !identical(controller$record$id, captured_id)
        ) {
          return()
        }
        old_state_id <- controller$record$bookmark_state_id
        controller$record$bookmark_state_id <- new_state_id
        if (!is.null(old_state_id)) {
          delete_bookmark_state(old_state_id)
        }
        controller$save_current()
        controller$send_navigate(
          paste0("?_state_id_=", new_state_id),
          captured_id
        )
      })
      session$doBookmark()
      cancel_bm()
    }

    controller$on_pre_switch <- function(target) {
      if (!is.null(target$bookmark_state_id)) {
        controller$send_navigate(
          paste0("?_state_id_=", target$bookmark_state_id),
          target$id,
          reload = TRUE
        )
        return(TRUE)
      }
      FALSE
    }

    controller$on_evict <- function(conv_id) {
      if (
        !is.null(controller$record) && identical(controller$record$id, conv_id)
      ) {
        state_id <- controller$record$bookmark_state_id
      } else {
        partition <- controller$partition
        rec <- if (!is.null(partition)) {
          controller$get_record(partition, conv_id)
        } else {
          NULL
        }
        state_id <- if (!is.null(rec)) rec$bookmark_state_id else NULL
      }
      if (!is.null(state_id)) delete_bookmark_state(state_id)
    }

    controller$on_active_id_change <- function(conv_id) {
      if (is.null(conv_id)) {
        controller$send_navigate(NULL, NULL, reload = TRUE)
      }
    }
  }

  # --- Bookmark stamp ---
  stamp_key <- paste0(id, "_history_conversation_id")
  stamp_cancel <- NULL
  bm_store <- shiny::getShinyOption("bookmarkStore", default = "disable")
  if (identical(bm_store, "server")) {
    stamp_cancel <- session$onBookmark(function(state) {
      if (!is.null(controller$record)) {
        state$values[[stamp_key]] <- controller$record$id
      }
    })
  }

  initialized <- FALSE
  restore_after_first_flush <- function(values) {
    session$onFlushed(
      function() {
        controller$restore_app_state(values %||% list())
      },
      once = TRUE
    )
  }
  init_effect <- shiny::observe(label = "history_init", {
    if (initialized) {
      return()
    }

    scope <- scope_val()
    shiny::req(scope)
    controller$partition <- conversation_partition(resolved_id, scope)

    # Priority 1: restore from a Shiny bookmark context (any mode).
    rc <- session$restoreContext
    if (!is.null(rc) && isTRUE(rc$active)) {
      restored_id <- rc$values[[stamp_key]]
      if (!is.null(restored_id) && nzchar(restored_id)) {
        target <- controller$get_record(controller$partition, restored_id)
        if (!is.null(target)) {
          set_turns_recorded(client, record_path_turns(target))
          if (restore_ui) {
            controller$replay_ui(target)
            if (!identical(restore_mode, "bookmark")) {
              restore_after_first_flush(target$values)
            }
          } else {
            controller$ui_offset <- record_ui_count(target)
          }
          controller$record <- target
          controller$send_sibling_metadata()
          controller$send_history_update()
          initialized <<- TRUE
          return()
        }
      }
    }

    # Priority 2: restore from the mode-specific ID source.
    current_id <- if (identical(restore_mode, "url")) {
      session$input[[url_id_input]]
    } else if (identical(restore_mode, "browser")) {
      session$input[[current_id_input]]
    } else {
      NULL
    }

    if (!is.null(current_id) && nzchar(current_id)) {
      target <- controller$get_record(controller$partition, current_id)
      if (!is.null(target)) {
        set_turns_recorded(client, record_path_turns(target))
        if (restore_ui) {
          controller$replay_ui(target)
          restore_after_first_flush(target$values)
        } else {
          controller$ui_offset <- record_ui_count(target)
        }
        controller$record <- target
        controller$send_sibling_metadata()
      }
    }

    controller$send_history_update()
    initialized <<- TRUE
  })

  history_notify_error <- function(prefix, e) {
    shiny::showNotification(
      paste0(prefix, ": ", sanitized_error_message(e)),
      type = "error",
      duration = NULL
    )
    rlang::warn(prefix, parent = e)
  }

  select_effect <- shiny::observeEvent(
    session$input[[paste0(id, "_history_select")]],
    label = "history_select",
    {
      if (is.null(controller$partition)) {
        return()
      }
      payload <- session$input[[paste0(id, "_history_select")]]
      tryCatch(
        controller$switch_to(as.character(payload$id)[[1L]]),
        error = function(e) {
          history_notify_error("Could not open conversation", e)
        }
      )
    }
  )

  new_effect <- shiny::observeEvent(
    session$input[[paste0(id, "_history_new")]],
    label = "history_new",
    {
      if (is.null(controller$partition)) {
        return()
      }
      tryCatch(
        controller$new_chat(),
        error = function(e) {
          history_notify_error("Could not start a new chat", e)
        }
      )
    }
  )

  rename_effect <- shiny::observeEvent(
    session$input[[paste0(id, "_history_rename")]],
    label = "history_rename",
    {
      if (is.null(controller$partition)) {
        return()
      }
      payload <- session$input[[paste0(id, "_history_rename")]]
      tryCatch(
        controller$rename(
          as.character(payload$id)[[1L]],
          as.character(payload$title)[[1L]]
        ),
        error = function(e) {
          history_notify_error("Could not rename conversation", e)
        }
      )
    }
  )

  delete_effect <- shiny::observeEvent(
    session$input[[paste0(id, "_history_delete")]],
    label = "history_delete",
    {
      if (is.null(controller$partition)) {
        return()
      }
      payload <- session$input[[paste0(id, "_history_delete")]]
      tryCatch(
        controller$delete(as.character(payload$id)[[1L]]),
        error = function(e) {
          history_notify_error("Could not delete conversation", e)
        }
      )
    }
  )

  message_edit_effect <- shiny::observeEvent(
    session$input[[paste0(id, "_message_edit")]],
    label = "message_edit",
    {
      if (is.null(controller$partition)) {
        return()
      }
      payload <- session$input[[paste0(id, "_message_edit")]]
      tryCatch(
        controller$handle_edit(
          as.integer(payload$index)[[1L]],
          as.character(payload$content)[[1L]],
          payload$attachments
        ),
        error = function(e) {
          history_notify_error("Could not edit message", e)
        }
      )
    }
  )

  message_navigate_effect <- shiny::observeEvent(
    session$input[[paste0(id, "_message_navigate")]],
    label = "message_navigate",
    {
      if (is.null(controller$partition)) {
        return()
      }
      payload <- session$input[[paste0(id, "_message_navigate")]]
      tryCatch(
        controller$handle_navigate(
          as.integer(payload$index)[[1L]],
          as.character(payload$direction)[[1L]]
        ),
        error = function(e) {
          history_notify_error("Could not navigate messages", e)
        }
      )
    }
  )

  # The save trigger: fires once the browser echoes an updated `_messages`
  # snapshot back to the server. This must be event-driven (not chained
  # directly onto the streaming response's promise) because the echo is a
  # separate round trip -- the browser only reports a finished assistant
  # reply *after* it has rendered it and sent it back over the websocket.
  # Triggering on stream completion instead would run on_response() one
  # message ahead of what the client has actually reported, and
  # extend_record_linear() would misattach the still-unreported assistant
  # reply to the wrong (next round's) node.
  message_response_effect <- shiny::observeEvent(
    session$input[[paste0(id, "_messages")]],
    label = "history_on_response",
    ignoreInit = TRUE,
    {
      if (is.null(controller$partition)) {
        return()
      }
      messages <- get_reported_messages(session, id)
      if (length(messages) == 0) {
        return()
      }
      last_role <- messages[[length(messages)]]$role
      if (!identical(last_role, "assistant")) {
        return()
      }
      tryCatch(
        controller$on_response(get_turns_recorded(controller$get_client())),
        error = function(e) {
          history_notify_error("Could not save conversation", e)
        }
      )
    }
  )

  cancel <- function() {
    init_effect$destroy()
    select_effect$destroy()
    new_effect$destroy()
    rename_effect$destroy()
    delete_effect$destroy()
    message_response_effect$destroy()
    message_edit_effect$destroy()
    message_navigate_effect$destroy()
    if (!is.null(stamp_cancel)) {
      stamp_cancel()
    }
    set_session_chat_bookmark_info(
      session,
      paste0(id, ".history-controller"),
      NULL
    )
    send_chat_action(
      id,
      list(
        type = "history_update",
        enabled = FALSE,
        conversations = list(),
        active_id = NULL
      ),
      session = session
    )
  }

  invisible(cancel)
}

call_on_save <- function(fn, values) {
  result <- fn(values)
  if (is.null(result)) {
    rlang::warn(
      "An `on_save` callback returned NULL; values are unchanged. Did you forget to return the modified list?"
    )
    return(values)
  }
  result
}
