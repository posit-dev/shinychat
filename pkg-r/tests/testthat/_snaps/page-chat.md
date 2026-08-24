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

# chat_artifact_panel() validates configuration

    Code
      chat_artifact_panel(title = list())
    Condition
      Error in `chat_validate_string()`:
      ! `title` must be a single string, not an empty list.

---

    Code
      chat_artifact_panel(width = -1)
    Condition
      Error in `chat_validate_width()`:
      ! `width` must be a positive number or a non-empty CSS length.

---

    Code
      chat_artifact_panel(width = "bogus")
    Condition
      Error in `chat_validate_width()`:
      ! `width` must be a valid CSS length.
      Caused by error in `htmltools::validateCssUnit()`:
      ! "bogus" is not a valid CSS unit (e.g., "100%", "400px", "auto")

---

    Code
      chat_artifact_panel(open = "yes")
    Condition
      Error in `chat_validate_boolean()`:
      ! `open` must be `TRUE` or `FALSE`.

---

    Code
      chat_artifact_panel(data_role = "artifact")
    Condition
      Error in `chat_config_content()`:
      ! Arguments in ... must be unnamed UI content.

# chat_nav_panel() requires page-chat configuration

    Code
      chat_nav_panel("")
    Condition
      Error in `chat_validate_string()`:
      ! `title` must be a single string, not the empty string "".

---

    Code
      chat_nav_panel("Settings", value = "")
    Condition
      Error in `chat_validate_string()`:
      ! `value` must be a single string, not the empty string "".

---

    Code
      chat_nav_panel("Settings", sidebar = list())
    Condition
      Error in `chat_validate_sidebar()`:
      ! `sidebar` must be `TRUE`, `FALSE`, or a `chat_sidebar()` or `bslib::sidebar()` configuration.

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

# page_chat() builds the default fillable page contract

    Code
      cat(rendered_html, "\n", sep = "")
    Output
      <body class="bslib-page-fill bslib-gap-spacing html-fill-container" style="padding:0px;gap:0px;">
        <shiny-chat-page id="chat_page" data-chat-id="chat" data-active-page="__home__" data-require-bs-version="5" data-require-bs-caller="page_chat">
          <header class="shiny-chat-page-header" data-bs-theme="auto" data-shiny-chat-page-nav-style="underline">
            <button type="button" class="shiny-chat-page-sidebar-toggle" aria-controls="chat-sidebar" aria-expanded="false" aria-label="Toggle app menu"><svg class="shiny-chat-page-sidebar-icon bi bi-list" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M2.5 12a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5m0-4a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5m0-4a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5"/></svg></button>
            <div class="shiny-chat-page-identity">
              <span class="shiny-chat-page-identity-icon">
                <span>A</span>
              </span>
              <span class="shiny-chat-page-identity-title">Assistant</span>
            </div>
            <div class="shiny-chat-page-controls-mount shiny-chat-page-controls-mount-desktop">
              <div class="shiny-chat-page-controls">
                <nav class="shiny-chat-page-nav" aria-label="Pages"></nav>
                <div class="shiny-chat-page-toolbar">
                  <div class="shiny-chat-page-toolbar-scoped"></div>
                  <div class="shiny-chat-page-toolbar-global">
                    <div class="bslib-toolbar bslib-gap-spacing" data-align="right">
                      <bslib-input-dark-mode attribute="data-bs-theme" style="--text-1:var(--bs-emphasis-color);--text-2:var(--bs-tertiary-color);--vertical-correction: ;" data-require-bs-version="5" data-require-bs-caller="input_dark_mode()"></bslib-input-dark-mode>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </header>
          <div class="shiny-chat-page-body">
            <aside id="chat-sidebar" class="shiny-chat-page-sidebar" aria-label="App menu" data-sidebar-key="default" data-sidebar-open="auto" data-sidebar-width="280px" data-sidebar-resizable="true">
              <div class="bslib-toolbar bslib-gap-spacing" data-align="right">
                <bslib-tooltip id="chat-sidebar-close_tooltip" placement="bottom" bsOptions="[]" data-require-bs-version="5" data-require-bs-caller="tooltip()">
                  <template>Close app menu</template>
                  <button aria-labelledby="btn-label-{id}" class="btn btn-default action-button bslib-toolbar-input-button btn-sm border-0 shiny-chat-page-sidebar-close" data-type="icon" id="chat-sidebar-close" type="button"><span class="action-icon"><span class="bslib-toolbar-icon" aria-hidden="true" style="pointer-events: none"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-x" viewBox="0 0 16 16"><path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708"/></svg></span></span><span class="action-label"><span id="btn-label-{id}" class="bslib-toolbar-label" hidden>Close app menu</span></span></button>
                </bslib-tooltip>
              </div>
              <div class="shiny-chat-page-controls-mount shiny-chat-page-controls-mount-mobile"></div>
              <div class="shiny-chat-page-sidebar-panel" data-sidebar-for="default" data-sidebar-open="auto" data-sidebar-width="280px" data-sidebar-resizable="true">
                <shiny-chat-history for="chat"></shiny-chat-history>
              </div>
            </aside>
            <main class="shiny-chat-page-main">
              <section class="shiny-chat-page-panel shiny-chat-page-home" data-page-value="__home__" data-sidebar-key="default" data-page-toolbar-source="home">
                <shiny-chat-container class="html-fill-item html-fill-container" data-app-role="primary" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill id="chat" max-attachment-size="31457280" placeholder="Enter a message..." style="--_chat-width:min(680px, 100%);height:100%;" submit-key="enter+modifier">
                  <shiny-chat-messages></shiny-chat-messages>
                  <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
                  <shiny-chat-artifact width="400px"></shiny-chat-artifact>
                </shiny-chat-container>
              </section>
            </main>
          </div>
          <div class="shiny-chat-page-toolbar-sources" hidden>
            <div class="shiny-chat-page-toolbar-source" data-page-toolbar-source="home">
              <div class="shiny-chat-page-toolbar-content"></div>
            </div>
          </div>
        </shiny-chat-page>
      </body>

