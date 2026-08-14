# resolve_store('auto') announces the dev-mode backend once per session

    Code
      invisible(resolve_store("auto"))
    Message
      Chat history: using in-memory storage (dev mode). History is lost on restart. To persist across restarts, use `history_options(store = "file")`.
      i Set `options(shinychat.history_options.store_auto.quiet = TRUE)` to silence this message.
      This message is displayed once per session.

# resolve_store('auto') announces the file-based backend once per session

    Code
      invisible(resolve_store("auto"))
    Message
      Chat history: using file-based storage. To use in-memory storage instead, use `history_options(store = "memory")`.
      i Set `options(shinychat.history_options.store_auto.quiet = TRUE)` to silence this message.
      This message is displayed once per session.

