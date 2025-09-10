# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [UNRELEASED]

### Improvements

* `message_content()` and `message_content_chunk()` can now take `ChatMessage()` as input. (#)

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
