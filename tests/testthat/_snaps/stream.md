# Chat component markup

    Code
      output_markdown_stream("stream")
    Output
      <shiny-markdown-stream id="stream" style="width:100%;height:auto;" content="" content-type="markdown" auto-scroll="TRUE"></shiny-markdown-stream>

---

    Code
      output_markdown_stream("stream", content = "Foo\nBar")
    Output
      <shiny-markdown-stream id="stream" style="width:100%;height:auto;" content="Foo&#10;Bar" content-type="markdown" auto-scroll="TRUE"></shiny-markdown-stream>

---

    Code
      render_tags(output_markdown_stream("stream", content = div("Hello",
        htmlDependency("foo", "1.0.0", ""))))
    Output
      $deps
      [{"name":"foo","all_files":true},{"name":"shinychat","script":{"src":"markdown-stream/markdown-stream.js","type":"module"},"stylesheet":"markdown-stream/markdown-stream.css","all_files":true}] 
      
      $html
      <shiny-markdown-stream id="stream" style="width:100%;height:auto;" content="&lt;div&gt;Hello&lt;/div&gt;" content-type="markdown" auto-scroll="TRUE"></shiny-markdown-stream>
      

