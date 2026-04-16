# Opaque HTML Islands Design

## Goal

Restore pre-React stable behavior for `shinychat-raw-html` content by treating HTML islands as server-owned opaque payloads. The markdown pipeline may identify island boundaries, but it must not define island internals.

## Decision

Adopt a compatibility-preserving opaque-island design:

- Preserve each island's original inner HTML immediately after `rehypeRaw`.
- Render islands from that preserved payload instead of recomputing HTML from `node.children`.
- Move island-local postprocessing to a DOM helper invoked by `RawHTML`.
- Reintroduce only stable-era behaviors inside islands:
  - external-link handling
  - suggestion accessibility
  - syntax highlighting for rendered code blocks

## Why

The current React pipeline parses island contents into HAST, allows rehype plugins to mutate that subtree, then serializes the mutated subtree back to HTML for `RawHTML`. That breaks the intended contract in two ways:

- islands no longer behave like ordinary non-React HTML
- unrelated rehype mutations can change the `html` prop passed to `RawHTML`, causing avoidable churn during streaming

The new boundary makes island HTML stable unless the server payload itself changes.

## Architecture

### Markdown pipeline

- Keep the existing server contract: raw HTML is wrapped in `<shinychat-raw-html>`.
- Continue parsing mixed markdown + islands in one unified pipeline.
- Add a rehype step after `rehypeRaw` that snapshots each island's original inner HTML onto the HAST node.
- Subsequent rehype plugins may continue operating on the rest of the tree, but island rendering must not depend on mutated island children.

### Rendering

- Update the `shinychat-raw-html` mapping in `MarkdownContent.tsx` to read the preserved payload from the HAST node.
- Stop using `toHtml(node.children)` as the rendering source for islands.
- Keep `RawHTML` as the rendering boundary for content React should not reconcile.

### Island enhancement

- Add a dedicated helper called by `RawHTML` after `innerHTML` assignment.
- Scope that helper strictly to the `RawHTML` container.
- The helper is responsible only for stable-era island behaviors:
  - external-link normalization
  - suggestion accessibility affordances
  - syntax highlighting of code blocks inside island HTML

## Non-goals

- Do not preserve every React-era rehype mutation inside islands.
- Do not redesign the transport layer or split message content into separate wire segments.
- Do not expand `RawHTML` into a general-purpose markdown postprocessor.

## Failure handling

- If an island lacks a preserved payload, render an empty string rather than reconstructing from mutated children.
- If island enhancement fails, leave the injected HTML in place and fail soft.
- Enhancements must never escape the island root or mutate neighboring React-rendered content.

## Testing

Add tests that cover:

- payload preservation: later rehype mutations must not change the HTML used for island rendering
- rendering source: `MarkdownContent` must render islands from preserved payload, not current children
- stable behavior inside islands:
  - external links receive stable-style behavior
  - suggestion elements receive accessibility affordances
  - raw HTML code blocks are highlighted
- streaming regression: surrounding markdown updates must not churn an unchanged island payload

## Implementation shape

Expected code changes:

- `js/src/markdown/processors.ts`
  - add a plugin that snapshots island payloads after `rehypeRaw`
- `js/src/markdown/MarkdownContent.tsx`
  - read preserved island HTML from the node
- `js/src/chat/RawHTML.tsx`
  - call a helper after HTML injection
- new helper module near `RawHTML`
  - apply stable-style DOM enhancements locally
- tests in `js/tests/markdown` and `js/tests/chat`
  - cover payload preservation and streaming stability

## Expected outcome

After this refactor, `shinychat-raw-html` islands should behave like stable-release non-React HTML embedded inside the React app: React does not own island internals, rehype ordering no longer defines island behavior, and streaming markdown updates do not reset unchanged island content.