# page_chat() validates page-owned arguments and page metadata

    Code
      page_chat("Assistant", NULL, "extra")
    Condition
      Error in `page_chat()`:
      ! Only `title` and `icon` may be supplied positionally.

---

    Code
      page_chat("Assistant", height = "10rem", fill = FALSE)
    Condition
      Error in `page_chat()`:
      ! `page_chat()` owns `height` and `fill`.
      i Remove the supplied arguments; the page always uses `height = "100%"`, `fill = TRUE`, and `show_history = TRUE`.

---

    Code
      page_chat("Assistant", id = NULL)
    Condition
      Error in `chat_validate_plain_string()`:
      ! `id` must be a single string, not `NULL`.

---

    Code
      page_chat("", id = "chat")
    Condition
      Error in `page_chat()`:
      ! `title` must not be an empty string.

---

    Code
      page_chat(NULL)
    Condition
      Error in `chat_validate_page_ui()`:
      ! `title` must not be NULL.

---

    Code
      page_chat("Assistant", pages_navbar = chat_nav_panel("About"))
    Condition
      Error in `normalize_chat_pages()`:
      ! `pages_navbar` must be `NULL` or a list of `chat_nav_panel()` configurations and supported bslib navigation items.

---

    Code
      page_chat("Assistant", pages_navbar = list(htmltools::tags$p("About")))
    Condition
      Error in `normalize_item()`:
      ! `pages_navbar` item 1 must be a `chat_nav_panel()` configuration or a supported bslib navigation item.

---

    Code
      page_chat("Assistant", pages_navbar = list(chat_nav_panel("Home", value = "__home__")))
    Condition
      Error in `normalize_chat_pages()`:
      ! "__home__" is reserved for the main chat page and cannot be used as a page value.

---

    Code
      page_chat("Assistant", pages_navbar = list(chat_nav_panel("About"),
      chat_nav_panel("About")))
    Condition
      Error in `normalize_chat_pages()`:
      ! Each navigation page must have a unique value; "About" is duplicated.

---

    Code
      page_chat("Assistant", window_title = htmltools::HTML("Unsafe"))
    Condition
      Error in `chat_validate_plain_string()`:
      ! `window_title` must be a plain string.

---

    Code
      page_chat("Assistant", lang = "")
    Condition
      Error in `chat_validate_plain_string()`:
      ! `lang` must be a single string, not the empty string "".

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
      chat_ui("chat", artifact_panel = list())
    Condition
      Error in `normalize_chat_artifact_panel()`:
      ! `artifact_panel` must be `TRUE`, `FALSE`, or a `chat_artifact_panel()` configuration.

---

    Code
      chat_ui("chat", show_history = NA)
    Condition
      Error in `chat_validate_boolean()`:
      ! `show_history` must be `TRUE` or `FALSE`.

