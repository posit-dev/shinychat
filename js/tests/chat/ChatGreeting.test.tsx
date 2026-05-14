import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, act } from "@testing-library/react"
import { ChatGreeting } from "../../src/chat/ChatGreeting"
import type { GreetingData } from "../../src/chat/state"

function makeGreeting(overrides: Partial<GreetingData> = {}): GreetingData {
  return {
    content: "Hello!",
    contentType: "markdown",
    streaming: false,
    visible: true,
    dismissed: false,
    options: {},
    blocks: [{ type: "content", content: "Hello!", contentType: "markdown" }],
    ...overrides,
  }
}

function mockMatchMedia(reducedMotion: boolean) {
  const mql = {
    matches: reducedMotion,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue(mql))
  return mql
}

beforeEach(() => {
  mockMatchMedia(false)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("ChatGreeting", () => {
  it("renders content when visible:true", () => {
    const { container } = render(<ChatGreeting greeting={makeGreeting()} />)
    expect(container.querySelector(".shiny-chat-greeting")).not.toBeNull()
  })

  it("renders nothing when visible:false and not dismissing", () => {
    const { container } = render(
      <ChatGreeting
        greeting={makeGreeting({ visible: false, dismissed: true })}
      />,
    )
    expect(container.querySelector(".shiny-chat-greeting")).toBeNull()
  })

  it("keeps greeting in DOM during pre-dismiss delay, then flips data-dismissing", () => {
    vi.useFakeTimers()
    try {
      const { container, rerender } = render(
        <ChatGreeting greeting={makeGreeting({ visible: true })} />,
      )

      act(() => {
        rerender(
          <ChatGreeting
            greeting={makeGreeting({ visible: false, dismissed: true })}
          />,
        )
      })

      const pre = container.querySelector(".shiny-chat-greeting")
      expect(pre).not.toBeNull()
      expect(pre?.hasAttribute("data-dismissing")).toBe(false)

      act(() => {
        vi.advanceTimersByTime(500)
      })

      const post = container.querySelector(".shiny-chat-greeting")
      expect(post).not.toBeNull()
      expect(post?.hasAttribute("data-dismissing")).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })

  it("removes immediately (no data-dismissing) when prefers-reduced-motion is set", () => {
    mockMatchMedia(true)

    const { container, rerender } = render(
      <ChatGreeting greeting={makeGreeting({ visible: true })} />,
    )

    act(() => {
      rerender(
        <ChatGreeting
          greeting={makeGreeting({ visible: false, dismissed: true })}
        />,
      )
    })

    expect(container.querySelector(".shiny-chat-greeting")).toBeNull()
  })
})
