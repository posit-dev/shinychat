# Create an attachment from a local file path

Reads a file, base64-encodes its contents, and returns a list in the
format expected by the `attachments` argument of
[`update_chat_user_input()`](https://posit-dev.github.io/shinychat/r/dev/reference/update_chat_user_input.md).

## Usage

``` r
chat_attachment(path, mime = NULL, name = NULL)
```

## Arguments

- path:

  Path to the file. The file must exist.

- mime:

  MIME type of the file. When `NULL` (default), guessed from the file
  extension. Raises an error if the extension is unrecognised.

- name:

  Filename shown in the attachment chip. Defaults to `basename(path)`.

## Value

A list with elements `mime`, `name`, `size`, and `data_url`, ready to
pass as an element of the `attachments` argument of
[`update_chat_user_input()`](https://posit-dev.github.io/shinychat/r/dev/reference/update_chat_user_input.md).
