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
      <shiny-markdown-stream id="stream" style="width:min(680px, 100%);height:auto;margin:0 auto;" content="&lt;div&gt;Hello&lt;/div&gt;" content-type="markdown" content-segments="[{&quot;block&quot;:{&quot;type&quot;:&quot;html_block&quot;,&quot;version&quot;:1,&quot;content&quot;:&quot;&lt;div&gt;Hello&lt;\/div&gt;&quot;,&quot;html_deps&quot;:[{&quot;name&quot;:&quot;foo&quot;,&quot;version&quot;:&quot;1.0.0&quot;,&quot;src&quot;:{&quot;href&quot;:&quot;foo-1.0.0&quot;},&quot;meta&quot;:{},&quot;script&quot;:{},&quot;stylesheet&quot;:{},&quot;head&quot;:{},&quot;attachment&quot;:{},&quot;package&quot;:{},&quot;all_files&quot;:true}]}}]" content-trusted="false" auto-scroll=""></shiny-markdown-stream>
      

