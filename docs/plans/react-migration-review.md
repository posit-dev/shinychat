# React Migration Code Review

Branch: `feat/react-migration`

## Bugs / Correctness Issues

### 1. Assistant processor has no sanitization (`processors.ts:25-34`)

The `assistantProcessor` chain omits `rehypeSanitize`. Initially flagged as a bug, but
**not actually an issue**: the output goes through `toJsxRuntime` (React elements), not
`innerHTML`. Script tags and event-handler attributes are inert in React's rendering model.
Updated the processor docstring to document this rationale.

**Status:** Not a bug (docstring updated)

### 2. `useAutoScroll` scroll listener leak on re-find

The hook was completely rewritten with a callback ref pattern before this review. The
scroll listener is attached once via the callback ref and uses a stable handler ref.
23 existing tests confirm correct behavior.

**Status:** Already fixed (pre-review)

### 3. `onSuggestionClick`/`onSuggestionKeydown` stale closure (`ChatContainer.tsx`)

Both were wrapped in `useCallback(fn, [])` with eslint-disable for exhaustive deps.
Not a runtime bug (ref indirection saves it), but misleading and fragile. Removed
unnecessary `useCallback` wrappers.

**Status:** Fixed

### 4. Dual subscription to transport (`ChatApp.tsx`, `ChatContainer.tsx`)

Both components subscribed to `transport.onMessage(elementId, ...)`. Not a current bug,
but fragile. Consolidated into a single subscription in `ChatApp`; imperative input
actions forwarded via `ChatContainer`'s `forwardRef` handle.

**Status:** Fixed

## Security

### 5. `dangerouslySetInnerHTML` with server-controlled `icon` HTML (`ChatMessage.tsx:62`)

Same trust model as the Lit version — carry-forward, not a regression.

**Status:** Deferred (accepted risk)

### 6. `ToolCard.formatTitle` injects `toolTitle` into HTML (`ToolCard.tsx:25-26`)

Server-controlled content, same trust boundary as Lit version.

**Status:** Deferred

## Dead Code / Unnecessary Code

### 7. `dom.ts` is unused (`utils/dom.ts`)

File no longer exists — already cleaned up.

**Status:** Already fixed (pre-review)

### 8. `customSchema` may be unused by assistant processor

Not dead code — used by `userProcessor` for defense-in-depth. Not needed for assistant
because React rendering via `toJsxRuntime` is inherently safe.

**Status:** Not a bug

### 9. `lit` still in dependencies

`chat-tools.ts` imports Lit but the `ShinyToolRequest`/`ShinyToolResult` classes are
**never registered** with `customElements.define`. The Lit rendering code is dead. However,
the file's side effects are still active:
- `window.shinychat.hiddenToolRequests` state
- `shiny-tool-request-hide` window event listener
- `shiny-tool-request-hide` Shiny message handler

These side effects may still be needed by the server-rendered tool elements. Removing
`lit` requires understanding whether React's `HIDE_TOOL_REQUEST` reducer action fully
replaces the window-level hide mechanism. Worth a separate cleanup task.

**Status:** Open (requires separate investigation)

## Design / Architecture

### 10. `MarkdownContent` re-parses markdown on every chunk

Accepted — same as Lit version, future optimization opportunity.

**Status:** Accepted

### 11. Mixed controlled/uncontrolled textarea (`ChatInput.tsx`)

Pragmatic approach, working correctly. Non-idiomatic but intentional.

**Status:** Accepted

### 12. `ExternalLinkDialog` singleton pattern

Minor — separate React root for dialog, works fine.

**Status:** Accepted

### 13. `inert` attribute type workaround (`ToolCard.tsx:84`)

Known React gap, cast is necessary.

**Status:** Accepted (minor)

## Minor / Style

### 14. Duplicate `markdownCodeBlock` function

Already extracted to `markdown/markdownCodeBlock.ts`.

**Status:** Already fixed (pre-review)

### 15. `CopyableCodeBlock`/`BootstrapTable` accept unused `node` prop

Convention from `hast-util-to-jsx-runtime` component overrides.

**Status:** Accepted (minor)

### 16. `as unknown as` casts in context defaults (`context.ts:6-8`)

Standard React pattern for contexts guaranteed to have a provider.

**Status:** Accepted (minor)
