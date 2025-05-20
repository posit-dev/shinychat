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
          <shiny-chat-message content="Foo"></shiny-chat-message>
          <shiny-chat-message content="Bar"></shiny-chat-message>
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
          <shiny-chat-message content="Assistant"></shiny-chat-message>
          <shiny-user-message content="User"></shiny-user-message>
        </shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
      </shiny-chat-container>

---

    Code
      chat_ui("chat", messages = list(div("Hello"), span("world")))
    Output
      <shiny-chat-container class="html-fill-item html-fill-container" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill id="chat" placeholder="Enter a message..." style="width:min(680px, 100%);height:auto;">
        <shiny-chat-messages>
          <shiny-chat-message content="&lt;div&gt;Hello&lt;/div&gt;"></shiny-chat-message>
          <shiny-chat-message content="&lt;span&gt;world&lt;/span&gt;"></shiny-chat-message>
        </shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
      </shiny-chat-container>

---

    Code
      render_tags(chat_ui("chat", messages = list(div("Hello", htmlDependency("foo",
        "1.0.0", "")), span("world"))))
    Output
      $deps
      [{"name":"foo","all_files":true},{"name":"shinychat","script":[{"src":"chat/chat.js","type":"module"},{"src":"markdown-stream/markdown-stream.js","type":"module"}],"stylesheet":["chat/chat.css","markdown-stream/markdown-stream.css"],"all_files":true},{"name":"bslib-tag-require","script":"tag-require.js","all_files":true},{"name":"htmltools-fill","stylesheet":"fill.css","all_files":true}] 
      
      $html
      <shiny-chat-container class="html-fill-item html-fill-container" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill id="chat" placeholder="Enter a message..." style="width:min(680px, 100%);height:auto;">
        <shiny-chat-messages>
          <shiny-chat-message content="&lt;div&gt;Hello&lt;/div&gt;"></shiny-chat-message>
          <shiny-chat-message content="&lt;span&gt;world&lt;/span&gt;"></shiny-chat-message>
        </shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
      </shiny-chat-container>
      

