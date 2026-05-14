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

  it("sets data-dismissing attribute when visible transitions to false (animation mode)", () => {
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

    const el = container.querySelector(".shiny-chat-greeting")
    expect(el).not.toBeNull()
    expect(el?.hasAttribute("data-dismissing")).toBe(true)
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
