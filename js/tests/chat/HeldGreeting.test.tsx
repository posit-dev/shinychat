import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { render, screen, act } from "@testing-library/react"
import { ChatApp } from "../../src/chat/ChatApp"
import {
  createMockTransport,
  createMockShinyLifecycle,
  installShinyWindowStub,
} from "../helpers/mocks"

const GREETING = {
  content: "Welcome to the test chat!",
  contentType: "markdown" as const,
  options: {},
}

function renderApp(restorePending: boolean) {
  const transport = createMockTransport()
  render(
    <ChatApp
      transport={transport}
      shinyLifecycle={createMockShinyLifecycle()}
      elementId="test-chat"
      inputId="test-input"
      initialGreeting={GREETING}
      restorePending={restorePending}
    />,
  )
  return transport
}

describe("held greeting during history restore", () => {
  beforeEach(() => {
    installShinyWindowStub()
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({
        matches: true, // reduced motion: skip reveal animation
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it("shows the greeting immediately when no restore is pending", () => {
    renderApp(false)
    expect(screen.queryByText(/Welcome to the test chat/)).not.toBeNull()
  })

  it("withholds the greeting while a restore is pending", () => {
    renderApp(true)
    expect(screen.queryByText(/Welcome to the test chat/)).toBeNull()
  })

  it("reveals the held greeting when history_update reports no restore", () => {
    const transport = renderApp(true)
    act(() => {
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
      })
    })
    expect(screen.queryByText(/Welcome to the test chat/)).not.toBeNull()
  })

  it("drops the held greeting when a conversation was restored", () => {
    const transport = renderApp(true)
    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "user",
          segments: [{ content: "hi", content_type: "text" }],
        },
      })
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [
          { id: "c_1", title: "hi", created_at: "", updated_at: "" },
        ],
        active_id: "c_1",
      })
    })
    expect(screen.queryByText(/Welcome to the test chat/)).toBeNull()
    // The greeting must be gone, not merely still held: a later
    // history_update reporting no restore must NOT bring it back.
    act(() => {
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
      })
    })
    expect(screen.queryByText(/Welcome to the test chat/)).toBeNull()
  })

  it("shows a restoring indicator only after a short delay", () => {
    vi.useFakeTimers()
    renderApp(true)
    expect(screen.queryByText(/Restoring conversation/)).toBeNull()
    act(() => {
      vi.advanceTimersByTime(400)
    })
    expect(screen.queryByText(/Restoring conversation/)).toBeNull()
    act(() => {
      vi.advanceTimersByTime(200)
    })
    expect(screen.queryByText(/Restoring conversation/)).not.toBeNull()
  })

  it("hides the restoring indicator once the restore settles", () => {
    vi.useFakeTimers()
    const transport = renderApp(true)
    act(() => {
      vi.advanceTimersByTime(600)
    })
    expect(screen.queryByText(/Restoring conversation/)).not.toBeNull()
    act(() => {
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
      })
    })
    expect(screen.queryByText(/Restoring conversation/)).toBeNull()
    expect(screen.queryByText(/Welcome to the test chat/)).not.toBeNull()
  })

  it("releases the held greeting after a timeout if no history_update arrives", () => {
    vi.useFakeTimers()
    renderApp(true)
    expect(screen.queryByText(/Welcome to the test chat/)).toBeNull()
    act(() => {
      vi.advanceTimersByTime(16000)
    })
    expect(screen.queryByText(/Welcome to the test chat/)).not.toBeNull()
  })
})
