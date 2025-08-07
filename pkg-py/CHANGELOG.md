# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [UNRELEASED]

### New features

* Added new `message_content()` and `message_chunk_content()` generic (`singledispatch`) functions. These functions aren't intended to be called directly by users, but instead, provide an opportunity to teach `Chat.append_message()`/`Chat.append_message_stream()` to extract message contents from different types of objects. (#96)

### Bug fixes

* The chat input no longer submits incomplete text when the user has activated IME completions (e.g. while typing in Japanese or Chinese). (#85)

## [0.1.0] - 2025-08-07

This first release of the `shinychat` package simply copies the `Chat` and `MarkdownStream` components exactly as they are in version 1.4.0 of `shiny`. Future versions of `shiny` will import these components from `shinychat`. By maintaining these components via a separate library, we can ship features more quickly and independently of `shiny`.
