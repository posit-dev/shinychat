# Content Rendering

This document explains how chat message content flows from the server (Python/R) through the client-side (JS/React) rendering pipeline. It covers the general architecture and calls out the non-obvious design decisions that are easy to misunderstand.

## Overview

A chat message's HTML content passes through three stages:

1. **Server-side preparation** (Python/R) — wraps raw HTML in `<shinychat-raw-html>` tags
2. **Client-side parsing** (unified/rehype) — parses the content string into a HAST (HTML Abstract Syntax Tree)
3. **React rendering** — converts the HAST into React elements, with special handling for certain tags

```
Server (Python/R)                    Client (JS)
─────────────────                    ───────────
TagList/htmltools output             Message string
        │                                  │
  split_html_islands()               parseMarkdown() / parseHtml()
        │                                  │
  Wraps non-React HTML in           HAST (Abstract Syntax Tree)
  <shinychat-raw-html>                     │
        │                            rehype plugins
        │                          (unwrap block CEs, etc.)
        │                                  │
  Serialized HTML string ──────►     hastToReact()
                                           │
                                     React elements
                                    (with component mapping)
```

## Server-Side: HTML Islands

The server sends message content as an HTML string. Some of that content is "React-native" (custom elements like `<shiny-tool-request>` that map to React components), and some is "opaque" server-rendered HTML (Shiny widgets, htmltools output) that React should not manage.

The `split_html_islands()` function (in both `pkg-py/src/shinychat/_html_islands.py` and `pkg-r/R/html_islands.R`) separates these two kinds of content:

- Elements with a `data-shinychat-react` attribute are emitted **bare** — they'll be mapped to React components on the client.
- Everything else is wrapped in `<shinychat-raw-html>...</shinychat-raw-html>` — these become "HTML islands" that React won't manage.

Example input:
```html
<div>Some widget output</div>
<shiny-tool-result data-shinychat-react request-id="req-1" ...></shiny-tool-result>
<div>More widget output</div>
```

After `split_html_islands()`:
```html
<shinychat-raw-html><div>Some widget output</div></shinychat-raw-html>
<shiny-tool-result data-shinychat-react request-id="req-1" ...></shiny-tool-result>
<shinychat-raw-html><div>More widget output</div></shinychat-raw-html>
```

## Client-Side: The Markdown/HAST Pipeline

On the client, message content goes through a [unified](https://unifiedjs.com/) pipeline that parses it into a HAST (HTML Abstract Syntax Tree) and then converts it to React elements.

### Processors

Three frozen processors exist for different content types (`js/src/markdown/processors.ts`):

- **`markdownProcessor`** — for LLM-generated markdown. Includes GFM, raw HTML passthrough, syntax highlighting, and several rehype plugins.
- **`htmlProcessor`** — for raw HTML content. Minimal processing (external links, uncontrolled inputs).
- **`semiMarkdownProcessor`** — for user input. HTML is escaped and sanitized.

### Two-Stage Rendering

`MarkdownContent` (`js/src/markdown/MarkdownContent.tsx`) is used directly by `ChatMessage` and `MarkdownStream`. It splits rendering into two memoized stages:

1. **Stage 1 (expensive):** Parse the content string into a HAST tree. Memoized by `content` + `processor`. This doesn't re-run when only `streaming` changes.
2. **Stage 2 (cheap):** Convert the HAST tree to React elements via `hastToReact()`. Re-runs when `streaming` toggles (to add/remove the streaming dot).

### Component Mapping

`hastToReact()` uses `hast-util-to-jsx-runtime`'s `components` option to map HTML tag names to React components. For assistant messages:

- `pre` → `CopyableCodeBlock`
- `table` → `BootstrapTable`
- `shinychat-raw-html` → inline adapter that renders `RawHTML`
- Additional mappings can be passed via `tagToComponentMap` (e.g., `shiny-tool-request` → `ToolRequestBridge`)

The `passNode: true` option means mapped components receive the raw HAST `Element` node as a prop, in addition to any converted children.

## The innerHTML Pattern (RawHTML)

`RawHTML` (`js/src/chat/RawHTML.tsx`) is the core primitive for rendering HTML that React should not own. It combines three concerns in one component:

1. **innerHTML injection** — uses a ref to opt out of React's DOM management
2. **Shiny binding** — automatically calls `bindAll`/`unbindAll` scoped to its own element
3. **Layout semantics** — optional `display: contents` and fill-container detection

```tsx
const ref = useRef<HTMLDivElement>(null)
const shiny = useContext(ShinyLifecycleContext)

useEffect(() => {
  const el = ref.current
  if (!el) return
  el.innerHTML = html
  if (shiny && html) shiny.bindAll(el)
  return () => { if (shiny && el) shiny.unbindAll(el) }
}, [html, shiny])
```

### Why not let React render the HTML normally?

When React renders DOM nodes, it "owns" them — it tracks them in its virtual DOM and may update or replace them during reconciliation. This is a problem for Shiny-bound content:

1. After React renders HTML to the DOM, Shiny's `bindAll()` attaches event handlers, observers, and state to those DOM nodes (for inputs, outputs, etc.).
2. If React later re-renders (e.g., because a new streaming chunk arrived), it may replace those DOM nodes with fresh ones.
3. The Shiny bindings are lost — inputs stop working, outputs go blank.

The `ref` + `innerHTML` pattern avoids this: React sees the wrapper div as an opaque leaf with no children to reconcile. The inner DOM nodes are invisible to React's reconciler, so Shiny bindings are preserved across re-renders.

### Self-Managed Shiny Binding

Each `RawHTML` instance manages its own Shiny bindings by consuming `ShinyLifecycleContext` directly (via `useContext`, not the throwing `useShinyLifecycle()` helper — so it works gracefully when no context is provided, e.g., in tests).

This means:
- **`bindAll` is scoped** to just the element's ref — no wasted DOM traversal over unrelated React-rendered content.
- **No streaming throttle needed** — island content doesn't change during streaming (it's server-generated, not LLM output), so the effect runs once per island.
- **`unbindAll` runs on cleanup** — covering both content changes and unmount.

