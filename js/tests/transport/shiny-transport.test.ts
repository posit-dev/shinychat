import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { ShinyTransport } from "../../src/transport/shiny-transport"
import {
  isValidEnvelope,
  type ChatAction,
  type ShinyChatEnvelope,
} from "../../src/transport/types"
import { installShinyWindowStub } from "../helpers/mocks"

function makeEnvelope(
  action: ChatAction,
  overrides: Partial<ShinyChatEnvelope> = {},
): ShinyChatEnvelope {
  return { id: "chat1", action, ...overrides }
}

// ---------------------------------------------------------------------------
// isValidEnvelope unit tests
// ---------------------------------------------------------------------------

describe("isValidEnvelope", () => {
  it("accepts a well-formed envelope", () => {
    expect(isValidEnvelope({ id: "chat1", action: { type: "clear" } })).toBe(
      true,
    )
  })

  it("rejects null", () => {
    expect(isValidEnvelope(null)).toBe(false)
  })

  it("rejects missing id", () => {
    expect(isValidEnvelope({ action: { type: "clear" } })).toBe(false)
  })

  it("rejects non-string id", () => {
    expect(isValidEnvelope({ id: 123, action: { type: "clear" } })).toBe(false)
  })

  it("rejects missing action", () => {
    expect(isValidEnvelope({ id: "chat1" })).toBe(false)
  })

  it("rejects action without type", () => {
    expect(isValidEnvelope({ id: "chat1", action: { content: "x" } })).toBe(
      false,
    )
  })

  it("rejects non-string action.type", () => {
    expect(isValidEnvelope({ id: "chat1", action: { type: 42 } })).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// ShinyTransport integration tests
// ---------------------------------------------------------------------------

describe("ShinyTransport", () => {
  // Capture handlers registered via addCustomMessageHandler
  let handlers: Record<string, (payload: unknown) => void | Promise<void>>

  beforeEach(() => {
    installShinyWindowStub()
    handlers = {}
    ;(
      window.Shiny!.addCustomMessageHandler as ReturnType<typeof vi.fn>
    ).mockImplementation(
      (name: string, handler: (payload: unknown) => void) => {
        handlers[name] = handler
      },
    )
  })

  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).__shinyChatTransport
  })

  function fire(envelope: ShinyChatEnvelope): Promise<void> {
    return Promise.resolve(handlers["shinyChatMessage"]!(envelope))
  }

  // -------------------------------------------------------------------------
  // Pending-message queue
  // -------------------------------------------------------------------------

  describe("pending-message queue", () => {
    it("queues messages that arrive before a listener and flushes on registration", async () => {
      const transport = new ShinyTransport()
      const envelope = makeEnvelope({
        type: "message",
        message: {
          role: "assistant",
          content: "queued",
          content_type: "markdown",
        },
      })
      await fire(envelope)

      const received: unknown[] = []
      transport.onMessage("chat1", (action) => received.push(action))

      expect(received).toHaveLength(1)
      expect(received[0]).toMatchObject({ type: "message" })
    })

    it("delivers messages immediately when a listener is already registered", async () => {
      const transport = new ShinyTransport()
      const received: unknown[] = []
      transport.onMessage("chat1", (action) => received.push(action))

      const envelope = makeEnvelope({
        type: "message",
        message: {
          role: "assistant",
          content: "live",
          content_type: "markdown",
        },
      })
      await fire(envelope)

      expect(received).toHaveLength(1)
      expect(received[0]).toMatchObject({ type: "message" })
    })

    it("flushes queued messages to a replacement listener after unsubscribe", async () => {
      const transport = new ShinyTransport()

      // Register then immediately unsubscribe
      const unsub = transport.onMessage("chat1", () => {})
      unsub()

      // Fire a message — no active listener, so it goes to pending
      const envelope = makeEnvelope({
        type: "message",
        message: {
          role: "assistant",
          content: "stale",
          content_type: "markdown",
        },
      })
      await fire(envelope)

      // Register a new listener — should receive the queued message
      const received: unknown[] = []
      transport.onMessage("chat1", (action) => received.push(action))
      expect(received).toHaveLength(1)
      expect(received[0]).toMatchObject({ type: "message" })
    })
  })

  // -------------------------------------------------------------------------
  // Listener lifecycle
  // -------------------------------------------------------------------------

  describe("listener lifecycle", () => {
    it("routes messages to the correct listener by ID", async () => {
      const transport = new ShinyTransport()
      const receivedA: unknown[] = []
      const receivedB: unknown[] = []

      transport.onMessage("chatA", (a) => receivedA.push(a))
      transport.onMessage("chatB", (a) => receivedB.push(a))

      await fire({ id: "chatA", action: { type: "clear" } })

      expect(receivedA).toHaveLength(1)
      expect(receivedA[0]).toEqual({ type: "clear" })
      expect(receivedB).toHaveLength(0)
    })

    it("stops delivering messages after unsubscribe", async () => {
      const transport = new ShinyTransport()
      const received: unknown[] = []
      const unsub = transport.onMessage("chat1", (a) => received.push(a))

      unsub()

      await fire({ id: "chat1", action: { type: "clear" } })

      // Message went to pending (no active listeners); received stays empty
      expect(received).toHaveLength(0)
    })
  })

  describe("envelope validation", () => {
    // Helper that accepts unknown to test malformed envelopes
    function fireRaw(payload: unknown): Promise<void> {
      return Promise.resolve(handlers["shinyChatMessage"]!(payload))
    }

    it("drops envelope with missing id and logs warning", async () => {
      const transport = new ShinyTransport()
      const received: unknown[] = []
      transport.onMessage("chat1", (a) => received.push(a))

      const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {})
      await fireRaw({ action: { type: "clear" } })

      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining("shinychat"),
        expect.anything(),
      )
      expect(received).toHaveLength(0)
      warnSpy.mockRestore()
    })

    it("drops envelope with missing action and logs warning", async () => {
      const transport = new ShinyTransport()
      const received: unknown[] = []
      transport.onMessage("chat1", (a) => received.push(a))

      const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {})
      await fireRaw({ id: "chat1" })

      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining("shinychat"),
        expect.anything(),
      )
      expect(received).toHaveLength(0)
      warnSpy.mockRestore()
    })

    it("drops envelope where action has no type and logs warning", async () => {
      const transport = new ShinyTransport()
      const received: unknown[] = []
      transport.onMessage("chat1", (a) => received.push(a))

      const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {})
      await fireRaw({ id: "chat1", action: { content: "hello" } })

      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining("shinychat"),
        expect.anything(),
      )
      expect(received).toHaveLength(0)
      warnSpy.mockRestore()
    })

    it("drops null envelope and logs warning", async () => {
      const transport = new ShinyTransport()
      const received: unknown[] = []
      transport.onMessage("chat1", (a) => received.push(a))

      const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {})
      await fireRaw(null)

      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining("shinychat"),
        expect.anything(),
      )
      expect(received).toHaveLength(0)
      warnSpy.mockRestore()
    })
  })

  describe("custom message handler contracts", () => {
    it("renders html dependencies before delivering a message action", async () => {
      const transport = new ShinyTransport()
      const received: unknown[] = []
      const order: string[] = []

      ;(
        window.Shiny!.renderDependenciesAsync as ReturnType<typeof vi.fn>
      ).mockImplementation(async () => {
        order.push("deps")
      })

      transport.onMessage("chat1", (action) => {
        order.push("listener")
        received.push(action)
      })

      await fire(
        makeEnvelope(
          {
            type: "message",
            message: {
              role: "assistant",
              content: "with deps",
              content_type: "markdown",
            },
          },
          { html_deps: [{ name: "x", version: "1.0.0", src: { href: "/" } }] },
        ),
      )

      expect(window.Shiny?.renderDependenciesAsync).toHaveBeenCalled()
      expect(received).toHaveLength(1)
      expect(order).toEqual(["deps", "listener"])
    })

    it("routes tool-request-hide to the correct listener by ID", async () => {
      const transport = new ShinyTransport()
      const receivedA: unknown[] = []
      const receivedB: unknown[] = []

      transport.onMessage("chatA", (action) => receivedA.push(action))
      transport.onMessage("chatB", (action) => receivedB.push(action))

      await fire({
        id: "chatA",
        action: { type: "hide_tool_request", requestId: "req-42" },
      })

      expect(receivedA).toEqual([
        { type: "hide_tool_request", requestId: "req-42" },
      ])
      expect(receivedB).toHaveLength(0)
    })
  })
})
