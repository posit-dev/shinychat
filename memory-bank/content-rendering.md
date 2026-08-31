# Content Rendering

This document explains how chat message content flows from the server (Python/R) through the client-side (JS/React) rendering pipeline. It covers the general architecture and calls out the non-obvious design decisions that are easy to misunderstand.

## Overview

A chat message carries an ordered list of segments: string segments (markdown/html/text/thinking) and structured content blocks (tool requests, tool results, web activity, raw-HTML islands). String segments pass through three stages:

1. **Server-side preparation** (Python/R) — wraps raw HTML in `<shinychat-raw-html>` tags
2. **Client-side parsing** (unified/rehype) — parses the content string into a HAST (HTML Abstract Syntax Tree)
3. **React rendering** — converts the HAST into React elements, with special handling for certain tags

Structured blocks bypass the HAST pipeline entirely — the client converts them to render-model blocks on arrival and dispatches directly to the right component (see [Structured Content Blocks](#structured-content-blocks)).

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

## Structured Content Blocks

Tool UI, web activity, and block-level raw HTML islands no longer travel as
markup embedded in the content string. They arrive as **structured content
blocks**: typed JSON envelopes (`{type, version: 1, ...}`) that only the
server can construct. The envelope — not markup scanned out of the text
channel — is the trust signal.

### Wire model

`MessagePayload.segments` is an ordered union of string segments
(`{content, content_type: "markdown"|"html"|"text"|"thinking"}`) and
structured blocks (`SegmentPayload` in `js/src/transport/types.ts`). Block
types: `tool_request`, `tool_result`, `web_search`, `web_search_results`,
`web_fetch`, `html_block`. Streaming `chunk` actions only ever target
string segments; structured blocks arrive complete. Every block carries
`version: 1` as a forward-compatibility marker — the client warns and skips
a block whose version it predates (`structuredBlockToLoop`,
`asWebActivityWireBlock`, `asHtmlBlock`), rather than breaking the message
around it.

### Delivery

Outside a stream, blocks are inline in `message.segments`. Mid-stream, a
`block_insert` action delivers one complete block to the in-flight message
(`js/src/chat/state.ts`, `block_insert` case). A no-op with `console.warn`
when no stream is in flight. The thinking-tag/fence state machine operates
only on string content and is deliberately untouched by `block_insert`.

### Client conversion

`messagePayloadToData` walks `segments` in order and converts each block to
its render-model form on arrival:

- **Role gate** — non-`html_block` structured blocks in a user-role message
  are ignored with a warning. Tool UI and web activity are never
  legitimate in a user message. An `html_block` is a server-attested
  trusted-HTML envelope valid in any role (e.g. a user message whose content
  was authored with tags on the server), so it passes through regardless.
- **Per-type guards** — each block type is defensively narrowed: unknown
  types and unsupported versions warn and no-op (`structuredBlockToLoop`,
  `asWebActivityWireBlock`, `asHtmlBlock`). Required fields are
  type-checked; malformed blocks are skipped.
- **Tool-loop merging** — a `tool_request`/`tool_result` block becomes a
  one-call `ToolLoopBlock` (`structuredBlockToLoop`). `appendToolLoopBlock`
  merges it into an adjacent trailing tool loop when one is reachable,
  tolerating a whitespace-only content block between carriers (the
  whitespace is dropped; any other block ends the run and starts a new
  loop). This is the structured re-expression of the old `routeToolBlocks`
  adjacency grouping — same logic, operating on typed blocks instead of
  parsed markup.
- **Web-activity merging** — consecutive `web_*` blocks group into one
  `WebActivityBlock` on arrival (`appendWebActivityBlock`), with the same
  whitespace-only tolerance. Search↔results pairing works by adjacency
  (`applyWebBlock` attaches results to the earliest still-pending search),
  exactly as the markup path's `WebActivity.parseItems` did. The group
  wrapper never appears on the wire.
- **`html_block`** — arrives render-ready as an `HtmlBlock` render-model
  block carrying `content` and block-level `htmlDeps`.

### Restore

Both servers re-derive structured blocks from stored turns; old persisted UI
state is discarded, never re-parsed for trust. Python adopts R's
turns-based restore: a `Turn` normalizes its contents into an ordered
interleaving of string runs and structured blocks (`parts`), and
`StoredMessage.wire_segments()` re-interleaves them at the recorded
positions so the wire order matches the source content order
(text/tool-result/text must not arrive as text/text/tool-result).
Persisted UI markup is never scanned for trust — the envelope is
re-constructed from the turn record on every restore.

## The Trust Invariant

The structured envelope **is** the trust signal. Only the server can
construct a block, so the fields it carries are server-attested. The
client never infers trust from `content_type` or from markup parsed out of
the text channel for structured blocks.

**Server-attested HTML fields** render through the single audited
`RawHTML` sink (`js/src/chat/RawHTML.tsx`):

- `tool_result.value` when `value_type: "html"` — rendered by
  `ToolResultValue` (`ToolResult.tsx`)
- `tool_result.title` and `tool_result.icon` (also `tool_request.title`,
  `tool_request.icon`) — rendered by `ToolCard.tsx` through `RawHTML`
  (the title span and icon span)
- `tool_result.footer` — rendered by `ToolCard.tsx` through `RawHTML`
- `html_block.content` — rendered by `HtmlBlockContent`
  (`ChatMessage.tsx`) through `RawHTML`

**Text fields** are escaped: `intent`, `label`, `value_preview`,
`tool_name`, `query` (web search), `url` (web fetch).

**Code-block fields** render as markdown code blocks (escaped):
`arguments` (tool request), `request_call` (tool result).

Model output travels only in string segments and can never instantiate
tool UI. The spoofed-`<shiny-tool-result>` XSS class — where a model
emitted a forged `<shiny-tool-result value-type="html" value="…">` as
ordinary assistant markdown and reached `RawHTML` → `innerHTML` with zero
user interaction — is eliminated by construction: no markup is ever
scanned out of the text channel for trust. The untrusted component map
(`untrustedChatTagToComponentMap`) still maps tool/web tags to
`EscapedIsland` as defense in depth, so a forged tag in a markdown string
segment renders as visible literal text rather than a real (empty) DOM
element.

## Server-Side: HTML Islands

The server sends message content as an HTML string. Some of that content is "React-native" (custom elements that map to React components), and some is "opaque" server-rendered HTML (Shiny widgets, htmltools output) that React should not manage.

The `split_html_islands()` function (in both `pkg-py/src/shinychat/_html_islands.py` and `pkg-r/R/html_islands.R`) separates these two kinds of content:

- Elements with a `data-shinychat-react` attribute are emitted **bare** — they'll be mapped to React components on the client.
- Everything else is wrapped in `<shinychat-raw-html>...</shinychat-raw-html>` — these become "HTML islands" that React won't manage.

Tool elements (`<shiny-tool-request>`/`<shiny-tool-result>` with `data-shinychat-react`) are no longer emitted into content strings — tool UI travels as structured blocks now (see [Structured Content Blocks](#structured-content-blocks)). `split_html_islands()` still exists for `html_block` derivation: `ChatMessage.__init__` walks its output, turning `<shiny-chat-raw-html>` wrappers into `html_block` structured blocks (block-level raw HTML islands only; inline islands are unsupported) and rendering bare React elements as residual string content.

Example input (non-string, tag-like content):
```html
<div>Some widget output</div>
<div>More widget output</div>
```

After `split_html_islands()`:
```html
<shinychat-raw-html><div>Some widget output</div><div>More widget output</div></shinychat-raw-html>
```

`ChatMessage.__init__` then renders the wrapper's children and emits an `html_block` structured block carrying the trusted HTML and its dependencies.

## HTML Dependencies: Client-Authoritative Round-Trip

Shiny HTML dependencies (`html_deps`) attached to a message follow a round-trip that keeps the client as the source of truth for chat history. `js/src/transport/shiny-transport.ts` renders each dependency (so its CSS/JS loads immediately) *and* attaches the serialized deps to the reducer action, rather than discarding them after rendering as it did previously. The reducer in `js/src/chat/state.ts` retains them per message as `ChatMessageData.htmlDeps`, and `buildMessagesSnapshot()` includes them when building the settled-message snapshot the client reports back to the server as the `${id}_messages:shinychat.messages` input.

On the server, `messages_input_value()` (`pkg-py/src/shinychat/_input_handler.py`) deserializes that snapshot into `StoredMessage`s and parks each message's `htmlDeps` on `segments[0].html_deps` (`StoredSegment.html_deps` in `pkg-py/src/shinychat/_chat_types.py`). Because the deps travel with the message data itself, they persist through chat history and can be re-registered on restore — even in a brand-new browser session with no prior Shiny binding state. This is a new capability of the client-authoritative model; the R package does not have an equivalent round-trip.

## Client-Side: The Markdown/HAST Pipeline

On the client, message content goes through a [unified](https://unifiedjs.com/) pipeline that parses it into a HAST (HTML Abstract Syntax Tree) and then converts it to React elements.

### Processors

Four frozen processors exist for different content types (`js/src/markdown/processors.ts`):

- **`markdownProcessor`** — for LLM-generated markdown. Reserved raw-HTML island tags are escaped to literal text.
- **`trustedMarkdownProcessor`** — the same markdown pipeline, but allows server-authored raw-HTML islands.
- **`htmlProcessor`** — for raw HTML content. Minimal processing (external links, uncontrolled inputs).
- **`userMarkdownProcessor`** — for user input. HTML is escaped and sanitized.

### Raw-HTML Island Trust

Only explicitly trusted server-authored content may instantiate
`<shiny-chat-raw-html>` (or its legacy spelling) and reach `innerHTML`.
Assistant markdown uses a disguise/escape plugin pair around `rehypeRaw`, so a
model-authored island renders as visible text.

MarkdownStream carries provenance on every content message. Plain strings are
untrusted; `HTML()` and Tag content are trusted. Mixed TagLists are split at
their leaves, so a plain string cannot inherit trust from an adjacent Tag.
The client retains ordered `{text, trusted}` runs and merges only adjacent runs
with equal trust when the wire marks a chunk as a continuation. A
`segment_start` flag preserves authored composite boundaries even when adjacent
segments have equal trust. Initial mixed content carries the same structure in
the `content-segments` attribute.

Untrusted MarkdownStream segments also override the raw-island component
mapping. This is a defense in depth backstop for Markdown and the primary
protection for `content_type="html"`, whose processor intentionally performs
minimal HTML parsing.

Chat messages now carry structured content blocks alongside string
segments. Trust comes from the typed envelope — only the server can
construct a block — not from `content_type` inference. The legacy
`content_type: "html"` string-segment path (island machinery) is retained
during the transition and remains trusted-by-channel; `html_block` is the
structured replacement. Model output travels only in string segments and
can never instantiate tool UI.

### Two-Stage Rendering

`MarkdownContent` (`js/src/markdown/MarkdownContent.tsx`) is used directly by `ChatMessage` and `MarkdownStream`. It splits rendering into two memoized stages:

1. **Stage 1 (expensive):** Parse the content string into a HAST tree. Memoized by `content` + `processor`. This doesn't re-run when only `streaming` changes.
2. **Stage 2 (cheap):** Convert the HAST tree to React elements via `hastToReact()`. Re-runs when `streaming` toggles (to add/remove the streaming dot).

### Component Mapping

`hastToReact()` uses `hast-util-to-jsx-runtime`'s `components` option to map HTML tag names to React components. For assistant messages:

- `pre` → `CopyableCodeBlock`
- `table` → `BootstrapTable`
- `shinychat-raw-html` → inline adapter that renders `RawHTML`
- Additional mappings can be passed via `tagToComponentMap` (e.g., `shiny-aside` → `Aside`)

Tool requests and results are now routed exclusively from structured wire blocks (`tool_request` / `tool_result`) before Markdown rendering, so they no longer appear in the component map. The untrusted map (`untrustedChatTagToComponentMap`) still maps `shiny-tool-request`, `shiny-tool-result`, and `shiny-web-*` tags to `EscapedIsland` — a defense-in-depth spoof guard so a forged tag in a markdown string segment renders as visible literal text rather than a real (empty) DOM element.

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

In practice, HTML islands contain server-generated content (widgets, `html_block` islands) that doesn't change during streaming — the streaming content is the LLM's markdown response, which is typically separate.

### Layout Semantics

When used for HTML islands (via the `displayContents` prop), `RawHTML` also handles:

- **`display: contents`** on the wrapper div — prevents the wrapper from introducing unwanted layout (the wrapper div becomes invisible to CSS layout, and its children participate in the parent's layout directly).
- **Fill-container detection** — if the parent element has the `html-fill-container` class, the wrapper gets `html-fill-item html-fill-container` classes so the island participates in Shiny's fill layout system.

## The rehypeUnwrapBlockCEs Plugin

Markdown parsers treat inline HTML as inline content and wrap it in `<p>` tags. When the "inline" HTML is actually a block-level custom element (like `<shinychat-raw-html>`), this produces invalid HTML (`<p>` cannot contain block elements).

The `rehypeUnwrapBlockCEs` plugin (`js/src/markdown/plugins/rehypeUnwrapBlockCEs.ts`) fixes this by visiting the HAST after parsing and promoting block-level custom elements out of `<p>` parents. It splits the `<p>` into separate elements:

```
Before: <p>text <shinychat-raw-html>...</shinychat-raw-html> more text</p>
After:  <p>text </p> <shinychat-raw-html>...</shinychat-raw-html> <p>more text</p>
```

## Where RawHTML is Used

`RawHTML` is used in five contexts:

1. **HTML islands** — via the `shinychat-raw-html` component mapping in `MarkdownContent.tsx`. The inline adapter extracts the raw HTML from the HAST node and passes it to `RawHTML` with `displayContents` enabled.
2. **Tool card title and icon** — `ToolCard.tsx` uses `RawHTML` (as `span`) for the server-attested `title` and `icon` fields. These were previously ad-hoc `dangerouslySetInnerHTML`; the structured-block trust invariant routes them through the single audited sink.
3. **Tool card footers** — `ToolCard.tsx` uses `RawHTML` for server-rendered footer content.
4. **Tool result values** — `ToolResult.tsx` uses `RawHTML` when the result's `valueType` is `"html"`.
5. **`html_block` content** — `HtmlBlockContent` (`ChatMessage.tsx`) renders a structured `html_block`'s server-attested HTML through `RawHTML`. Block-level dependencies are rendered via `shiny.renderDependencies` *before* the HTML mounts (the `depsReady` gate), so a dynamically-sent island's styles/scripts are in place before its markup — and its Shiny bindings — attach.

In all cases, the purpose is the same: inject server-rendered HTML that React should not reconcile, preserving Shiny bindings.

## Known Inefficiency: The HAST Round-Trip

For HTML islands, the content goes through a round-trip:

1. Server sends HTML wrapped in `<shinychat-raw-html>`
2. The unified pipeline parses the inner HTML into HAST nodes
3. `toJsxRuntime` converts those children into React elements (passed as `children` prop to the mapped component)
4. The mapped component **ignores** those React children
5. Instead, it serializes the HAST node's children back to an HTML string via `toHtml()`
6. That string is injected via `innerHTML`

Steps 2-5 are wasted work — the inner HTML is parsed into a tree, converted to React elements (thrown away), serialized back to a string, and injected as raw HTML. The content could theoretically go straight from step 1 to step 6.

This round-trip exists because a legacy `html` string segment goes through the unified pipeline together with the rest of the message. The structured `html_block` already bypasses it — `HtmlBlockContent` passes the block's `content` straight to `RawHTML` with no HAST parse. The round-trip remains only for the retained island machinery (`html` string segments with `<shinychat-raw-html>` markup), which is itself slated for retirement once the transition completes.
