# Chat component markup

    Code
      chat_ui("chat")
    Output
      <shiny-chat-container class="html-fill-item html-fill-container" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill id="chat" placeholder="Enter a message..." style="width:min(680px, 100%);height:auto;">
        <shiny-chat-messages></shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
      </shiny-chat-container>

---

    Code
      chat_ui("chat", messages = list("Foo", "Bar"))
    Output
      <shiny-chat-container class="html-fill-item html-fill-container" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill id="chat" placeholder="Enter a message..." style="width:min(680px, 100%);height:auto;">
        <shiny-chat-messages>
          <shiny-chat-message data-role="assistant" content="Foo"></shiny-chat-message>
          <shiny-chat-message data-role="assistant" content="Bar"></shiny-chat-message>
        </shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
      </shiny-chat-container>

---

    Code
      chat_ui("chat", messages = list(list(content = "Assistant", role = "assistant"),
      list(content = "User", role = "user")))
    Output
      <shiny-chat-container class="html-fill-item html-fill-container" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill id="chat" placeholder="Enter a message..." style="width:min(680px, 100%);height:auto;">
        <shiny-chat-messages>
          <shiny-chat-message data-role="assistant" content="Assistant"></shiny-chat-message>
          <shiny-chat-message data-role="user" content="User"></shiny-chat-message>
        </shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
      </shiny-chat-container>

---

    Code
      chat_ui("chat", messages = list(div("Hello"), span("world")))
    Output
      <shiny-chat-container class="html-fill-item html-fill-container" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill id="chat" placeholder="Enter a message..." style="width:min(680px, 100%);height:auto;">
        <shiny-chat-messages>
          <shiny-chat-message data-role="assistant" content="&lt;shinychat-html&gt;&#10;  &lt;div&gt;Hello&lt;/div&gt;&#10;&lt;/shinychat-html&gt;"></shiny-chat-message>
          <shiny-chat-message data-role="assistant" content="&lt;shinychat-html&gt;&#10;  &lt;span&gt;world&lt;/span&gt;&#10;&lt;/shinychat-html&gt;"></shiny-chat-message>
        </shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
      </shiny-chat-container>

---

    Code
      render_tags(chat_ui("chat", messages = list(div("Hello", htmlDependency("foo",
        "1.0.0", "")), span("world"))))
    Output
      $deps
      [{"name":"foo","all_files":true},{"name":"shinychat","script":{"src":"shinychat.js","type":"module"},"stylesheet":"shinychat.css","all_files":true},{"name":"bslib-tag-require","script":"tag-require.js","all_files":true},{"name":"htmltools-fill","stylesheet":"fill.css","all_files":true}] 
      
      $html
      <shiny-chat-container class="html-fill-item html-fill-container" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill id="chat" placeholder="Enter a message..." style="width:min(680px, 100%);height:auto;">
        <shiny-chat-messages>
          <shiny-chat-message data-role="assistant" content="&lt;shinychat-html&gt;&#10;  &lt;div&gt;Hello&lt;/div&gt;&#10;&lt;/shinychat-html&gt;"></shiny-chat-message>
          <shiny-chat-message data-role="assistant" content="&lt;shinychat-html&gt;&#10;  &lt;span&gt;world&lt;/span&gt;&#10;&lt;/shinychat-html&gt;"></shiny-chat-message>
        </shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
      </shiny-chat-container>
      

---

    Code
      react_tag <- tags$div("react", `data-shinychat-react` = NA)
      chat_ui("chat", messages = list(tagList(tags$div("before"), react_tag, tags$div(
        "after"))))
    Output
      <shiny-chat-container class="html-fill-item html-fill-container" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill id="chat" placeholder="Enter a message..." style="width:min(680px, 100%);height:auto;">
        <shiny-chat-messages>
          <shiny-chat-message data-role="assistant" content="&lt;shinychat-html&gt;&#10;  &lt;div&gt;before&lt;/div&gt;&#10;&lt;/shinychat-html&gt;&#10;&lt;div data-shinychat-react&gt;react&lt;/div&gt;&#10;&lt;shinychat-html&gt;&#10;  &lt;div&gt;after&lt;/div&gt;&#10;&lt;/shinychat-html&gt;"></shiny-chat-message>
        </shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
      </shiny-chat-container>

