# Changelog

## shinychat 0.3.0

CRAN release: 2025-11-20

### Breaking changes

- [`chat_mod_server()`](https://posit-dev.github.io/shinychat/r/reference/chat_app.md)
  now returns a list of reactives for `last_input` and `last_turn`, as
  well functions to `update_user_input()`,
  [`append()`](https://rdrr.io/r/base/append.html) and `clear()` the
  chat. ([\#130](https://github.com/posit-dev/shinychat/issues/130),
  [\#143](https://github.com/posit-dev/shinychat/issues/143),
  [\#145](https://github.com/posit-dev/shinychat/issues/145))

### New features

- Added
  [`chat_restore()`](https://posit-dev.github.io/shinychat/r/reference/chat_restore.md)
  which adds Shiny bookmarking hooks to save and restore the
  [ellmer](https://ellmer.tidyverse.org) chat client.
  ([\#28](https://github.com/posit-dev/shinychat/issues/28),
  [\#82](https://github.com/posit-dev/shinychat/issues/82))

- Added
  [`update_chat_user_input()`](https://posit-dev.github.io/shinychat/r/reference/update_chat_user_input.md)
  for programmatically updating the user input of a chat UI element.
  ([\#78](https://github.com/posit-dev/shinychat/issues/78))

- shinychat now shows tool call request and results in the UI, and the
  feature is enabled by default in
  [`chat_app()`](https://posit-dev.github.io/shinychat/r/reference/chat_app.md)
  and the chat module
  ([`chat_mod_server()`](https://posit-dev.github.io/shinychat/r/reference/chat_app.md)).
  When using
  [`chat_append()`](https://posit-dev.github.io/shinychat/r/reference/chat_append.md)
  with
  [`chat_ui()`](https://posit-dev.github.io/shinychat/r/reference/chat_ui.md),
  set `stream = "content"` when you call the `$stream_async()` method on
  the [`ellmer::Chat`](https://ellmer.tidyverse.org/reference/Chat.html)
  client to ensure tool calls are included in the chat stream output.
  Learn more in the [tool calling UI
  article](https://posit-dev.github.io/shinychat/r/articles/tool-ui.html).
  ([\#52](https://github.com/posit-dev/shinychat/issues/52))

- Added `chat_append(icon=...)` and `chat_ui(icon_assistant=...)` for
  customizing the icon that appears next to assistant responses.
  ([\#88](https://github.com/posit-dev/shinychat/issues/88))

### Improvements

- [`chat_app()`](https://posit-dev.github.io/shinychat/r/reference/chat_app.md)
  now correctly restores the chat client state when refreshing the app,
  e.g. by reloading the page.
  ([\#71](https://github.com/posit-dev/shinychat/issues/71))

- External links in chat messages in
  [`chat_ui()`](https://posit-dev.github.io/shinychat/r/reference/chat_ui.md)
  now open in a new tab by default, with a confirmation dialog.
  ([\#120](https://github.com/posit-dev/shinychat/issues/120))

### Bug fixes

- The chat input no longer submits incomplete text when the user has
  activated IME completions (e.g. while typing in Japanese or Chinese).
  ([\#85](https://github.com/posit-dev/shinychat/issues/85))

### Internal changes

- We consolidated the `<shiny-chat-message>` and `<shiny-user-message>`
  components into a single `<shiny-chat-message>` component with a
  `data-role` attribute to indicate whether it’s an “assistant” or
  “user” message. This likely has minimal impact on your apps, other
  than custom styles. You should update any `shiny-user-message` rules
  to use `shiny-chat-message[data-role="user"]`.
  ([\#101](https://github.com/posit-dev/shinychat/issues/101))

- The chat UI’s send input button is now identified by the class
  `.shiny-chat-btn-send`.
  ([@DeepanshKhurana](https://github.com/DeepanshKhurana),
  [\#138](https://github.com/posit-dev/shinychat/issues/138))

## shinychat 0.2.0

CRAN release: 2025-05-16

### New features and improvements

- Added new
  [`output_markdown_stream()`](https://posit-dev.github.io/shinychat/r/reference/output_markdown_stream.md)
  and
  [`markdown_stream()`](https://posit-dev.github.io/shinychat/r/reference/markdown_stream.md)
  functions to allow for streaming markdown content to the client. This
  is useful for showing Generative AI responses in real-time in a Shiny
  app, outside of a chat interface.
  ([\#23](https://github.com/posit-dev/shinychat/issues/23))

- Both
  [`chat_ui()`](https://posit-dev.github.io/shinychat/r/reference/chat_ui.md)
  and
  [`output_markdown_stream()`](https://posit-dev.github.io/shinychat/r/reference/output_markdown_stream.md)
  now support arbitrary Shiny UI elements inside of messages. This
  allows for gathering input from the user (e.g.,
  [`selectInput()`](https://rdrr.io/pkg/shiny/man/selectInput.html)),
  displaying of rich output (e.g.,
  [htmlwidgets](https://github.com/ramnathv/htmlwidgets) like
  [plotly](https://plotly-r.com)), and more.
  ([\#29](https://github.com/posit-dev/shinychat/issues/29))

- Added a new
  [`chat_clear()`](https://posit-dev.github.io/shinychat/r/reference/chat_clear.md)
  function to clear the chat of all messages.
  ([\#25](https://github.com/posit-dev/shinychat/issues/25))

- Added
  [`chat_app()`](https://posit-dev.github.io/shinychat/r/reference/chat_app.md),
  [`chat_mod_ui()`](https://posit-dev.github.io/shinychat/r/reference/chat_app.md)
  and
  [`chat_mod_server()`](https://posit-dev.github.io/shinychat/r/reference/chat_app.md).
  [`chat_app()`](https://posit-dev.github.io/shinychat/r/reference/chat_app.md)
  takes an [ellmer](https://ellmer.tidyverse.org) chat client and
  launches a simple Shiny app interface with the chat.
  [`chat_mod_ui()`](https://posit-dev.github.io/shinychat/r/reference/chat_app.md)
  and
  [`chat_mod_server()`](https://posit-dev.github.io/shinychat/r/reference/chat_app.md)
  replicate the interface as a Shiny module, for easily adding a simple
  chat interface connected to a specific
  [ellmer](https://ellmer.tidyverse.org) chat client.
  ([\#36](https://github.com/posit-dev/shinychat/issues/36))

- The promise returned by
  [`chat_append()`](https://posit-dev.github.io/shinychat/r/reference/chat_append.md)
  now resolves to the content streamed into the chat.
  ([\#49](https://github.com/posit-dev/shinychat/issues/49))

### Bug fixes

- [`chat_append()`](https://posit-dev.github.io/shinychat/r/reference/chat_append.md),
  [`chat_append_message()`](https://posit-dev.github.io/shinychat/r/reference/chat_append_message.md)
  and
  [`chat_clear()`](https://posit-dev.github.io/shinychat/r/reference/chat_clear.md)
  now all work in Shiny modules without needing to namespace the `id` of
  the Chat component.
  ([\#37](https://github.com/posit-dev/shinychat/issues/37))

- [`chat_append()`](https://posit-dev.github.io/shinychat/r/reference/chat_append.md)
  now logs and throws a silent error if the stream errors for any
  reason. This prevents the app from crashing if the stream is
  interrupted. You can still use
  [`promises::catch()`](https://rstudio.github.io/promises/reference/then.html)
  to handle the error in your app code if desired.
  ([\#46](https://github.com/posit-dev/shinychat/issues/46))

## shinychat 0.1.1

CRAN release: 2024-12-18

- Initial CRAN submission.
