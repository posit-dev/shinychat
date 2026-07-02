# Abstract base class for conversation storage backends

Subclass this to plug a custom persistence backend into
[`chat_enable_history()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_enable_history.md)
via `history_options(store = )`. All methods are partitioned by a
`conversation_partition()` (chat id + owner scope); implementations
should not need to know about users, sessions, or Shiny beyond that.

A conversation record is a list with fields `schema_version`, `id`,
`title`, `title_source` (`"llm"`, `"user"`, or `NULL`),
`response_count`, `created_at`, `updated_at` (ISO 8601 strings),
`client_info`, `nodes` (a named list of turn nodes forming the
conversation tree), `current_leaf` (id of the most recent node, or
`NULL`), `values` (the app state dict captured by `on_save`), and
`bookmark_state_id`. A conversation meta list is the lightweight summary
returned by [`list()`](https://rdrr.io/r/base/list.html): `id`, `title`,
`created_at`, `updated_at`, and `size_bytes` (the backend's storage
footprint for that conversation, e.g. on-disk bytes).

## Methods

### Public methods

- [`ConversationStore$list()`](#method-ConversationStore-list)

- [`ConversationStore$get()`](#method-ConversationStore-get)

- [`ConversationStore$put()`](#method-ConversationStore-put)

- [`ConversationStore$delete()`](#method-ConversationStore-delete)

- [`ConversationStore$search()`](#method-ConversationStore-search)

- [`ConversationStore$total_size()`](#method-ConversationStore-total_size)

- [`ConversationStore$clone()`](#method-ConversationStore-clone)

------------------------------------------------------------------------

### `ConversationStore$list()`

Must be implemented by subclasses. All conversations in `partition`,
newest-first by `updated_at`.

#### Usage

    ConversationStore$list(partition)

#### Arguments

- `partition`:

  A `conversation_partition()`.

#### Returns

A list of conversation meta lists.

------------------------------------------------------------------------

### `ConversationStore$get()`

Must be implemented by subclasses. The full conversation record for `id`
in `partition`.

#### Usage

    ConversationStore$get(partition, id)

#### Arguments

- `partition`:

  A `conversation_partition()`.

- `id`:

  A conversation id, as found in the `id` field of a conversation meta
  list.

#### Returns

The conversation record, or `NULL` if missing.

------------------------------------------------------------------------

### `ConversationStore$put()`

Must be implemented by subclasses. Upsert `record` into `partition`. A
rename is just mutating `record$title` and calling `put()` again.

#### Usage

    ConversationStore$put(partition, record)

#### Arguments

- `partition`:

  A `conversation_partition()`.

- `record`:

  A conversation record, in the same shape returned by
  [`get()`](https://rdrr.io/r/base/get.html).

#### Returns

`NULL`, invisibly.

------------------------------------------------------------------------

### `ConversationStore$delete()`

Must be implemented by subclasses. Remove the conversation `id` from
`partition`. Missing ids are a no-op.

#### Usage

    ConversationStore$delete(partition, id)

#### Arguments

- `partition`:

  A `conversation_partition()`.

- `id`:

  A conversation id, as found in the `id` field of a conversation meta
  list.

#### Returns

`NULL`, invisibly.

------------------------------------------------------------------------

### `ConversationStore$search()`

Case-insensitive substring match of `query` against title, over
`list(partition)`. Backends don't need to override this unless they have
a more efficient search path.

#### Usage

    ConversationStore$search(partition, query)

#### Arguments

- `partition`:

  A `conversation_partition()`.

- `query`:

  A search string.

#### Returns

A list of conversation meta lists whose title matches `query`.

------------------------------------------------------------------------

### `ConversationStore$total_size()`

Total bytes used by all conversations in `partition`, derived from
[`list()`](https://rdrr.io/r/base/list.html)'s per-record `size_bytes`.
Backends don't need to override this unless they have a cheaper way to
compute it.

#### Usage

    ConversationStore$total_size(partition)

#### Arguments

- `partition`:

  A `conversation_partition()`.

#### Returns

The total size in bytes, as a double.

------------------------------------------------------------------------

### `ConversationStore$clone()`

The objects of this class are cloneable with this method.

#### Usage

    ConversationStore$clone(deep = FALSE)

#### Arguments

- `deep`:

  Whether to make a deep clone.
