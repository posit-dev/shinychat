# File-based conversation storage backend

Uses temporary records and journal rollback to protect against ordinary
I/O failures, but does not fsync files or directories. This store also
does not coordinate concurrent access across processes; callers must
serialize reads and writes for each conversation.

## Super class

[`ConversationStore`](https://posit-dev.github.io/shinychat/r/dev/reference/ConversationStore.md)
-\> `FileConversationStore`

## Methods

### Public methods

- [`FileConversationStore$new()`](#method-FileConversationStore-initialize)

- [`FileConversationStore$list()`](#method-FileConversationStore-list)

- [`FileConversationStore$get()`](#method-FileConversationStore-get)

- [`FileConversationStore$put()`](#method-FileConversationStore-put)

- [`FileConversationStore$delete()`](#method-FileConversationStore-delete)

- [`FileConversationStore$clone()`](#method-FileConversationStore-clone)

Inherited methods

- [`ConversationStore$search()`](https://posit-dev.github.io/shinychat/r/dev/reference/ConversationStore.html#method-search)
- [`ConversationStore$total_size()`](https://posit-dev.github.io/shinychat/r/dev/reference/ConversationStore.html#method-total_size)

------------------------------------------------------------------------

### `FileConversationStore$new()`

Create a new file-based conversation store.

#### Usage

    FileConversationStore$new(dir = NULL)

#### Arguments

- `dir`:

  Directory to store conversations under. Defaults to `NULL`, which
  resolves a redeploy-safe location at first use (see
  `resolve_history_dir()`).

------------------------------------------------------------------------

### `FileConversationStore$list()`

All conversations in `partition`, newest-first by `updated_at`, read
from one `record.json` per conversation directory on disk.

#### Usage

    FileConversationStore$list(partition)

#### Arguments

- `partition`:

  A `conversation_partition()`.

#### Returns

A list of conversation meta lists.

------------------------------------------------------------------------

### `FileConversationStore$get()`

The full conversation record for `id` in `partition`, reassembled from
`record.json`, `turns.jsonl`, and `ui.jsonl`.

#### Usage

    FileConversationStore$get(partition, id)

#### Arguments

- `partition`:

  A `conversation_partition()`.

- `id`:

  A conversation id, as found in the `id` field of a conversation meta
  list.

#### Returns

The conversation record, or `NULL` if missing.

------------------------------------------------------------------------

### `FileConversationStore$put()`

Upsert `record` into `partition`, appending new turns and UI data to
`turns.jsonl`/`ui.jsonl` and rewriting `record.json`.

#### Usage

    FileConversationStore$put(partition, record)

#### Arguments

- `partition`:

  A `conversation_partition()`.

- `record`:

  A conversation record, in the same shape returned by
  [`get()`](https://rdrr.io/r/base/get.html).

#### Returns

`NULL`, invisibly.

------------------------------------------------------------------------

### `FileConversationStore$delete()`

Remove the conversation `id` from `partition` by deleting its directory.
Missing ids are a no-op.

#### Usage

    FileConversationStore$delete(partition, id)

#### Arguments

- `partition`:

  A `conversation_partition()`.

- `id`:

  A conversation id, as found in the `id` field of a conversation meta
  list.

#### Returns

`NULL`, invisibly.

------------------------------------------------------------------------

### `FileConversationStore$clone()`

The objects of this class are cloneable with this method.

#### Usage

    FileConversationStore$clone(deep = FALSE)

#### Arguments

- `deep`:

  Whether to make a deep clone.
