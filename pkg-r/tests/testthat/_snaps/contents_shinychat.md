# opt_shinychat_tool_display handles options and environment variables

    Code
      opt_shinychat_tool_display()
    Condition
      Error in `opt_shinychat_tool_display()`:
      ! `SHINYCHAT_TOOL_DISPLAY` must be one of "none", "basic", or "rich", not "invalid".

---

    Code
      opt_shinychat_tool_display()
    Condition
      Error in `opt_shinychat_tool_display()`:
      ! `shinychat.tool_display` must be one of "none", "basic", or "rich", not "invalid".

# ContentToolResult requires an associated `@request` property

    Code
      contents_shinychat(new_tool_result(request = NULL))
    Condition
      Error in `method(contents_shinychat, ellmer::ContentToolResult)`:
      ! `ContentToolResult` objects must have an associated `@request` property.

# get_tool_result_display handles invalid formats

    Code
      get_tool_result_display(result)
    Condition
      Warning:
      Invalid `@extra$display` format for `ContentToolResult` from `test-tool()` (call id: test-id).
      i To display HTML content for tool results in shinychat, create a tool result with `extra = list(display = list(html = ...))`.
      i You can also use `markdown` or `text` items in `display` to show Markdown or plain text, respectively.
    Output
      list()
      attr(,"class")
      [1] "shinychat_tool_result_display"

---

    Code
      get_tool_result_display(result)
    Condition
      Warning:
      Invalid `@extra$display` format for `ContentToolResult` from `test-tool()` (call id: test-id).
      x Expected a list with fields `title`, `icon`, `html`, `markdown`, `text`, `show_request`, `open`, `full_screen`, `footer`, `label`, `value_preview`, or `open_style`, not a string.
    Output
      list()
      attr(,"class")
      [1] "shinychat_tool_result_display"

# throws when a result does not have a `request` property

    Code
      contents_shinychat(new_tool_result(request = NULL))
    Condition
      Error in `method(contents_shinychat, ellmer::ContentToolResult)`:
      ! `ContentToolResult` objects must have an associated `@request` property.

# throws for invalid tool display option

    Code
      opt_shinychat_tool_display()
    Condition
      Error in `opt_shinychat_tool_display()`:
      ! `shinychat.tool_display` must be one of "none", "basic", or "rich", not "invalid".

# throws for invalid tool display ennvar

    Code
      opt_shinychat_tool_display()
    Condition
      Error in `opt_shinychat_tool_display()`:
      ! `SHINYCHAT_TOOL_DISPLAY` must be one of "none", "basic", or "rich", not "invalid".

# warns when `display` is not a list

    Code
      format(contents_shinychat(result))
    Condition
      Warning:
      Invalid `@extra$display` format for `ContentToolResult` from `test-tool()` (call id: test-id).
      i To display HTML content for tool results in shinychat, create a tool result with `extra = list(display = list(html = ...))`.
      i You can also use `markdown` or `text` items in `display` to show Markdown or plain text, respectively.
    Output
                 type         version      request_id       tool_name    request_call 
        "tool_result"             "1"       "test-id"     "test-tool" "`test-tool`()" 
               status      tool_title            icon          intent    show_request 
            "success"              ""          "NULL"          "NULL"          "TRUE" 
             expanded     full_screen      open_style          footer        grouping 
              "FALSE"         "FALSE"          "NULL"          "NULL"          "NULL" 
                label   value_preview           value      value_type 
               "NULL"          "NULL"            "{}"          "code" 

