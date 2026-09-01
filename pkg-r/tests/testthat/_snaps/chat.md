# Chat component markup

    Code
      chat_ui("chat")
    Output
      <shiny-chat-container class="html-fill-item html-fill-container" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill icon-assistant="" id="chat" max-attachment-size="31457280" placeholder="Enter a message..." style="--_chat-width:min(clamp(680px, 50vw, 760px), 100%);height:auto;">
        <shiny-chat-messages></shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
        <shiny-chat-drawer width="400px"></shiny-chat-drawer>
      </shiny-chat-container>

---

    Code
      chat_ui("chat", messages = list("Foo", "Bar"))
    Output
      <shiny-chat-container class="html-fill-item html-fill-container" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill icon-assistant="" id="chat" max-attachment-size="31457280" placeholder="Enter a message..." style="--_chat-width:min(clamp(680px, 50vw, 760px), 100%);height:auto;">
        <shiny-chat-messages>
          <shiny-chat-message data-role="assistant" content="Foo" icon=""></shiny-chat-message>
          <shiny-chat-message data-role="assistant" content="Bar" icon=""></shiny-chat-message>
        </shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
        <shiny-chat-drawer width="400px"></shiny-chat-drawer>
      </shiny-chat-container>

---

    Code
      chat_ui("chat", messages = list(list(content = "Assistant", role = "assistant"),
      list(content = "User", role = "user")))
    Output
      <shiny-chat-container class="html-fill-item html-fill-container" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill icon-assistant="" id="chat" max-attachment-size="31457280" placeholder="Enter a message..." style="--_chat-width:min(clamp(680px, 50vw, 760px), 100%);height:auto;">
        <shiny-chat-messages>
          <shiny-chat-message data-role="assistant" content="Assistant" icon=""></shiny-chat-message>
          <shiny-chat-message data-role="user" content="User"></shiny-chat-message>
        </shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
        <shiny-chat-drawer width="400px"></shiny-chat-drawer>
      </shiny-chat-container>

---

    Code
      chat_ui("chat", messages = list(div("Hello"), span("world")))
    Output
      <shiny-chat-container class="html-fill-item html-fill-container" data-initial-messages="[{&quot;role&quot;:&quot;assistant&quot;,&quot;segments&quot;:[{&quot;type&quot;:&quot;html_block&quot;,&quot;version&quot;:1,&quot;content&quot;:&quot;&lt;div&gt;Hello&lt;\/div&gt;&quot;}],&quot;icon&quot;:&quot;&quot;},{&quot;role&quot;:&quot;assistant&quot;,&quot;segments&quot;:[{&quot;type&quot;:&quot;html_block&quot;,&quot;version&quot;:1,&quot;content&quot;:&quot;&lt;span&gt;world&lt;\/span&gt;&quot;}],&quot;icon&quot;:&quot;&quot;}]" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill icon-assistant="" id="chat" max-attachment-size="31457280" placeholder="Enter a message..." style="--_chat-width:min(clamp(680px, 50vw, 760px), 100%);height:auto;">
        <shiny-chat-messages></shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
        <shiny-chat-drawer width="400px"></shiny-chat-drawer>
      </shiny-chat-container>

---

    Code
      render_tags(chat_ui("chat", messages = list(div("Hello", htmlDependency("foo",
        "1.0.0", "")), span("world"))))
    Output
      $deps
      [{"name":"shinychat","script":{"src":"shinychat.js","type":"module"},"stylesheet":"shinychat.css","all_files":true},{"name":"foo","all_files":true},{"name":"bslib-tag-require","script":"tag-require.js","all_files":true},{"name":"htmltools-fill","stylesheet":"fill.css","all_files":true}] 
      
      $html
      <shiny-chat-container class="html-fill-item html-fill-container" data-initial-messages="[{&quot;role&quot;:&quot;assistant&quot;,&quot;segments&quot;:[{&quot;type&quot;:&quot;html_block&quot;,&quot;version&quot;:1,&quot;content&quot;:&quot;&lt;div&gt;Hello&lt;\/div&gt;&quot;}],&quot;icon&quot;:&quot;&quot;},{&quot;role&quot;:&quot;assistant&quot;,&quot;segments&quot;:[{&quot;type&quot;:&quot;html_block&quot;,&quot;version&quot;:1,&quot;content&quot;:&quot;&lt;span&gt;world&lt;\/span&gt;&quot;}],&quot;icon&quot;:&quot;&quot;}]" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill icon-assistant="" id="chat" max-attachment-size="31457280" placeholder="Enter a message..." style="--_chat-width:min(clamp(680px, 50vw, 760px), 100%);height:auto;">
        <shiny-chat-messages></shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
        <shiny-chat-drawer width="400px"></shiny-chat-drawer>
      </shiny-chat-container>
      

---

    Code
      react_tag <- tags$div("react", `data-shinychat-react` = NA)
      chat_ui("chat", messages = list(tagList(tags$div("before"), react_tag, tags$div(
        "after"))))
    Output
      <shiny-chat-container class="html-fill-item html-fill-container" data-initial-messages="[{&quot;role&quot;:&quot;assistant&quot;,&quot;segments&quot;:[{&quot;type&quot;:&quot;html_block&quot;,&quot;version&quot;:1,&quot;content&quot;:&quot;&lt;div&gt;before&lt;\/div&gt;&quot;},{&quot;content&quot;:&quot;\n\n&lt;div data-shinychat-react&gt;react&lt;\/div&gt;\n\n&quot;,&quot;content_type&quot;:&quot;html&quot;},{&quot;type&quot;:&quot;html_block&quot;,&quot;version&quot;:1,&quot;content&quot;:&quot;&lt;div&gt;after&lt;\/div&gt;&quot;}],&quot;icon&quot;:&quot;&quot;}]" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill icon-assistant="" id="chat" max-attachment-size="31457280" placeholder="Enter a message..." style="--_chat-width:min(clamp(680px, 50vw, 760px), 100%);height:auto;">
        <shiny-chat-messages></shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
        <shiny-chat-drawer width="400px"></shiny-chat-drawer>
      </shiny-chat-container>

# chat_ui() emits tool-grouping only when non-default

    Code
      chat_ui("chat", tool_grouping = "all")
    Output
      <shiny-chat-container class="html-fill-item html-fill-container" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill icon-assistant="" id="chat" max-attachment-size="31457280" placeholder="Enter a message..." style="--_chat-width:min(clamp(680px, 50vw, 760px), 100%);height:auto;" tool-grouping="all">
        <shiny-chat-messages></shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
        <shiny-chat-drawer width="400px"></shiny-chat-drawer>
      </shiny-chat-container>

# chat_ui() errors for an invalid tool_grouping value

    Code
      chat_ui("chat", tool_grouping = "invalid")
    Condition
      Error in `chat_ui()`:
      ! `tool_grouping` must be one of "tool", "none", or "all", not "invalid".

