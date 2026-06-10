#' Slash command content
#'
#' @description
#' An [ellmer::ContentText] subclass that preserves the original slash command
#' entered by the user. When the chat UI is restored from a bookmark (or
#' pre-existing turns), the original `/command args` is shown in the UI
#' instead of the (possibly transformed) `text` that was sent to the LLM.
#'
#' @details
#' # How it works
#'
#' Slash command handlers that accept an argument receive a
#' `ContentSlashCommand` object rather than a plain string. The object has
#' three properties:
#'
#' * `command`: the command name (e.g., `"greet"`).
#' * `args`: the text the user typed after the command (e.g., `"world"`).
#' * `text`: the text that will be sent to the LLM. This starts as a
#'   descriptive string like
#'   `"The user entered the /greet slash command with arguments: world"`.
#'   Set it to whatever text the LLM should actually see.
#'
#' Because `ContentSlashCommand` extends [ellmer::ContentText], it works
#' anywhere a `ContentText` does -- including `client$stream()`,
#' `client$chat()`, etc. LLM providers read the `text` property
#' (inherited behavior), while `contents_shinychat()` reconstructs the
#' original `/command args` for display in the chat UI.
#'
#' Bookmark serialization via [ellmer::contents_record()] /
#' [ellmer::contents_replay()] is automatic.
#'
#' # Example
#'
#' ```r
#' chat$slash_command("greet", "Greet someone", function(content) {
#'   content@text <- paste("Say hello to", content@args)
#'   stream <- client$stream(content)
#'   chat_append("chat", stream)
#' })
#' ```
#'
#' The LLM sees `"Say hello to world"`, but on restore the chat UI shows
#' `/greet world`.
#'
#' @param command The slash command name (without the leading `/`).
#' @param args The arguments string provided by the user (the text after the
#'   command name). Defaults to `""`.
#' @param text The text sent to the LLM. When constructed by the chat module,
#'   this defaults to a descriptive string like
#'   `"The user entered the /greet slash command with arguments: world"`.
#'   Set it in the handler to control what the LLM actually sees.
#'
#' @return A `ContentSlashCommand` object.
#'
#' @seealso [chat_mod_server()] for registering slash commands via the
#'   `slash_command()` method on the returned module object.
#'
#' @export
ContentSlashCommand <- S7::new_class(
  "ContentSlashCommand",
  parent = ellmer::ContentText,
  properties = list(
    command = new_property(
      class_character,
      validator = function(value) {
        if (length(value) != 1 || is.na(value)) {
          "must be a single non-missing string."
        }
      }
    ),
    args = new_property(
      class_character,
      default = "",
      validator = function(value) {
        if (length(value) != 1 || is.na(value)) {
          "must be a single non-missing string."
        }
      }
    )
  )
)
