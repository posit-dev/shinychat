# shinychat (development version)

## New features and improvements

* Added `chat_enable_bookmarking()` which adds Shiny bookmarking hooks to save and restore the `{ellmer}` chat client. (#28)

* `chat_app()` now correctly restores the chat client state when refreshing the app, e.g. by reloading the page. (#71)

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
