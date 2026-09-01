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

type ElementInternals = {
  api: ReturnType<typeof createMockApi> | null
  pendingMessages: (ContentMessage | IsStreamingMessage)[]
  dispatchMessage: (msg: ContentMessage | IsStreamingMessage) => void
  onApiReadyCallback: ((api: ReturnType<typeof createMockApi>) => void) | null
}

function internals(el: HTMLElement): ElementInternals {
  return el as unknown as ElementInternals
}

beforeAll(async () => {
  ;(window as unknown as Record<string, unknown>).Shiny = {
    addCustomMessageHandler: vi.fn(),
  }

  await import("../../src/markdown-stream/markdown-stream-entry")
})

beforeEach(() => {
  ;(window as unknown as Record<string, unknown>).Shiny = {
    addCustomMessageHandler: vi.fn(),
  }
})

afterEach(() => {
  document.body.innerHTML = ""
})

function createElement_(): {
  el: HTMLElement
  simulateApiReady: (api: ReturnType<typeof createMockApi>) => void
} {
  const el = document.createElement("shiny-markdown-stream") as HTMLElement &
    ElementInternals

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

describe("MarkdownStreamElement — pending message queue", () => {
  it("renders structured initial trust segments", async () => {
    const el = document.createElement("shiny-markdown-stream")
    el.setAttribute(
      "content-segments",
      JSON.stringify([
        { text: "## Markdown", trusted: false },
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
    await act(async () => {
      document.body.appendChild(el)
    })

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

    const handle = el as unknown as {
      handleMessage: (m: ContentMessage | IsStreamingMessage) => void
    }
    handle.handleMessage(msg1)
    handle.handleMessage(msg2)
    handle.handleMessage(msg3)

    expect(internals(el).pendingMessages).toHaveLength(3)
    expect(api.appendContent).not.toHaveBeenCalled()

    simulateApiReady(api)

    expect(internals(el).pendingMessages).toHaveLength(0)
    expect(api.appendContent).toHaveBeenNthCalledWith(1, "hello", false, false)
    expect(api.appendContent).toHaveBeenNthCalledWith(2, " world", false, false)
    expect(api.setStreaming).toHaveBeenCalledWith(false)
  })

  it("dispatches messages immediately when api is already set", () => {
    const { el, simulateApiReady } = createElement_()
    const api = createMockApi()

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

    await waitFor(() => {
      expect(el.textContent).toContain("initial")
    })

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

    await act(async () => {
      right.appendChild(el)
    })

    await waitFor(() => {
      expect(el.textContent).toContain("initial")
    })

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

    await act(async () => {
      handle.disconnectedCallback()
      await new Promise((resolve) => setTimeout(resolve, 0))
    })

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
          { block: { type: "web_search_results", version: 1 } },
        ]),
      )

      await act(async () => {
        document.body.appendChild(el)
      })

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

      await waitFor(() => {
        expect(el.textContent).toContain("<shiny-chat-raw-html>")
      })
      expect(el.querySelector("[data-forged]")).toBeNull()
    } finally {
      warn.mockRestore()
    }
  })
})
