# Create a UI element for a markdown stream.

Creates a UI element for a
[`markdown_stream()`](https://posit-dev.github.io/shinychat/r/reference/markdown_stream.md).
A markdown stream can be useful for displaying generative AI responses
(outside of a chat interface), streaming logs, or other use cases where
chunks of content are generated over time.

## Usage

``` r
output_markdown_stream(
  id,
  ...,
  content = "",
  content_type = "markdown",
  auto_scroll = TRUE,
  width = "min(680px, 100%)",
  height = "auto"
)
```

## Arguments

- id:

  A unique identifier for this markdown stream.

- ...:

  Extra HTML attributes to include on the chat element

- content:

  A string of content to display before any streaming occurs. When
  `content_type` is Markdown or HTML, it may also be UI element(s) such
  as input and output bindings.

- content_type:

  The content type. Default is `"markdown"` (specifically, CommonMark).
  Supported content types include: \* `"markdown"`: markdown text,
  specifically CommonMark \* `"html"`: for rendering HTML content. \*
  `"text"`: for plain text. \* `"semi-markdown"`: for rendering
  markdown, but with HTML tags escaped.

- auto_scroll:

  Whether to automatically scroll to the bottom of a scrollable
  container when new content is added. Default is True.

- width:

  The width of the UI element.

- height:

  The height of the UI element.

## Value

A shiny tag object.

## See also

[`markdown_stream()`](https://posit-dev.github.io/shinychat/r/reference/markdown_stream.md)
