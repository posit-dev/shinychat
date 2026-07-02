# Enable conversation history for a chat

Enable conversation history for a chat

## Usage

``` r
chat_enable_history(
  id,
  client,
  ...,
  on_save = NULL,
  on_restore = NULL,
  options = history_options(),
  restore_ui = TRUE,
  session = shiny::getDefaultReactiveDomain()
)
```

## Arguments

- id:

  The chat element ID.

- client:

  An [ellmer::Chat](https://ellmer.tidyverse.org/reference/Chat.html)
  object.

- ...:

  Reserved for future use.

- on_save:

  An optional `function(values)` called whenever the active conversation
  is saved. Receives a named list; add any per-conversation state you
  want to persist and return the modified list. Fired on each LLM
  response and when the user switches conversations. Multiple callbacks
  may be registered; they are called in registration order.

- on_restore:

  An optional `function(values)` called when a conversation is loaded —
  on page-load restore and on in-session switches. Use it to sync
  auxiliary UI state (tabs, model selectors, etc.) to match the restored
  conversation. Call the appropriate `updateXxx()` functions here.
  Receives the `values` list captured by `on_save`. Multiple callbacks
  may be registered; they are called in registration order.

  **Note:** This callback does not fire when
  `restore_mode = "bookmark"`. In that mode Shiny's native bookmark
  restore cycle handles app state; use `session$onRestore()` directly if
  needed.

- options:

  A
  [`history_options()`](https://posit-dev.github.io/shinychat/r/dev/reference/history_options.md)
  object controlling storage, identity, titling, and restore behaviour.

- restore_ui:

  Whether to render the active conversation into the chat UI and fire
  `on_restore` on registration. Default is `TRUE`. Set to `FALSE` when
  re-registering history after a client swap (where the UI already
  reflects the conversation).

- session:

  The Shiny session.

## Value

Invisibly, a function that cancels all history registrations.
