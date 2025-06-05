# Shiny Integration for React MarkdownStream

This document explains how the React-based MarkdownStream component integrates with Shiny applications.

## Overview

The Shiny integration consists of:

1. **React Component** (`MarkdownStream.tsx`) - The core UI component
2. **Shiny Wrapper** (`ShinyMarkdownStream.tsx`) - Custom element that bridges React and Shiny
3. **Custom Element** (`<shiny-markdown-stream>`) - The HTML element used in Shiny apps
4. **Message Handler** (`shinyMarkdownStreamMessage`) - Handles server-to-client communication

## Architecture

```
Shiny Server (R/Python)
       ↓ (sends messages)
Message Handler (shinyMarkdownStreamMessage)
       ↓ (updates)
Custom Element (<shiny-markdown-stream>)
       ↓ (manages)
React Component (MarkdownStream)
       ↓ (renders)
DOM / User Interface
```

## Custom Element Usage

### Basic HTML Structure

```html
<shiny-markdown-stream 
    id="my-stream"
    content="# Initial Content"
    content-type="markdown"
    auto-scroll>
</shiny-markdown-stream>
```

### Attributes

- `id` - Required unique identifier for the element
- `content` - Initial markdown/HTML content
- `content-type` - Type of content: `"markdown"`, `"semi-markdown"`, `"html"`, or `"text"`
- `streaming` - Present when content is streaming (shows animated dot)
- `auto-scroll` - Enable automatic scrolling to bottom as content updates

## Shiny Message Protocol

The component listens for `shinyMarkdownStreamMessage` custom messages with the following structure:

### Content Update Messages

```javascript
{
  id: "element-id",           // ID of the target element
  content: "New content",     // Content to add/replace
  operation: "replace",       // "replace" or "append"
  html_deps?: [...]          // Optional HTML dependencies
}
```

### Streaming State Messages

```javascript
{
  id: "element-id",           // ID of the target element
  isStreaming: true          // Boolean streaming state
}
```

## JavaScript API

### Custom Element Methods

```javascript
const element = document.getElementById('my-stream');

// Update content
element.updateContent("New content", "replace");
element.updateContent("Additional content", "append");

// Control streaming state
element.setStreaming(true);
element.setStreaming(false);

// Change content type
element.setContentType("html");

// Toggle auto-scroll
element.setAutoScroll(true);
```

### Events

The custom element dispatches these events:

```javascript
element.addEventListener('contentchange', (event) => {
  console.log('Content changed:', event.detail.content);
});

element.addEventListener('streamend', (event) => {
  console.log('Streaming ended');
});
```

## Integration with Existing Shiny Code

This React-based component is designed to be a drop-in replacement for the existing Lit-based component:

### Same Custom Element Name
- Uses `<shiny-markdown-stream>` (same as Lit version)

### Same Message Handler
- Listens for `shinyMarkdownStreamMessage` (same as Lit version)

### Same Message Format
- Compatible with existing R/Python server code

### Same Attributes
- All attributes work the same way

## Building and Including

### Build Configuration

Add this entry to your build configuration:

```typescript
{
  name: "components/shiny-markdown-stream",
  jsEntry: "src/components/ShinyMarkdownStream.tsx",
  sassEntry: "src/components/MarkdownStream.css",
}
```

### Include in HTML

```html
<!-- Include the compiled JavaScript -->
<script type="module" src="dist/components/shiny-markdown-stream.js"></script>

<!-- Include the CSS -->
<link rel="stylesheet" href="dist/components/shiny-markdown-stream.css">
```

### Bundle Requirements

The component requires these dependencies to be available:
- Preact (aliased as React)
- DOMPurify (for HTML sanitization)
- highlight.js (for syntax highlighting)
- marked (for Markdown parsing)
- clipboard (for copy-to-clipboard functionality)

## Testing

### Unit Tests

Run the test suite:

```bash
npm test ShinyMarkdownStream
```

### Demo Page

A demo page is available for testing:

```bash
# Build the demo
npm run build

# Open the demo
open src/__demos__/markdown-stream/shiny-demo.html
```

The demo includes:
- Mock Shiny object for testing
- Interactive controls for all features
- Visual feedback for message handling

## Migration from Lit

If you're migrating from the Lit-based component:

1. **No server-side changes required** - Same message format and element name
2. **Update build configuration** - Include the new React-based bundle
3. **Replace script imports** - Use the new compiled files
4. **Test thoroughly** - Verify all functionality works as expected

## Error Handling

The component includes comprehensive error handling:

- **Missing Element**: Shows error if message targets non-existent element
- **Invalid Content**: Sanitizes HTML content for security
- **Dependency Errors**: Handles HTML dependency rendering failures
- **Streaming Errors**: Gracefully handles streaming state changes

## Performance Considerations

- **Light DOM**: Uses light DOM instead of shadow DOM for style inheritance
- **React Reconciliation**: Efficient updates through React's diffing algorithm
- **Throttled Operations**: Some operations are throttled to prevent excessive updates
- **Memory Management**: Proper cleanup on element disconnect
