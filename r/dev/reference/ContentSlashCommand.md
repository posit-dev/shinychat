# Slash command content

An
[ellmer::ContentText](https://ellmer.tidyverse.org/reference/Content.html)
subclass that preserves the original slash command entered by the user.
When the chat UI is restored from a bookmark (or pre-existing turns),
the original `/command user_text` is shown in the UI instead of the
(possibly transformed) `text` that was sent to the LLM.

## Usage

``` r
ContentSlashCommand(
  text = stop("Required"),
  command = character(0),
  user_text = ""
)
```

## Arguments

- text:

  The text sent to the LLM. When constructed by the chat module, this
  defaults to a descriptive string like
  `"The user entered the /greet slash command with arguments: world"`.
  Set it in the handler to control what the LLM actually sees.

- command:

  The slash command name (without the leading `/`).

- user_text:

  The text the user typed after the command name. Defaults to `""`.

## Value

A `ContentSlashCommand` object.

## How it works

Slash command handlers that accept an argument receive a
`ContentSlashCommand` object rather than a plain string. The object has
three properties:

- `command`: the command name (e.g., `"greet"`).

- `user_text`: the text the user typed after the command (e.g.,
  `"world"`).

- `text`: the text that will be sent to the LLM. This starts as a
  descriptive string like
  `"The user entered the /greet slash command with arguments: world"`.
  Set it to whatever text the LLM should actually see.

Because `ContentSlashCommand` extends
[ellmer::ContentText](https://ellmer.tidyverse.org/reference/Content.html),
it works anywhere a `ContentText` does – including `client$stream()`,
`client$chat()`, etc. LLM providers read the `text` property (inherited
behavior), while
[`contents_shinychat()`](https://posit-dev.github.io/shinychat/r/dev/reference/contents_shinychat.md)
reconstructs the original `/command user_text` for display in the chat
UI.

Bookmark serialization via
[`ellmer::contents_record()`](https://ellmer.tidyverse.org/reference/contents_record.html)
/
[`ellmer::contents_replay()`](https://ellmer.tidyverse.org/reference/contents_record.html)
is automatic.

## Example

    chat$slash_command("greet", "Greet someone", function(content) {
      content@text <- paste("Say hello to", content@user_text)
      stream <- client$stream(content)
      chat_append("chat", stream)
    })

The LLM sees `"Say hello to world"`, but on restore the chat UI shows
`/greet world`.

## See also

[`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)
for registering slash commands via the `slash_command()` method on the
returned object.
