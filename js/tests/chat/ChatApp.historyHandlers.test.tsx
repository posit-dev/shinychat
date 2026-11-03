/**
 * Regression for roborev finding #2 (history-tree): ChatApp's handleEdit and
 * handleRetry are stable useCallbacks that read messages only through
 * messagesRef, which a useLayoutEffect keeps fresh. Two properties must hold:
 *
 * 1. Identity: message updates and paced chunk emissions re-render ChatApp,
 *    but the onEdit/onRetry callbacks handed to ChatContainer never change.
 * 2. Freshness: a handler captured at mount still guards on the LIVE exchange
 *    metadata, so under readOnly + canResubmit only the prep_failed row may
 *    retry/edit. The pre-fix code closed over the mount-time messages array
 *    (empty at capture), silently dropping every such recovery.
 *
 * Only ChatContainer — the boundary ChatApp hands its handlers to — is
 * mocked, and only to capture those props; ChatApp, the reducer, HistoryStore
 * and the transport all run for real. Assertions compare captured callback
 * identity, never the DOM.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, act } from "@testing-library/react"
import { ChatApp } from "../../src/chat/ChatApp"
import { resetHistoryStoreRegistryForTests } from "../../src/chat/historyStore"
import type { AttachmentPayload } from "../../src/chat/attachments"
import type { ChatAction } from "../../src/transport/types"
import {
  createMockTransport,
  createMockShinyLifecycle,
  installShinyWindowStub,
} from "../helpers/mocks"

type CapturedHandlers = {
  onEdit: (
    index: number,
    content: string,
    attachments: AttachmentPayload[],
  ) => void
  onRetry: (index: number) => void
}

// vi.hoisted so the vi.mock factory (hoisted above imports) can close over it.
const containerProps = vi.hoisted((): CapturedHandlers[] => [])

vi.mock("../../src/chat/ChatContainer", () => ({
  ChatContainer: function ChatContainer(props: CapturedHandlers) {
    containerProps.push({ onEdit: props.onEdit, onRetry: props.onRetry })
    return null
  },
}))

let chatSeq = 0

/**
 * Renders a completion-v2 chat, then replays a transcript whose last user
 * row (index 2) failed preparation in a read-only conversation that allows
 * explicit resubmit. Returns the transport and the ORIGINAL mount-time
 * handler capture.
 */
function renderReadOnlyFailedExchange() {
  const transport = createMockTransport()
  // Unique ids per render: history stores are keyed by elementId and outlive
  // a component across tests within this file.
  const elementId = `handlers-chat-${++chatSeq}`

  render(
    <ChatApp
      transport={transport}
      shinyLifecycle={createMockShinyLifecycle()}
      elementId={elementId}
      inputId={`${elementId}-input`}
    />,
  )

  const fire = (action: ChatAction) => {
    act(() => {
      transport.fire(elementId, action)
    })
  }

  // History restore under the completion-v2 protocol.
  fire({
    type: "history_update",
    enabled: true,
    conversations: [],
    active_id: "conv-1",
    transition_protocol: "completion-v2",
  })
  fire({
    type: "message",
    message: {
      role: "user",
      segments: [{ content: "first ask", content_type: "markdown" }],
    },
  })
  // A paced assistant stream between the two user rows.
  fire({
    type: "chunk_start",
    message: {
      role: "assistant",
      segments: [{ content: "", content_type: "markdown" }],
    },
  })
  fire({ type: "chunk", content: "assistant reply", operation: "append" })
  fire({ type: "chunk_end" })
  // Drain the StreamSmoother within a bounded window so the streamed tail
  // commits (and its paced emissions re-render ChatApp).
  act(() => {
    vi.advanceTimersByTime(1000)
  })
  fire({
    type: "message",
    message: {
      role: "user",
      segments: [{ content: "second ask", content_type: "markdown" }],
    },
  })
  // Read-only recovery: resubmit is allowed, but only for the row whose
  // exchange failed preparation.
  fire({
    type: "update_exchange_metadata",
    data: {
      2: {
        status: "error",
        retryable: true,
        preparation_failed: true,
        error_message: "Message not sent.",
      },
    },
  })
  fire({
    type: "history_update",
    enabled: true,
    conversations: [],
    active_id: "conv-1",
    active_read_only: true,
    active_can_resubmit: true,
    transition_protocol: "completion-v2",
  })

  return { transport, elementId, mountProps: containerProps[0]! }
}

function expectStableHandlerIdentity(): CapturedHandlers {
  const first = containerProps[0]!
  // Every message update, chunk emission and history change re-rendered
  // ChatApp (and therefore the mocked ChatContainer).
  expect(containerProps.length).toBeGreaterThan(5)
  for (const props of containerProps) {
    expect(props.onEdit).toBe(first.onEdit)
    expect(props.onRetry).toBe(first.onRetry)
  }
  return first
}

beforeEach(() => {
  installShinyWindowStub()
  containerProps.length = 0
})

afterEach(() => {
  resetHistoryStoreRegistryForTests()
})

describe("ChatApp history handler stability (roborev finding #2)", () => {
  it("keeps one onRetry identity that still reads live prep_failed metadata", () => {
    vi.useFakeTimers()
    try {
      const { transport, elementId, mountProps } =
        renderReadOnlyFailedExchange()

      expectStableHandlerIdentity()

      // The ORIGINAL handler, captured before any transcript or metadata
      // existed, still guards on live messages: healthy rows stay blocked,
      // the failed row retries exactly once with a fresh request id.
      act(() => mountProps.onRetry(0))
      act(() => mountProps.onRetry(1))
      expect(transport.sendMessageResubmit).not.toHaveBeenCalled()
      act(() => mountProps.onRetry(2))
      expect(transport.sendMessageResubmit).toHaveBeenCalledExactlyOnceWith(
        elementId,
        2,
        "retry",
        expect.any(String),
      )
    } finally {
      vi.useRealTimers()
    }
  })

  it("keeps one onEdit identity that still reads live prep_failed metadata", () => {
    vi.useFakeTimers()
    try {
      const { transport, elementId, mountProps } =
        renderReadOnlyFailedExchange()

      expectStableHandlerIdentity()

      act(() => mountProps.onEdit(0, "blocked edit", []))
      act(() => mountProps.onEdit(1, "blocked edit", []))
      expect(transport.sendMessageEdit).not.toHaveBeenCalled()
      act(() => mountProps.onEdit(2, "fixed content", []))
      expect(transport.sendMessageEdit).toHaveBeenCalledExactlyOnceWith(
        elementId,
        2,
        "fixed content",
        [],
        expect.any(String),
      )
    } finally {
      vi.useRealTimers()
    }
  })
})
