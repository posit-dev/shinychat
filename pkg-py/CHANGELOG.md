# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [UNRELEASED]

* Numerous `Chat()` features have been deprecated in preparation for future removal to simplify the API (#91)
  * `Chat(messages=...)` was deprecated. Use `chat.ui(messages=...)` instead.
  * `Chat(tokenizer=...)` was deprecated. This is only relevant for `.messages(token_limits=...)` which is also now deprecated.
  * All parameters to `.messages()` were deprecated. This reflects an overall change philosophy for maintaining the conversation history sent to the LLM -- `Chat` should no longer be responsible for maintaining it -- another stateful object (perhaps the one provided by chatlas, LangChain, etc.) should be used instead. That said, `.messages()` is still useful if you want to access UI message state.
  * The `.transform_user_input` and `.transform_assistant_response` decorators were deprecated. Instead, transformation of input/responses should be done manually and independently of `Chat`.
  * As a result of the previous deprecations, `.user_input(transform=...)` was also deprecated.

* The chat input no longer submits incomplete text when the user has activated IME completions (e.g. while typing in Japanese or Chinese). (#85)


## [0.1.0] - 2025-08-07

This first release of the `shinychat` package simply copies the `Chat` and `MarkdownStream` components exactly as they are in version 1.4.0 of `shiny`. Future versions of `shiny` will import these components from `shinychat`. By maintaining these components via a separate library, we can ship features more quickly and independently of `shiny`.
