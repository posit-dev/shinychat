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
import {
  describe,
  it,
  expect,
  vi,
  beforeAll,
  beforeEach,
  afterEach,
} from "vitest"
import { act, waitFor } from "@testing-library/react"
import type { HtmlDep, StructuredBlock } from "../../src/transport/types"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type ContentMessage = {
  id: string
  content?: string
  operation: "append" | "replace"
  trusted: boolean
  segment_start: boolean
  block?: StructuredBlock
}

type IsStreamingMessage = {
  id: string
  isStreaming: boolean
}

/** Minimal MarkdownStreamApi mock. */
function createMockApi() {
  return {
    appendContent: vi.fn(),
    appendBlock: vi.fn(),
    replaceContent: vi.fn(),
    replaceWithBlock: vi.fn(),
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

afterEach(() => {
  document.body.innerHTML = ""
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
  it("renders structured initial trust segments", async () => {
    const el = document.createElement("shiny-markdown-stream")
    el.setAttribute(
      "content-segments",
      JSON.stringify([
        { text: "## Markdown", trusted: false },
        // Trusted HTML travels as raw markup — no island wrapper (the
        // island tags are dead markup, neutralized as a spoof guard).
        {
          text: "<div data-trusted>HTML</div>",
          trusted: true,
        },
      ]),
    )

    await act(async () => {
      document.body.appendChild(el)
    })

    await waitFor(() => {
      expect(el.querySelector("h2")?.textContent).toBe("Markdown")
      expect(el.querySelector("[data-trusted]")?.textContent).toBe("HTML")
    })
  })

  it("fails closed when initial provenance is malformed", async () => {
    const el = document.createElement("shiny-markdown-stream")
    el.setAttribute(
      "content",
      "<shiny-chat-raw-html><div data-forged>unsafe</div></shiny-chat-raw-html>",
    )
    el.setAttribute("content-segments", "{not-json")
    el.setAttribute("content-trusted", "true")

    await act(async () => {
      document.body.appendChild(el)
    })

    await waitFor(() => {
      expect(el.textContent).toContain("<shiny-chat-raw-html>")
    })
    expect(el.querySelector("[data-forged]")).toBeNull()
  })

  it("treats presence boolean attributes as enabled on connect", async () => {
    const el = document.createElement("shiny-markdown-stream")
    el.setAttribute("content", "streaming")
    el.setAttribute("streaming", "")
    document.body.appendChild(el)

    await waitFor(() => {
      expect(el.querySelector(".markdown-stream-dot")).toBeTruthy()
    })
  })

  it("queues messages when api is null and dispatches them in order on API ready", () => {
    const { el, simulateApiReady } = createElement_()
    const api = createMockApi()

    const msg1: ContentMessage = {
      id: "x",
      content: "hello",
      operation: "append",
      trusted: false,
      segment_start: false,
    }
    const msg2: ContentMessage = {
      id: "x",
      content: " world",
      operation: "append",
      trusted: false,
      segment_start: false,
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
    expect(api.appendContent).toHaveBeenNthCalledWith(1, "hello", false, false)
    expect(api.appendContent).toHaveBeenNthCalledWith(2, " world", false, false)
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
      trusted: true,
      segment_start: true,
    }
    const handle = el as unknown as {
      handleMessage: (m: ContentMessage | IsStreamingMessage) => void
    }
    handle.handleMessage(msg)

    expect(internals(el).pendingMessages).toHaveLength(0)
    expect(api.replaceContent).toHaveBeenCalledWith("immediate", true)
  })

  it("preserves streamed content when moved to another container", async () => {
    const left = document.createElement("div")
    const right = document.createElement("div")
    document.body.append(left, right)

    const el = document.createElement("shiny-markdown-stream")
    el.setAttribute("id", "move-stream")
    el.setAttribute("content", "initial")

    await act(async () => {
      left.appendChild(el)
    })

    // Wait for the React component to render the initial content (API ready).
    await waitFor(() => {
      expect(el.textContent).toContain("initial")
    })

    // Stream additional content that lives only in React state — it is never
    // written back to the `content` attribute.
    const handle = el as unknown as {
      handleMessage: (m: ContentMessage | IsStreamingMessage) => void
    }
    await act(async () => {
      handle.handleMessage({
        id: "move-stream",
        content: " streamed",
        operation: "append",
        trusted: false,
        segment_start: false,
      })
    })

    await waitFor(() => {
      expect(el.textContent).toContain("streamed")
    })

    // Move the element: disconnectedCallback -> connectedCallback.
    await act(async () => {
      right.appendChild(el)
    })

    await waitFor(() => {
      expect(el.textContent).toContain("initial")
    })

    // The streamed content must survive the move (proves React state preserved).
    expect(el.textContent).toContain("streamed")
  })

  it("clears the queue on genuine teardown so messages do not replay on remount", async () => {
    const { el } = createElement_()

    const msg: ContentMessage = {
      id: "x",
      content: "queued",
      operation: "append",
      trusted: false,
      segment_start: false,
    }
    const handle = el as unknown as {
      handleMessage: (m: ContentMessage | IsStreamingMessage) => void
      disconnectedCallback: () => void
    }
    handle.handleMessage(msg)
    expect(internals(el).pendingMessages).toHaveLength(1)

    // Genuine removal: disconnect with no reconnect to cancel the deferred
    // teardown, so the queue/api reset runs on the next tick.
    handle.disconnectedCallback()
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(internals(el).pendingMessages).toHaveLength(0)
    expect(internals(el).api).toBeNull()
  })
})

describe("MarkdownStreamElement — structured block messages", () => {
  const wireBlock = (content: string, html_deps?: HtmlDep[]): StructuredBlock =>
    ({
      type: "html_block",
      version: 1,
      content,
      ...(html_deps ? { html_deps } : {}),
    }) as StructuredBlock

  it("dispatches a block message to appendBlock as a render-model block", () => {
    const { el, simulateApiReady } = createElement_()
    const api = createMockApi()
    simulateApiReady(api)

    const dep = { name: "testlib", version: "1.0" } as unknown as HtmlDep
    const handle = el as unknown as {
      handleMessage: (m: ContentMessage | IsStreamingMessage) => void
    }
    handle.handleMessage({
      id: "x",
      operation: "append",
      trusted: true,
      segment_start: true,
      block: wireBlock("<div>island</div>", [dep]),
    })

    expect(api.appendContent).not.toHaveBeenCalled()
    expect(api.appendBlock).toHaveBeenCalledWith({
      type: "html_block",
      content: "<div>island</div>",
      contentType: "html",
      htmlDeps: [dep],
    })
  })

  it("dispatches a block-carrying replace to replaceWithBlock", () => {
    const { el, simulateApiReady } = createElement_()
    const api = createMockApi()
    simulateApiReady(api)

    const handle = el as unknown as {
      handleMessage: (m: ContentMessage | IsStreamingMessage) => void
    }
    handle.handleMessage({
      id: "x",
      operation: "replace",
      trusted: true,
      segment_start: true,
      block: wireBlock("<div>fresh</div>"),
    })

    // Uniform replace (kata#0r4g): wipe everything, then append the block —
    // never a string-segment replace.
    expect(api.replaceContent).not.toHaveBeenCalled()
    expect(api.replaceWithBlock).toHaveBeenCalledWith({
      type: "html_block",
      content: "<div>fresh</div>",
      contentType: "html",
      htmlDeps: [],
    })
  })

  it("drops a malformed html_block with a warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    try {
      const { el, simulateApiReady } = createElement_()
      const api = createMockApi()
      simulateApiReady(api)

      const handle = el as unknown as {
        handleMessage: (m: ContentMessage | IsStreamingMessage) => void
      }
      handle.handleMessage({
        id: "x",
        operation: "append",
        trusted: true,
        segment_start: true,
        block: {
          type: "html_block",
          version: 99,
          content: "<div>island</div>",
        } as unknown as StructuredBlock,
      })

      expect(api.appendBlock).not.toHaveBeenCalled()
      expect(api.replaceWithBlock).not.toHaveBeenCalled()
      expect(warn).toHaveBeenCalled()
    } finally {
      warn.mockRestore()
    }
  })

  it("drops a non-html_block structured block with a warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    try {
      const { el, simulateApiReady } = createElement_()
      const api = createMockApi()
      simulateApiReady(api)

      const handle = el as unknown as {
        handleMessage: (m: ContentMessage | IsStreamingMessage) => void
      }
      handle.handleMessage({
        id: "x",
        operation: "append",
        trusted: true,
        segment_start: true,
        block: {
          type: "tool_request",
          version: 1,
          request_id: "r1",
          tool_name: "my_tool",
        },
      })

      expect(api.appendBlock).not.toHaveBeenCalled()
      expect(api.replaceWithBlock).not.toHaveBeenCalled()
      expect(warn).toHaveBeenCalledWith(expect.stringContaining("tool_request"))
    } finally {
      warn.mockRestore()
    }
  })

  it("dispatches a web_search block message to appendBlock in wire form", () => {
    const { el, simulateApiReady } = createElement_()
    const api = createMockApi()
    simulateApiReady(api)

    const handle = el as unknown as {
      handleMessage: (m: ContentMessage | IsStreamingMessage) => void
    }
    handle.handleMessage({
      id: "x",
      operation: "append",
      trusted: true,
      segment_start: true,
      block: { type: "web_search", version: 1, query: "weather in Duluth" },
    })

    expect(api.appendContent).not.toHaveBeenCalled()
    // Web blocks stay in wire form across the API boundary — the grouping
    // machinery (appendWebActivityBlock) consumes wire blocks.
    expect(api.appendBlock).toHaveBeenCalledWith({
      type: "web_search",
      version: 1,
      query: "weather in Duluth",
    })
  })

  it("dispatches a block-carrying web block replace to replaceWithBlock", () => {
    const { el, simulateApiReady } = createElement_()
    const api = createMockApi()
    simulateApiReady(api)

    const handle = el as unknown as {
      handleMessage: (m: ContentMessage | IsStreamingMessage) => void
    }
    handle.handleMessage({
      id: "x",
      operation: "replace",
      trusted: true,
      segment_start: true,
      block: {
        type: "web_fetch",
        version: 1,
        url: "https://example.net/article",
        status: "success",
      },
    })

    expect(api.replaceContent).not.toHaveBeenCalled()
    expect(api.replaceWithBlock).toHaveBeenCalledWith({
      type: "web_fetch",
      version: 1,
      url: "https://example.net/article",
      status: "success",
    })
  })

  it("drops a malformed web block with a warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    try {
      const { el, simulateApiReady } = createElement_()
      const api = createMockApi()
      simulateApiReady(api)

      const handle = el as unknown as {
        handleMessage: (m: ContentMessage | IsStreamingMessage) => void
      }
      handle.handleMessage({
        id: "x",
        operation: "append",
        trusted: true,
        segment_start: true,
        // Missing the required `query` string.
        block: { type: "web_search", version: 1 } as unknown as StructuredBlock,
      })

      expect(api.appendBlock).not.toHaveBeenCalled()
      expect(api.replaceWithBlock).not.toHaveBeenCalled()
      expect(warn).toHaveBeenCalledWith(
        expect.stringContaining("malformed web_search"),
      )
    } finally {
      warn.mockRestore()
    }
  })

  it("drops a web block with an unsupported version with a warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    try {
      const { el, simulateApiReady } = createElement_()
      const api = createMockApi()
      simulateApiReady(api)

      const handle = el as unknown as {
        handleMessage: (m: ContentMessage | IsStreamingMessage) => void
      }
      handle.handleMessage({
        id: "x",
        operation: "append",
        trusted: true,
        segment_start: true,
        block: {
          type: "web_search",
          version: 99,
          query: "future",
        } as unknown as StructuredBlock,
      })

      expect(api.appendBlock).not.toHaveBeenCalled()
      expect(warn).toHaveBeenCalledWith(
        expect.stringContaining("unsupported version"),
      )
    } finally {
      warn.mockRestore()
    }
  })

  it("renders initial segments carrying web block entries, grouped", async () => {
    const el = document.createElement("shiny-markdown-stream")
    el.setAttribute(
      "content-segments",
      JSON.stringify([
        { text: "## Markdown", trusted: false },
        {
          block: { type: "web_search", version: 1, query: "weather in Duluth" },
        },
        {
          block: {
            type: "web_search_results",
            version: 1,
            sources: [{ url: "https://example.com/weather" }],
          },
        },
      ]),
    )

    await act(async () => {
      document.body.appendChild(el)
    })

    await waitFor(() => {
      expect(el.querySelector("h2")?.textContent).toBe("Markdown")
      // The two adjacent web block entries grouped into ONE activity.
      const activities = el.querySelectorAll(".shiny-web-activity")
      expect(activities).toHaveLength(1)
      expect(activities[0]!.textContent).toContain("Searched the web")
    })
  })

  it("fails closed when an initial web block entry is malformed", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    try {
      const el = document.createElement("shiny-markdown-stream")
      el.setAttribute("content", "fallback content")
      el.setAttribute(
        "content-segments",
        JSON.stringify([
          { text: "fine", trusted: false },
          // Missing the required `sources` array.
          { block: { type: "web_search_results", version: 1 } },
        ]),
      )

      await act(async () => {
        document.body.appendChild(el)
      })

      // The whole provenance array fails closed to the untrusted fallback
      // content (existing malformed-segments behavior).
      await waitFor(() => {
        expect(el.textContent).toContain("fallback content")
      })
      expect(el.querySelector(".shiny-web-activity")).toBeNull()
      expect(warn).toHaveBeenCalled()
    } finally {
      warn.mockRestore()
    }
  })

  it("renders initial segments carrying block entries", async () => {
    const el = document.createElement("shiny-markdown-stream")
    el.setAttribute(
      "content-segments",
      JSON.stringify([
        { text: "## Markdown", trusted: false },
        {
          block: {
            type: "html_block",
            version: 1,
            content: "<div data-island>HTML</div>",
          },
        },
      ]),
    )

    await act(async () => {
      document.body.appendChild(el)
    })

    await waitFor(() => {
      expect(el.querySelector("h2")?.textContent).toBe("Markdown")
      expect(el.querySelector("[data-island]")?.textContent).toBe("HTML")
    })
  })

  it("fails closed when an initial block entry is malformed", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    try {
      const el = document.createElement("shiny-markdown-stream")
      el.setAttribute(
        "content",
        "<shiny-chat-raw-html><div data-forged>unsafe</div></shiny-chat-raw-html>",
      )
      el.setAttribute(
        "content-segments",
        JSON.stringify([
          { text: "fine", trusted: false },
          {
            block: {
              type: "html_block",
              version: 99,
              content: "<div data-forged>unsafe</div>",
            },
          },
        ]),
      )

      await act(async () => {
        document.body.appendChild(el)
      })

      // The whole provenance array fails closed to the untrusted fallback
      // content (existing malformed-segments behavior).
      await waitFor(() => {
        expect(el.textContent).toContain("<shiny-chat-raw-html>")
      })
      expect(el.querySelector("[data-forged]")).toBeNull()
    } finally {
      warn.mockRestore()
    }
  })
})
