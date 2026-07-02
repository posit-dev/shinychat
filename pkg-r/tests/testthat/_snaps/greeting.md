# chat_ui() snapshot for plain string greeting

    Code
      chat_ui("chat", greeting = "## Welcome!")
    Output
      <shiny-chat-container class="html-fill-item html-fill-container" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill greeting="{&quot;content&quot;:&quot;## Welcome!&quot;,&quot;content_type&quot;:&quot;markdown&quot;,&quot;options&quot;:{&quot;persistent&quot;:false}}" id="chat" max-attachment-size="31457280" placeholder="Enter a message..." style="--_width:min(680px, 100%);height:auto;">
        <shiny-chat-messages></shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
      </shiny-chat-container>

# chat_ui() snapshot for chat_greeting with persistent=TRUE

    Code
      chat_ui("chat", greeting = chat_greeting("## Hi", persistent = TRUE))
    Output
      <shiny-chat-container class="html-fill-item html-fill-container" data-require-bs-caller="chat_ui" data-require-bs-version="5" fill greeting="{&quot;content&quot;:&quot;## Hi&quot;,&quot;content_type&quot;:&quot;markdown&quot;,&quot;options&quot;:{&quot;persistent&quot;:true}}" id="chat" max-attachment-size="31457280" placeholder="Enter a message..." style="--_width:min(680px, 100%);height:auto;">
        <shiny-chat-messages></shiny-chat-messages>
        <shiny-chat-input id="chat_user_input" placeholder="Enter a message..."></shiny-chat-input>
      </shiny-chat-container>

