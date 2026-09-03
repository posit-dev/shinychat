# Chat component markup

    Code
      output_markdown_stream("stream")
    Output
      <shiny-markdown-stream id="stream" style="width:min(680px, 100%);height:auto;margin:0 auto;" content="" content-type="markdown" content-segments="[{&quot;text&quot;:&quot;&quot;,&quot;trusted&quot;:false}]" content-trusted="false" auto-scroll=""></shiny-markdown-stream>

---

    Code
      output_markdown_stream("stream", content = "Foo\nBar")
    Output
      <shiny-markdown-stream id="stream" style="width:min(680px, 100%);height:auto;margin:0 auto;" content="Foo&#10;Bar" content-type="markdown" content-segments="[{&quot;text&quot;:&quot;Foo\nBar&quot;,&quot;trusted&quot;:false}]" content-trusted="false" auto-scroll=""></shiny-markdown-stream>

---

    Code
      render_tags(output_markdown_stream("stream", content = div("Hello",
        htmlDependency("foo", "1.0.0", ""))))
    Output
      $deps
      [{"name":"foo","all_files":true},{"name":"shinychat","script":{"src":"shinychat.js","type":"module"},"stylesheet":"shinychat.css","all_files":true}] 
      
      $html
      <shiny-markdown-stream id="stream" style="width:min(680px, 100%);height:auto;margin:0 auto;" content="&lt;shiny-chat-raw-html&gt;&#10;  &lt;div&gt;Hello&lt;/div&gt;&#10;&lt;/shiny-chat-raw-html&gt;" content-type="markdown" content-segments="[{&quot;text&quot;:&quot;&lt;shiny-chat-raw-html&gt;\n  &lt;div&gt;Hello&lt;\/div&gt;\n&lt;\/shiny-chat-raw-html&gt;&quot;,&quot;trusted&quot;:true}]" content-trusted="true" auto-scroll=""></shiny-markdown-stream>
      