This replaces the previous architecture where `ShinyBoundMarkdown` wrapped `MarkdownContent` and called `bindAll` on the entire message container with a 200ms streaming throttle. That component and the `useShinyBinding` hook have been deleted.

### When is re-rendering safe?

The `RawHTML` component instance (and its wrapper div) persists as long as React doesn't unmount it. React would only unmount it if:

- The element's **key changes** between renders
- The element's **position shifts** in a sibling list without stable keys

In practice, HTML islands contain server-generated content (tool results, widgets) that doesn't change during streaming — the streaming content is the LLM's markdown response, which is typically separate.

### Layout Semantics

When used for HTML islands (via the `displayContents` prop), `RawHTML` also handles:

- **`display: contents`** on the wrapper div — prevents the wrapper from introducing unwanted layout (the wrapper div becomes invisible to CSS layout, and its children participate in the parent's layout directly).
- **Fill-container detection** — if the parent element has the `html-fill-container` class, the wrapper gets `html-fill-item html-fill-container` classes so the island participates in Shiny's fill layout system.

## The rehypeUnwrapBlockCEs Plugin

Markdown parsers treat inline HTML as inline content and wrap it in `<p>` tags. When the "inline" HTML is actually a block-level custom element (like `<shiny-tool-request>` or `<shinychat-raw-html>`), this produces invalid HTML (`<p>` cannot contain block elements).

The `rehypeUnwrapBlockCEs` plugin (`js/src/markdown/plugins/rehypeUnwrapBlockCEs.ts`) fixes this by visiting the HAST after parsing and promoting block-level custom elements out of `<p>` parents. It splits the `<p>` into separate elements:

```
Before: <p>text <shinychat-raw-html>...</shinychat-raw-html> more text</p>
After:  <p>text </p> <shinychat-raw-html>...</shinychat-raw-html> <p>more text</p>
```

## Where RawHTML is Used

`RawHTML` is used in three contexts:

1. **HTML islands** — via the `shinychat-raw-html` component mapping in `MarkdownContent.tsx`. The inline adapter extracts the raw HTML from the HAST node and passes it to `RawHTML` with `displayContents` enabled.
2. **Tool card footers** — `ToolCard.tsx` uses `RawHTML` for server-rendered footer content.
3. **Tool result values** — `ToolResult.tsx` uses `RawHTML` when the result's `valueType` is `"html"`.

In all three cases, the purpose is the same: inject server-rendered HTML that React should not reconcile, preserving Shiny bindings.

## Known Inefficiency: The HAST Round-Trip

For HTML islands, the content goes through a round-trip:

1. Server sends HTML wrapped in `<shinychat-raw-html>`
2. The unified pipeline parses the inner HTML into HAST nodes
3. `toJsxRuntime` converts those children into React elements (passed as `children` prop to the mapped component)
4. The mapped component **ignores** those React children
5. Instead, it serializes the HAST node's children back to an HTML string via `toHtml()`
6. That string is injected via `innerHTML`

Steps 2-5 are wasted work — the inner HTML is parsed into a tree, converted to React elements (thrown away), serialized back to a string, and injected as raw HTML. The content could theoretically go straight from step 1 to step 6.

This round-trip exists because the entire message is one string that goes through the unified pipeline together. Avoiding it would require either pre-extracting island content before the pipeline or restructuring the transport layer to send content as separate segments. Neither is worth the added complexity given that the inefficiency has no observable performance impact.
