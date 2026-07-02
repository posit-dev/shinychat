# File-based conversation storage backend

File-based conversation storage backend

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

#### Usage

    FileConversationStore$list(partition)

#### Arguments

- `partition`:

  A `conversation_partition()`.

------------------------------------------------------------------------

### `FileConversationStore$get()`

#### Usage

    FileConversationStore$get(partition, id)

#### Arguments

- `partition`:

  A `conversation_partition()`.

- `id`:

  A conversation id, as found in the `id` field of a conversation meta
  list.

------------------------------------------------------------------------

### `FileConversationStore$put()`

#### Usage

    FileConversationStore$put(partition, record)

#### Arguments

- `partition`:

  A `conversation_partition()`.

- `record`:

  A conversation record, in the same shape returned by
  [`get()`](https://rdrr.io/r/base/get.html).

------------------------------------------------------------------------

### `FileConversationStore$delete()`

#### Usage

    FileConversationStore$delete(partition, id)

#### Arguments

- `partition`:

  A `conversation_partition()`.

- `id`:

  A conversation id, as found in the `id` field of a conversation meta
  list.

------------------------------------------------------------------------

### `FileConversationStore$clone()`

The objects of this class are cloneable with this method.

#### Usage

    FileConversationStore$clone(deep = FALSE)

#### Arguments

- `deep`:

  Whether to make a deep clone.
