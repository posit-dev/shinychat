# shinychat (development version)

* Added new `output_markdown_stream()` and `markdown_stream()` functions to allow for streaming markdown content to the client. This is useful for showing Generative AI responses in real-time in a Shiny app, outside of a chat interface. (#23)

* Both `chat_ui()` and `output_markdown_stream()` now support arbirary Shiny UI elements inside of messages. This allows for gathering input from the user (e.g., `selectInput()`), displaying of rich output (e.g., `{htmlwidgets}` like `{plotly}`), and more. (#1868)

* Added a new `chat_clear()` function to clear the chat of all messages. (#25)

* Added `chat_app()`, `chat_mod_ui()` and `chat_mod_server()`. `chat_app()` takes an `ellmer::Chat` client and launches a simple Shiny app interface with the chat. `chat_mod_ui()` and `chat_mod_server()` replicate the interface as a Shiny module, for easily adding a simple chat interface connected to a specific `ellmer::Chat` client. (#36)

# shinychat 0.1.1

* Initial CRAN submission.
