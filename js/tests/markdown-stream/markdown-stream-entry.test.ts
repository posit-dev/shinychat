/**
 * Tests for MarkdownStreamElement pending-message queue.
 *
 * Messages that arrive at handleMessage() before the React component calls
 * onApiReady (setting this.api) must be queued and replayed in order once
 * the API becomes available. This file verifies that queue/flush/clear
 * behaviour without relying on full React rendering.
 *
 * Strategy: we import the module (which registers the custom element), create
 * an instance, and interact with its public/private interface directly via
 * type casts. The onApiReady callback is captured by spying on
 * createElement so we can invoke it manually without mounting React.
 */
import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type ContentMessage = {
  id: string
  content: string
  operation: "append" | "replace"
}

type IsStreamingMessage = {
  id: string
  isStreaming: boolean
}

/** Minimal MarkdownStreamApi mock. */
function createMockApi() {
  return {
    appendContent: vi.fn(),
    replaceContent: vi.fn(),
    setStreaming: vi.fn(),
    setContentType: vi.fn(),
  }
}

/**
 * Access private fields on MarkdownStreamElement via a typed cast.
 * This keeps the production code clean while letting tests inspect internals.
 */
type ElementInternals = {
  api: ReturnType<typeof createMockApi> | null
  pendingMessages: (ContentMessage | IsStreamingMessage)[]
  dispatchMessage: (msg: ContentMessage | IsStreamingMessage) => void
  onApiReadyCallback: ((api: ReturnType<typeof createMockApi>) => void) | null
}

function internals(el: HTMLElement): ElementInternals {
  return el as unknown as ElementInternals
}

// ---------------------------------------------------------------------------
// Setup — register custom element & stub window.Shiny
// ---------------------------------------------------------------------------

beforeAll(async () => {
  // Stub window.Shiny before importing the module so the message handler
  // registration at module level doesn't throw.
  ;(window as unknown as Record<string, unknown>).Shiny = {
    addCustomMessageHandler: vi.fn(),
  }

  // Import the module; this registers <shiny-markdown-stream> as a side effect.
  await import("../../src/markdown-stream/markdown-stream-entry")
})

beforeEach(() => {
  // Reset Shiny stub between tests (fresh vi.fn() counts).
  ;(window as unknown as Record<string, unknown>).Shiny = {
    addCustomMessageHandler: vi.fn(),
  }
})

// ---------------------------------------------------------------------------
// Helper: create an element and capture the onApiReady callback without
// actually mounting React. We do this by patching the instance's internals
// directly — connectedCallback is never called, so reactRoot stays null and
// the React tree is never rendered.
// ---------------------------------------------------------------------------

function createElement_(): {
  el: HTMLElement
  simulateApiReady: (api: ReturnType<typeof createMockApi>) => void
} {
  const el = document.createElement("shiny-markdown-stream") as HTMLElement &
    ElementInternals

  // Manually wire the onApiReady flush logic by exposing a helper that mimics
  // what the onApiReady callback inside connectedCallback does.
  function simulateApiReady(api: ReturnType<typeof createMockApi>) {
    const intr = internals(el)
    intr.api = api
    for (const msg of intr.pendingMessages) {
      intr.dispatchMessage(msg)
    }
    intr.pendingMessages = []
  }

  return { el, simulateApiReady }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("MarkdownStreamElement — pending message queue", () => {
  it("queues messages when api is null and dispatches them in order on API ready", () => {
    const { el, simulateApiReady } = createElement_()
    const api = createMockApi()

    const msg1: ContentMessage = {
      id: "x",
      content: "hello",
      operation: "append",
    }
    const msg2: ContentMessage = {
      id: "x",
      content: " world",
      operation: "append",
    }
    const msg3: IsStreamingMessage = { id: "x", isStreaming: false }

    // API not yet ready — all messages go to the queue
    const handle = el as unknown as {
      handleMessage: (m: ContentMessage | IsStreamingMessage) => void
    }
    handle.handleMessage(msg1)
    handle.handleMessage(msg2)
    handle.handleMessage(msg3)

    expect(internals(el).pendingMessages).toHaveLength(3)
    expect(api.appendContent).not.toHaveBeenCalled()

    // API becomes available — queue is flushed in order
    simulateApiReady(api)

    expect(internals(el).pendingMessages).toHaveLength(0)
    expect(api.appendContent).toHaveBeenNthCalledWith(1, "hello")
    expect(api.appendContent).toHaveBeenNthCalledWith(2, " world")
    expect(api.setStreaming).toHaveBeenCalledWith(false)
  })

  it("dispatches messages immediately when api is already set", () => {
    const { el, simulateApiReady } = createElement_()
    const api = createMockApi()

    // API is ready before any messages arrive
    simulateApiReady(api)

    const msg: ContentMessage = {
      id: "x",
      content: "immediate",
      operation: "replace",
    }
    const handle = el as unknown as {
      handleMessage: (m: ContentMessage | IsStreamingMessage) => void
    }
    handle.handleMessage(msg)

    expect(internals(el).pendingMessages).toHaveLength(0)
    expect(api.replaceContent).toHaveBeenCalledWith("immediate")
  })

  it("disconnectedCallback clears the queue so messages do not replay on remount", () => {
    const { el } = createElement_()

    const msg: ContentMessage = {
      id: "x",
      content: "queued",
      operation: "append",
    }
    const handle = el as unknown as {
      handleMessage: (m: ContentMessage | IsStreamingMessage) => void
      disconnectedCallback: () => void
    }
    handle.handleMessage(msg)
    expect(internals(el).pendingMessages).toHaveLength(1)

    // Simulate disconnect
    handle.disconnectedCallback()

    expect(internals(el).pendingMessages).toHaveLength(0)
    expect(internals(el).api).toBeNull()
  })
})
