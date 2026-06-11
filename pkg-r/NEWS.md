# shinychat (development version)

## New features and improvements

* Added slash commands: a typeahead command palette that lets users trigger named shortcuts directly from the chat input. Type `/` to open the palette, filter by typing, and pick a command with arrow keys or click. Commands can expand into LLM prompts, trigger server-side side effects (clear chat, open a modal, export transcript), or be handled entirely client-side via the cancelable `shiny:chat-slash-command` DOM event. Register commands with `chat$slash_command()`, which accepts 0- or 1-argument handlers; 1-argument handlers receive a `ContentSlashCommand` object (a `ContentText` subclass with `command` and `user_text` slots) so handlers can mutate `content@text` before passing it to `client$stream()`. The `echo` parameter controls whether an invocation is recorded as a user message and triggers a loading state. Echoed commands are faithfully restored on bookmark/restore. (#239)

* Added `submit_key` parameter to `chat_ui()` and `chat_mod_ui()`: `"enter"` (default, Enter submits) or `"enter+modifier"` (Ctrl/Cmd+Enter submits, plain Enter inserts a line break). The input remains editable while a response is streaming — only submission is blocked, not typing. (#251)

## Bug fixes

* Fixed the copy button on code blocks not working in some embedded contexts. (@thisisnic, #247)

# shinychat 0.4.0

## Experimental internal changes

* The chat UI's rendering layer has been migrated from Lit to React. This significantly improves streaming performance — incoming chunks no longer clear previous DOM state — and makes the codebase more maintainable. One trade-off is that certain Shiny UI elements embedded in chat messages may not work as well as before (e.g., inline `<script>` tags are generally not supported inside a React runtime). If you encounter issues, please [let us know](https://github.com/posit-dev/shinychat/issues).

## New features and improvements

* The chat UI now displays model reasoning/thinking content as collapsible panels above assistant responses. Thinking content streams in real-time with animated topic labels. This works with providers that support structured thinking (e.g., Claude's extended thinking via `ellmer`) and with local models that wrap reasoning in `<thinking>` tags. (#208)

* Added `enable_cancel` parameter to `chat_ui()` to show a stop button that lets users cancel an in-progress AI response. Press the stop button or hit Escape to cancel. `chat_mod_ui()` enables cancellation by default, and `chat_mod_server()` handles the cancellation wiring automatically, using the stream cancellation features introduced in ellmer v0.4.1. (#221)

* Markdown lists where every item is a `<span class="suggestion">` are now rendered as a grid of clickable suggestion cards. Each suggestion's text content becomes both the card label and the value sent on click. To add a short heading above the body text, set the `title` attribute on the span — e.g. `<span class="suggestion" title="Heading">Body text shown on the card.</span>`. Only the body text (not the title) is submitted when the card is clicked. Cards stream in with staggered animations and support keyboard navigation (arrow keys, Home/End) with roving tabindex. (#219)

* Added `chat_greeting()` for creating welcome messages that appear when the chat is empty. Greetings can be set statically via `chat_ui(greeting=)` or dynamically from the server with `chat_set_greeting()`. They are automatically dismissed when the user sends their first message. A new `greeting_requested` input fires when the chat is visible, empty, and has no greeting, enabling LLM-generated welcome messages. `chat_mod_server(greeting=)` accepts a function for auto-generated greetings. (#217)

* Tool result cards now render images and PDFs returned by ellmer tools. When a tool returns `content_image_file()`, `content_image_url()`, or `content_pdf_file()`, the result is displayed as an inline image or a PDF filename badge. Mixed content lists (e.g., `list(ContentText("summary"), content_image_file("plot.png"))`) are rendered with items interleaved in order. (#225)

* Added `footer` parameter to `chat_ui()` for displaying arbitrary HTML content below the chat input. Useful for disclaimers, attribution, or interactive toolbars. Styled with sensible defaults and customizable via `--shiny-chat-footer-font-size` and `--shiny-chat-footer-color` CSS custom properties. (#224)

* Tool result cards now support a fullscreen toggle. Set `full_screen = TRUE` in the `display` list (or set `res$full_screen <- NA` in a custom `contents_shinychat()` method) to add a button that expands the card to fill the viewport. Press `Escape`, click the backdrop, or use the close button to exit fullscreen.

* Added `footer` field to `ToolResultDisplay` for displaying custom HTML content below the tool result card body. (#178)

* `chat_mod_server()` now returns a `set_client(new_client, sync = TRUE)` function for swapping the chat client used by the module at runtime. When `sync = TRUE` (the default), the new client inherits the current conversation's turns, system prompt, and tools so the conversation continues seamlessly. If a response is currently streaming, the swap is deferred until the stream completes. (#227)

* `chat_mod_server()` now returns a `status` reactive that reports the current interaction state: `"idle"` when no response is in progress, or `"streaming"` while a response is actively being received. (#227)

* `chat_restore()` now invisibly returns a cancel function that tears down all bookmark registrations made by that call. This is useful when swapping the chat client via `set_client()`, which handles the re-registration automatically. (#227)

## Improvements

* All navigating links in assistant messages now open in a new tab to preserve the app's session state. Cross-origin links still show the confirmation dialog; same-origin links open directly. (#238)

## Bug fixes

* Fixed the external link confirmation dialog not rendering in Safari. The backdrop overlay appeared but the dialog content was invisible due to a Bootstrap/`<dialog>` CSS interaction. (#201, #238)

* Fixed pressing Escape to dismiss the external link dialog leaving it in a broken state where subsequent link clicks no longer worked. (#238)

* Fixed an issue where user chat messages would display the default assistant icon. (#162)

# shinychat 0.3.0

## Breaking changes

* `chat_mod_server()` now returns a list of reactives for `last_input` and `last_turn`, as well functions to `update_user_input()`, `append()` and `clear()` the chat. (#130, #143, #145)

## New features

* Added `chat_restore()` which adds Shiny bookmarking hooks to save and restore the `{ellmer}` chat client. (#28, #82)

* Added `update_chat_user_input()` for programmatically updating the user input of a chat UI element. (#78)

* shinychat now shows tool call request and results in the UI, and the feature is enabled by default in `chat_app()` and the chat module (`chat_mod_server()`). When using `chat_append()` with `chat_ui()`, set `stream = "content"` when you call the `$stream_async()` method on the `ellmer::Chat` client to ensure tool calls are included in the chat stream output. Learn more in the [tool calling UI article](https://posit-dev.github.io/shinychat/r/articles/tool-ui.html). (#52)

* Added `chat_append(icon=...)` and `chat_ui(icon_assistant=...)` for customizing the icon that appears next to assistant responses. (#88)

## Improvements

* `chat_app()` now correctly restores the chat client state when refreshing the app, e.g. by reloading the page. (#71)

* External links in chat messages in `chat_ui()` now open in a new tab by default, with a confirmation dialog. (#120)

## Bug fixes

* The chat input no longer submits incomplete text when the user has activated IME completions (e.g. while typing in Japanese or Chinese). (#85)

## Internal changes

* We consolidated the `<shiny-chat-message>` and `<shiny-user-message>` components into a single `<shiny-chat-message>` component with a `data-role` attribute to indicate whether it's an "assistant" or "user" message. This likely has minimal impact on your apps, other than custom styles. You should update any `shiny-user-message` rules to use `shiny-chat-message[data-role="user"]`. (#101)

* The chat UI's send input button is now identified by the class `.shiny-chat-btn-send`. (@DeepanshKhurana, #138)

# shinychat 0.2.0

## New features and improvements

* Added new `output_markdown_stream()` and `markdown_stream()` functions to allow for streaming markdown content to the client. This is useful for showing Generative AI responses in real-time in a Shiny app, outside of a chat interface. (#23)

* Both `chat_ui()` and `output_markdown_stream()` now support arbitrary Shiny UI elements inside of messages. This allows for gathering input from the user (e.g., `selectInput()`), displaying of rich output (e.g., `{htmlwidgets}` like `{plotly}`), and more. (#29)

* Added a new `chat_clear()` function to clear the chat of all messages. (#25)

* Added `chat_app()`, `chat_mod_ui()` and `chat_mod_server()`. `chat_app()` takes an `{ellmer}` chat client and launches a simple Shiny app interface with the chat. `chat_mod_ui()` and `chat_mod_server()` replicate the interface as a Shiny module, for easily adding a simple chat interface connected to a specific `{ellmer}` chat client. (#36)

* The promise returned by `chat_append()` now resolves to the content streamed into the chat. (#49)

## Bug fixes

* `chat_append()`, `chat_append_message()` and `chat_clear()` now all work in Shiny modules without needing to namespace the `id` of the Chat component. (#37)

* `chat_append()` now logs and throws a silent error if the stream errors for any reason. This prevents the app from crashing if the stream is interrupted. You can still use `promises::catch()` to handle the error in your app code if desired. (#46)

# shinychat 0.1.1

* Initial CRAN submission.
