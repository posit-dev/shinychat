# chat_app() rejects startup messages while history is enabled

    Code
      chat_app(client, messages = list("Hi!"))
    Condition
      Error in `chat_app()`:
      ! `chat_app(messages = ...)` requires `history = FALSE`: startup messages can't be recorded by the conversation-history feature.
      Use the `greeting` argument for a startup message, or set `history = FALSE` if you're managing conversation state yourself.

# chat_app() forwards app options and bookmark store

    Code
      chat_app(mock_chat_client(), app_options = "not-a-list")
    Condition
      Error in `chat_app()`:
      ! `app_options` must be a list.

# chat_app() diagnoses legacy shinyApp() arguments in dots

    Code
      chat_app(client, options = list())
    Condition
      Error in `chat_app()`:
      ! `chat_app()` no longer passes `...` to `shiny::shinyApp()`.
      i Pass this list with `app_options`.

---

    Code
      chat_app(client, enableBookmarking = "server")
    Condition
      Error in `chat_app()`:
      ! `chat_app()` no longer passes `...` to `shiny::shinyApp()`.
      i Use `bookmark_store`.

---

    Code
      chat_app(client, onStart = function() NULL)
    Condition
      Error in `chat_app()`:
      ! `chat_app()` no longer passes `...` to `shiny::shinyApp()`.
      i Compose `page_chat()` and `chat_server()` manually to customize app startup.

---

    Code
      chat_app(client, uiPattern = "/chat")
    Condition
      Error in `chat_app()`:
      ! `chat_app()` no longer passes `...` to `shiny::shinyApp()`.
      i Compose `page_chat()` and `chat_server()` manually to customize the app route.

---

    Code
      chat_app(client, ui = shiny::fluidPage())
    Condition
      Error in `chat_app()`:
      ! `chat_app()` no longer passes `...` to `shiny::shinyApp()`.
      i `chat_app()` owns the app UI; compose `page_chat()` and `chat_server()` manually instead.

---

    Code
      chat_app(client, server = function(...) NULL)
    Condition
      Error in `chat_app()`:
      ! `chat_app()` no longer passes `...` to `shiny::shinyApp()`.
      i `chat_app()` owns the app server; compose `page_chat()` and `chat_server()` manually instead.

