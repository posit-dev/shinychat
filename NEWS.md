# shinychat (development version)

* Added new `output_markdown_stream()` and `markdown_stream()` functions to allow for streaming markdown content to the client. This is useful for showing Generative AI responses in real-time in a Shiny app, outside of a chat interface. (#23)

* Both `chat_ui()` and `output_markdown_stream()` now support arbirary Shiny UI elements inside of messages. This allows for gathering input from the user (e.g., `selectInput()`), displaying of rich output (e.g., `{htmlwidgets}` like `{plotly}`), and more. (#1868)

* Added a new `chat_clear()` function to clear the chat of all messages. (#25)

* `chat_append()`, `chat_append_message()` and `chat_clear()` now all work in Shiny modules without needing to namespace the `id` of the Chat component. (#37)

# shinychat 0.1.1

* Initial CRAN submission.
