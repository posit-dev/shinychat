# chat_sidebar() validates and normalizes configuration

    Code
      chat_sidebar(history = NA)
    Condition
      Error in `chat_validate_boolean()`:
      ! `history` must be `TRUE` or `FALSE`.

---

    Code
      chat_sidebar(width = 0)
    Condition
      Error in `chat_validate_width()`:
      ! `width` must be a positive number or a non-empty CSS length.

---

    Code
      chat_sidebar(width = "bogus")
    Condition
      Error in `chat_validate_width()`:
      ! `width` must be a valid CSS length.
      Caused by error in `htmltools::validateCssUnit()`:
      ! "bogus" is not a valid CSS unit (e.g., "100%", "400px", "auto")

---

    Code
      chat_sidebar(open = "desktop")
    Condition
      Error in `chat_normalize_sidebar_open()`:
      ! `open` must be one of "auto", "open", "closed", or "always".

---

    Code
      chat_sidebar(class = "not-an-attribute")
    Condition
      Error in `chat_config_content()`:
      ! Arguments in ... must be unnamed UI content.

# chat_artifact() validates configuration

    Code
      chat_artifact(title = list())
    Condition
      Error in `chat_validate_string()`:
      ! `title` must be a string.

---

    Code
      chat_artifact(width = -1)
    Condition
      Error in `chat_validate_width()`:
      ! `width` must be a positive number or a non-empty CSS length.

---

    Code
      chat_artifact(width = "bogus")
    Condition
      Error in `chat_validate_width()`:
      ! `width` must be a valid CSS length.
      Caused by error in `htmltools::validateCssUnit()`:
      ! "bogus" is not a valid CSS unit (e.g., "100%", "400px", "auto")

---

    Code
      chat_artifact(open = "yes")
    Condition
      Error in `chat_validate_boolean()`:
      ! `open` must be `TRUE` or `FALSE`.

---

    Code
      chat_artifact(data_role = "artifact")
    Condition
      Error in `chat_config_content()`:
      ! Arguments in ... must be unnamed UI content.

# chat_nav_panel() requires page-chat configuration

    Code
      chat_nav_panel("")
    Condition
      Error in `chat_validate_string()`:
      ! `title` must be a non-empty string.

---

    Code
      chat_nav_panel("Settings", value = "")
    Condition
      Error in `chat_validate_string()`:
      ! `value` must be a non-empty string.

---

    Code
      chat_nav_panel("Settings", sidebar = list())
    Condition
      Error in `chat_validate_sidebar()`:
      ! `sidebar` must be `TRUE`, `FALSE`, or a `chat_sidebar()` configuration.

---

    Code
      chat_nav_panel("Settings", sidebar = bslib::sidebar())
    Condition
      Error in `chat_validate_sidebar()`:
      ! `sidebar` must be `TRUE`, `FALSE`, or a `chat_sidebar()` configuration.

# chat_ui_history() resolves IDs and accepts named HTML attributes

    Code
      chat_ui_history("chat", htmltools::tags$span("Nope"))
    Condition
      Error in `chat_ui_history()`:
      ! All arguments in ... must be named HTML attributes.

---

    Code
      chat_ui_history("chat", `for` = "another-chat")
    Condition
      Error in `chat_ui_history()`:
      ! `for` is managed by chat_ui_history(); supply the associated chat ID with `id`.

# chat_ui() renders configured artifact content and dependencies

    Code
      ui
    Output
      <shiny-chat-container class="html-fill-item html-fill-container" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill id="chat" max-attachment-size="31457280" placeholder="Enter a message..." style="--_chat-width:min(680px, 100%);height:auto;">
        <shiny-chat-messages></shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
        <shiny-chat-artifact title="" width="30rem" open resizable="false">
          <div>Artifact</div>
        </shiny-chat-artifact>
      </shiny-chat-container>

# chat_ui() omits disabled artifact support and history presentation

    Code
      chat_ui("chat", artifact = list())
    Condition
      Error in `normalize_chat_artifact()`:
      ! `artifact` must be `TRUE`, `FALSE`, or a `chat_artifact()` configuration.

---

    Code
      chat_ui("chat", show_history = NA)
    Condition
      Error in `chat_validate_boolean()`:
      ! `show_history` must be `TRUE` or `FALSE`.

