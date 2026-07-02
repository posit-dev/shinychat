# Deprecated chat module functions

**\[deprecated\]**

These functions are deprecated as of shinychat 0.5.0. Use
[`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md)
with `NS(id, "chat")` and
[`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)
instead.

## Usage

``` r
chat_mod_ui(
  id,
  ...,
  client = deprecated(),
  messages = NULL,
  allow_attachments = TRUE
)

chat_mod_server(
  id,
  client,
  greeting = NULL,
  history = TRUE,
  bookmark_on_input = lifecycle::deprecated(),
  bookmark_on_response = lifecycle::deprecated()
)
```

## Arguments

- id:

  The chat module ID.

- ...:

  Extra HTML attributes to include on the chat element

- client:

  Deprecated. The client state is now managed by
  [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md).

- messages:

  Initial messages shown in the chat, used only when `client` doesn't
  already contain turns. Passed to `messages` in
  [`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md).

- allow_attachments:

  Controls the file-attachment affordance (an attach button, plus
  clipboard paste and drag-and-drop) in the chat input. `NULL` (default)
  defers to
  [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md),
  which enables attachments automatically. Pass `TRUE` to accept all
  supported types (PNG, JPEG, GIF, WebP, PDF, and common text/code files
  such as Markdown, plain text, CSV, JSON, and source files), `FALSE` to
  disable, or a character vector of MIME types to restrict what is
  accepted (each must be one of the supported types).

  The shape of `input$<id>_user_input` is determined by this argument,
  so it is predictable for a given app. When attachments are disabled
  (the default), it is the typed text as a character string, exactly as
  before. When attachments are enabled, it is always a list of ellmer
  [ellmer::Content](https://ellmer.tidyverse.org/reference/Content.html)
  objects (the typed text, if any, followed by one content object per
  attachment) - a list even when no files were attached. Splice the list
  into a chat method's `...` with `!!!`, e.g.
  `client$stream_async(!!!input$<id>_user_input)`. (No
  [`rlang::inject()`](https://rlang.r-lib.org/reference/inject.html) is
  needed: ellmer's chat methods collect `...` with dynamic dots.)

  The maximum combined size of all attachments in a single message is
  controlled globally by the `SHINYCHAT_MAX_ATTACHMENT_SIZE` environment
  variable (a raw byte count; defaults to approximately 30 MB). Files
  that would push the total over this cap are rejected in the browser
  with a notice.

- greeting:

  See
  [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md).

- bookmark_on_input:

  See
  [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md).

- bookmark_on_response:

  See
  [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md).

## Value

- `chat_mod_ui()` returns the UI for a shinychat module.

- `chat_mod_server()` returns the value of
  [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md).

## Functions

- `chat_mod_server()`: A Shiny module server for chat (deprecated). Use
  [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)
  instead.
