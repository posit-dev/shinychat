# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-04-29

### Experimental internal changes

* The chat UI's rendering layer has been migrated from Lit to React. This significantly improves streaming performance — incoming chunks no longer clear previous DOM state — and makes the codebase more maintainable. One trade-off is that certain Shiny UI elements embedded in chat messages may not work as well as before (e.g., inline `<script>` tags are generally not supported inside a React runtime). If you encounter issues, please [let us know](https://github.com/posit-dev/shinychat/issues).

### New features

* Tool result cards now support a fullscreen toggle. Set `full_screen=True` in `ToolResultDisplay()` to add a button that expands the card to fill the viewport. Press `Escape`, click the backdrop, or use the close button to exit fullscreen. (#179)

* Added `footer` parameter to `ToolResultDisplay` for displaying custom HTML content below the tool result card body. (#178)

### Breaking changes

* Removed the deprecated `transform_user` and `transform_assistant` parameters from `.messages()`. As a result, `.messages()` now _always_ returns transformed content (i.e., the result of applying `.transform_user_input()` / `.transform_assistant_response()`, if any), meaning it's better reflection of UI state than LLM-facing message state. This change reflects a greater change in philosophy that `shinychat` shouldn't be managing LLM message state (a backend framework like `chatlas`, `langchain`, `pydantic`, etc. should do this instead). (#193)

* Removed the deprecated `transform` parameter from `.user_input()`. `.user_input()` now always returns the currently stored user message content, which matches the simplified transform handling used by `.messages()`. (#193)

* `ChatMessageDict` (returned by `.messages()`) may now include an `html_deps` key containing serialized `HTMLDependency` dicts. Code that unpacks or iterates these dicts with a fixed set of keys should be updated to handle the new field. (#193)

### Improvements

* Streaming messages now support mid-stream content type transitions. When the content type changes during streaming, previous content is preserved as a frozen segment, maintaining HTML islands and Shiny bindings. (#199)

* Replaced the custom auto-scroll implementation with the `use-stick-to-bottom` library for smoother stick-to-bottom behavior during streaming. A centered "scroll to bottom" button now appears when the user scrolls away from the bottom. (#195)

* Migrated Google provider from the deprecated `google-generativeai` SDK to `google-genai`. (#174)


### Bug fixes

* Fixed some issues with bookmarking. (#188, #192, #193)

* Fixed chat message content touching the right edge of the container. (#197)

* Fixed content inside tool cards (e.g., widgets, plots) not re-laying out when the card is collapsed or expanded. (#180)

* Fixed the chat UI crashing on non-HTTPS contexts (e.g., RStudio Server over plain HTTP) due to `crypto.randomUUID()` being unavailable outside secure contexts. (#186, #187)

* Fixed pyright 1.1.409 compatibility by adding missing `__all__` exports. (#200)

## [0.2.9] - 2026-02-09

### Improvements

* Improved scroll to bottom behavior with tool requests/results. (#157)
* Constrain images in markdown content with max-width: 100%. (#168)

### Maintenance

* Fixed an issue where user chat messages would display the default assistant icon. (#162)

* shinychat now requires Python 3.10 or later and, optionally, langchain 1.0.0 or newer. (#156)

## [0.2.8] - 2025-09-11

### Bug fixes

* Allow `chatlas.types.ToolResultDisplay` to be imported without `pydantic`.

## [0.2.7] - 2025-09-11

### Bug fixes

* Only import `pydantic` if `chatlas` is relevant.

## [0.2.6] - 2025-09-11

### Bug fixes

* `pydantic` is (once again) a soft dependency (included in the `providers` extra).

## [0.2.5] - 2025-09-11

### Bug fixes

* `chatlas` is (once again) a soft dependency (included in the `providers` extra).

## [0.2.4] - 2025-09-10

### Bug fixes

* Fixed an issue (introduced in v0.2.0) where statically rendered messages with HTML dependencies weren't being handled properly. (#134)

## [0.2.3] - 2025-09-10

### Bug fixes

* `message_content()` and `message_content_chunk()` correctly extract content from a `chatlas.Turn`. (#133)

## [0.2.2] - 2025-09-10

### Improvements

* `message_content()` and `message_content_chunk()` can now take `ChatMessage()` as input. (#132)

## [0.2.1] - 2025-09-10

### New features

* `Chat.chat_ui(messages=...)` now supports any type also supported by `message_content()`. (#131)
* `ChatMessage()` can now be constructed outside of a Shiny session. (#131)

## [0.2.0] - 2025-09-10

### New features

* New and improved UI for tool calls that occur via [chatlas](https://posit-dev.github.io/chatlas/). As a reminder, tool call displays are enabled by setting `content="all"` in chatlas' `.stream()` (or `.stream_async()`) method. See the tests under the `pkg-py/tests/playwright/tools` directory for inspiration of what is now possible with custom tool displays via the new `ToolResultDisplay` class. (#107)

* Added new `message_content()` and `message_content_chunk()` generic (`singledispatch`) functions. These functions aren't intended to be called directly by users, but instead, provide an opportunity to teach `Chat.append_message()`/`Chat.append_message_stream()` to extract message contents from different types of objects. (#96)

* External links in chat messages in `chat_ui()` now open in a new tab by default, with a confirmation dialog. (#120)

### Bug fixes

* The chat input no longer submits incomplete text when the user has activated IME completions (e.g. while typing in Japanese or Chinese). (#85)

### Deprecations

* Numerous `Chat()` features have been deprecated in preparation for future removal to simplify the API (#91)
  * `Chat(messages=...)` was deprecated. Use `chat.ui(messages=...)` instead.
  * `Chat(tokenizer=...)` was deprecated. This is only relevant for `.messages(token_limits=...)` which is also now deprecated.
  * All parameters to `.messages()` were deprecated. This reflects an overall change philosophy for maintaining the conversation history sent to the LLM -- `Chat` should no longer be responsible for maintaining it -- another stateful object (perhaps the one provided by chatlas, LangChain, etc.) should be used instead. That said, `.messages()` is still useful if you want to access UI message state.
  * The `.transform_user_input` and `.transform_assistant_response` decorators were deprecated. Instead, transformation of input/responses should be done manually and independently of `Chat`.
  * As a result of the previous deprecations, `.user_input(transform=...)` was also deprecated.

* We consolidated the `<shiny-chat-message>` and `<shiny-user-message>` components into a single `<shiny-chat-message>` component with a `data-role` attribute to indicate whether it's an "assistant" or "user" message. This likely has minimal impact on your apps, other than custom styles. You should update any `shiny-user-message` rules to use `shiny-chat-message[data-role="user"]`. (#101)

## [0.1.0] - 2025-08-07

This first release of the `shinychat` package simply copies the `Chat` and `MarkdownStream` components exactly as they are in version 1.4.0 of `shiny`. Future versions of `shiny` will import these components from `shinychat`. By maintaining these components via a separate library, we can ship features more quickly and independently of `shiny`.
