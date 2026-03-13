# Tool Request Hiding Fix Plan

## Goal

Restore Lit-era behavior where a rendered tool result hides the matching tool request even when no explicit `"shiny-tool-request-hide"` transport message is sent.

This document is intended to be sufficient for implementation from a fresh session with no additional context.

## Problem Summary

The React migration currently hides tool requests in two ways:

1. Explicit transport action:
   - `shiny-tool-request-hide` from the backend
   - converted to `hide_tool_request` in the client state
2. Reducer-side HTML scanning:
   - only for `chunk` actions
   - only when `operation === "replace"`

That is narrower than the old Lit behavior.

Current regression:

- If a tool request is already rendered and a matching `<shiny-tool-result>` later arrives as a normal `message` action, the request stays visible.
- This also affects preloaded/restored content where the request and result are present without a separate hide event.

## Confirmed Reproducer

Test file:

- `js/tests/chat/ToolBridge.test.tsx`

Added failing test:

- `hides an existing tool request when a matching tool result arrives without an explicit hide action`

Run command:

```sh
cd js
npm test -- tests/chat/ToolBridge.test.tsx
```

Expected current result:

- test fails because `.shiny-tool-request` is still present after rendering the matching result

## Root Cause

### Current state flow

Relevant files:

- `js/src/chat/state.ts`
- `js/src/chat/ToolRequest.tsx`
- `js/src/chat/ToolResult.tsx`
- `js/src/chat/ToolResultBridge.tsx`
- `js/src/chat/context.ts`

Current behavior in `chatReducer()`:

- `message` appends a message and never scans for tool results
- `chunk` scans content for `<shiny-tool-result>` only when `operation === "replace"`
- `hide_tool_request` updates `hiddenToolRequests`

Why this is incomplete:

- `message` is a common path for assistant output
- preloaded initial content bypasses transport-time hide events entirely
- string scanning raw HTML is a brittle proxy for what actually rendered

### Old Lit behavior

The old implementation effectively hid the request when the result component mounted, which tied the behavior to rendered content rather than transport shape.

That is the behavior to restore.

## Recommended Design

Hide the request when `ToolResult` or `ToolResultBridge` renders, not only when the reducer sees a special action.

This should be treated as render-driven reconciliation:

- if a result with `requestId="x"` is present in rendered content
- then request `"x"` should be considered hidden in chat state

This keeps the behavior close to the thing that actually proves the request is complete: the visible tool result.

## Implementation Strategy

### Step 1. Add dispatch-on-mount behavior for rendered tool results

Preferred file:

- `js/src/chat/ToolResult.tsx`

Alternative:

- `js/src/chat/ToolResultBridge.tsx`

Recommended approach:

- In `ToolResult`, get `dispatch` from `useChatDispatch()`
- Add an effect that dispatches:

```ts
{ type: "hide_tool_request", requestId }
```

- Run it when the component mounts or when `requestId` changes

Why `ToolResult` is preferable:

- It expresses the invariant at the component level: when a result exists, the request should hide
- It works regardless of whether the result came from:
  - a normal `message`
  - chunked content
  - restored history
  - initial content

Implementation notes:

- `chatReducer()` already deduplicates duplicate request IDs and returns the same state for repeats
- that means dispatching on mount is safe and should not cause unnecessary rerenders after the first hide

### Step 2. Keep existing explicit hide transport support

Do not remove existing support for:

- `hide_tool_request` actions
- backend `shiny-tool-request-hide` messages

Reason:

- they are still useful
- they may hide a request before a result is rendered
- they preserve current backend compatibility

The render-driven hide should be additive, not a replacement.

### Step 3. Decide how much reducer-side HTML scanning to keep

Short-term recommendation:

- Keep existing reducer-side scanning for now
- Do not expand it further unless needed for a separate bug

Reason:

- render-driven hiding becomes the primary correctness mechanism
- reducer-side scanning can remain as a best-effort optimization for stream transitions
- removing it in the same patch increases change surface unnecessarily

Possible future cleanup:

- once render-driven hiding is established and tests are strong, consider removing HTML scanning entirely from `chatReducer()`

## Tests To Add Or Update

### 1. Keep the new failing regression test and make it pass

File:

- `js/tests/chat/ToolBridge.test.tsx`

Test already added:

- result message should hide an already-rendered request without explicit hide action

### 2. Add coverage for initial/restored content

Recommended new test file target:

- `js/tests/chat/ChatApp.test.tsx`

Suggested scenarios:

1. `initialMessages` contains:
   - one assistant message with `<shiny-tool-request request-id="r1" ...>`
   - later assistant message with `<shiny-tool-result request-id="r1" ...>`
   - expect only the result to remain visible after initial render

2. A single message contains both request and result markup:
   - verify the result-driven hide still wins

This ensures the fix is not transport-dependent.

### 3. Keep explicit hide behavior tests

Do not remove current tests that verify explicit hide messages still work.

## Detailed Code Changes

### Change A: `ToolResult.tsx`

Add:

- `useEffect`
- `useChatDispatch`

Behavior:

- dispatch `hide_tool_request` when the component is mounted

Pseudo-shape:

```ts
const dispatch = useChatDispatch()

useEffect(() => {
  dispatch({ type: "hide_tool_request", requestId })
}, [dispatch, requestId])
```

Notes:

- this requires `ToolResult` to be rendered within `ChatDispatchContext.Provider`
- current architecture already does that via `ChatApp`

### Change B: no reducer contract changes required

`chatReducer()` already supports:

- `hide_tool_request`
- duplicate suppression

So no state shape change should be needed for the first pass.

### Change C: optional comment update

If useful, update comments in:

- `js/src/chat/ToolRequest.tsx`
- `js/src/chat/state.ts`

to clarify that tool requests may be hidden either by transport or by rendered tool results.

## Validation Checklist

After implementation:

1. Run the focused regression test:

```sh
cd js
npm test -- tests/chat/ToolBridge.test.tsx
```

2. Run broader chat tests:

```sh
cd js
npm test -- tests/chat/ChatApp.test.tsx tests/chat/ChatApp.integration.test.tsx tests/chat/context-isolation.test.tsx tests/chat/state.test.ts
```

3. Run full JS suite:

```sh
cd js
npm test
```

4. Manually inspect for regressions in these behaviors:

- explicit hide message still hides requests
- a rendered result hides the request without explicit hide
- repeated mounts do not cause visible churn
- initial chat history with both request and result renders correctly

## Risks

### 1. Dispatch during render lifecycle

Using an effect in `ToolResult` is the right pattern.

Do not dispatch directly during render.

### 2. Context assumptions

If `ToolResult` is ever rendered outside `ChatApp`, `useChatDispatch()` would throw.

Before implementing, confirm all current render paths for `ToolResult` are inside the chat app context.

If that assumption is false, use one of these fallbacks:

- move the effect to `ToolResultBridge` and make it conditional on context presence
- or provide a no-op dispatch context default

Current code suggests `ToolResult` is only used inside chat rendering, so this is probably safe.

### 3. StrictMode/double-mount semantics

If React StrictMode is introduced in tests or app shells later, mount effects may run twice in development.

That should still be safe because:

- reducer deduplicates `requestId`
- duplicate hide dispatches are idempotent

## Non-Goals For This Patch

Do not combine this fix with:

- broader cleanup of reducer-side HTML scanning
- auto-scroll fixes
- `ToolCard` fullscreen fixes
- React warning cleanup around invalid DOM `class` props

Those should be handled independently to keep the patch narrow and reviewable.
