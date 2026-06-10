#' Slash command content
#'
#' @description
#' An [ellmer::ContentText] subclass that preserves the original slash command
#' entered by the user. When the chat UI is restored from a bookmark (or
#' pre-existing turns), the original `/command args` is shown instead of the
#' `text` that was sent to the LLM.
#'
#' @details
#' Slash command handlers registered via `chat$slash_command()` receive a
#' `ContentSlashCommand` object as their argument. The `text` property starts
#' equal to `args`; transform it before passing to `client$stream()`:
#'
#' ```r
#' chat$slash_command("greet", "Greet someone", function(content) {
#'   content@text <- paste("Say hello to", content@args)
#'   stream <- client$stream(content)
#'   chat_append("chat", stream)
#' })
#' ```
#'
#' The LLM sees the `text` value; the chat UI shows `/greet <args>` on
#' restore. Bookmark serialization is handled automatically by
#' [ellmer::contents_record()] / [ellmer::contents_replay()].
#'
#' @param command The slash command name (without the leading `/`).
#' @param args The arguments string provided by the user.
#' @param text The text to send to the LLM. Defaults to `args`; set to a
#'   transformed value in the handler if the LLM should see different text.
#'
#' @return A `ContentSlashCommand` object.
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
