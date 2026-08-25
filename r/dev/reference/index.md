# Package index

## Chat interfaces

- [`chat_ui()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui.md)
  : Create a chat UI element
- [`chat_app()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)
  [`chat_server()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_app.md)
  : Open a live chat application in the browser
- [`chat_append()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_append.md)
  : Append an assistant response (or user message) to a chat control
- [`chat_append_message()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_append_message.md)
  : Low-level function to append a message to a chat control
- [`chat_clear()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_clear.md)
  : Clear all messages from a chat control
- [`chat_greeting()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_greeting.md)
  : Create a greeting for a chat UI
- [`chat_set_greeting()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_set_greeting.md)
  : Set the greeting for a chat UI
- [`chat_get_greeting()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_get_greeting.md)
  : Get the current greeting content
- [`update_chat_user_input()`](https://posit-dev.github.io/shinychat/r/dev/reference/update_chat_user_input.md)
  : Update the user input of a chat control

## Page chat

- [`page_chat()`](https://posit-dev.github.io/shinychat/r/dev/reference/page_chat.md)
  : Create a full-window chat page

- [`page_chat_theme()`](https://posit-dev.github.io/shinychat/r/dev/reference/page_chat_theme.md)
  :

  Create a theme for
  [`page_chat()`](https://posit-dev.github.io/shinychat/r/dev/reference/page_chat.md)

- [`chat_nav_panel()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_nav_panel.md)
  : Create a page-chat navigation panel

- [`chat_sidebar()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_sidebar.md)
  : Create a chat sidebar configuration

- [`chat_ui_history()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_ui_history.md)
  : Create a chat history selector

- [`chat_drawer()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer.md)
  : Create a chat drawer configuration

- [`chat_drawer_show()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer_show.md)
  : Show a chat drawer

- [`chat_drawer_hide()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer_hide.md)
  : Hide a chat drawer

- [`chat_drawer_toggle()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer_toggle.md)
  : Toggle a chat drawer

- [`chat_drawer_update()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_drawer_update.md)
  : Update a chat drawer

## Streaming markdown interface

- [`markdown_stream()`](https://posit-dev.github.io/shinychat/r/dev/reference/markdown_stream.md)
  : Stream markdown content
- [`output_markdown_stream()`](https://posit-dev.github.io/shinychat/r/dev/reference/output_markdown_stream.md)
  : Create a UI element for a markdown stream.

## Chat history

- [`chat_enable_history()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_enable_history.md)
  : Enable conversation history for a chat
- [`history_options()`](https://posit-dev.github.io/shinychat/r/dev/reference/history_options.md)
  : Configure chat history options
- [`ConversationStore`](https://posit-dev.github.io/shinychat/r/dev/reference/ConversationStore.md)
  : Abstract base class for conversation storage backends
- [`FileConversationStore`](https://posit-dev.github.io/shinychat/r/dev/reference/FileConversationStore.md)
  : File-based conversation storage backend
- [`chat_restore()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_restore.md)
  : Add Shiny bookmarking for shinychat

## Slash commands

- [`ContentSlashCommand()`](https://posit-dev.github.io/shinychat/r/dev/reference/ContentSlashCommand.md)
  : Slash command content

## File attachments

- [`chat_attachment()`](https://posit-dev.github.io/shinychat/r/dev/reference/chat_attachment.md)
  : Create an attachment from a local file path

## Integration with ellmer

- [`contents_shinychat()`](https://posit-dev.github.io/shinychat/r/dev/reference/contents_shinychat.md)
  : Format ellmer content for shinychat
- [`tool_result_display()`](https://posit-dev.github.io/shinychat/r/dev/reference/tool_result_display.md)
  : Customize how a tool result is displayed
