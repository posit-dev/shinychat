# Configure chat history options

Configure chat history options

## Usage

``` r
history_options(
  restore_mode = c("browser", "url", "none", "bookmark"),
  store = "auto",
  scope = NULL,
  title = "auto",
  max_store_mb = 100
)
```

## Arguments

- restore_mode:

  How a previous conversation is reloaded when the page opens.
  `"browser"` (the default) stores the active conversation ID in
  `localStorage` so it survives page reloads. `"url"` stores the ID as a
  plain `?shinychat_conversation_id=<id>` query parameter so the active
  conversation is visible in the address bar and users can share or
  bookmark specific conversations; no server bookmarking configuration
  is required. `"bookmark"` participates in Shiny server bookmarking:
  after every LLM response a fresh server bookmark is minted and the
  address bar updates to `?_state_id_=...`. Requires
  `bookmarkStore = "server"` in the Shiny app options. On in-session
  conversation switches, navigates to the target conversation's bookmark
  URL if one exists. `"none"` disables automatic restore entirely.

- store:

  Storage backend: `"auto"` (default: memory in dev, file in
  production), `"memory"`, `"file"`, or a
  [ConversationStore](https://posit-dev.github.io/shinychat/r/dev/reference/ConversationStore.md)
  R6 instance.

- scope:

  Storage namespace for conversations. A string, a `function(session)`
  returning a string, or `NULL` (default: uses `session$user` if
  authenticated, otherwise a per-browser token). Pass a shared string to
  allow multiple users to share history — for example
  `session$groups[[1]]` to scope by group, or a constant like `"global"`
  to share across all users.

- title:

  Title generation strategy. `"auto"` (default) for LLM-generated
  titles, a `function(recorded_turns)` for custom titles, or `NULL` to
  skip LLM titling (the conversation keeps its initial timestamp-based
  name).

- max_store_mb:

  Maximum total storage in megabytes per chat history partition. Oldest
  conversations are evicted when the limit is exceeded. Defaults to
  `100`.

## Value

A configuration object for use with
[`chat_enable_history()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_enable_history.md).
