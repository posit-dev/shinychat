import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, act } from "@testing-library/react"
import { ChatGreeting } from "../../src/chat/ChatGreeting"
import { ChatDispatchContext } from "../../src/chat/context"
import type { GreetingData } from "../../src/chat/state"
import type { AnyAction } from "../../src/chat/state"

function renderWithDispatch(
  element: React.ReactElement,
  dispatch: (a: AnyAction) => void = () => {},
) {
  return render(
    <ChatDispatchContext.Provider value={dispatch}>
      {element}
    </ChatDispatchContext.Provider>,
  )
}

function makeGreeting(overrides: Partial<GreetingData> = {}): GreetingData {
  return {
    content: "Hello!",
    contentType: "markdown",
    streaming: false,
    status: "visible",
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
  it("renders content when status:visible", () => {
    const { container } = renderWithDispatch(
      <ChatGreeting greeting={makeGreeting()} />,
    )
    expect(container.querySelector(".shiny-chat-greeting")).not.toBeNull()
  })

  it("renders nothing when status:dismissed", () => {
    const { container } = renderWithDispatch(
      <ChatGreeting greeting={makeGreeting({ status: "dismissed" })} />,
    )
    expect(container.querySelector(".shiny-chat-greeting")).toBeNull()
  })

  it("renders with data-dismissing when status:dismissing", () => {
    const { container } = renderWithDispatch(
      <ChatGreeting greeting={makeGreeting({ status: "dismissing" })} />,
    )
    const el = container.querySelector(".shiny-chat-greeting")
    expect(el).not.toBeNull()
    expect(el?.hasAttribute("data-dismissing")).toBe(true)
  })

  it("dispatches greeting_dismissed immediately when prefers-reduced-motion is set", () => {
    mockMatchMedia(true)
    const dispatch = vi.fn()

    renderWithDispatch(
      <ChatGreeting greeting={makeGreeting({ status: "dismissing" })} />,
      dispatch,
    )

    expect(dispatch).toHaveBeenCalledWith({ type: "greeting_dismissed" })
  })

  it("dispatches greeting_dismissed on animationend", () => {
    const dispatch = vi.fn()
    const { container } = renderWithDispatch(
      <ChatGreeting greeting={makeGreeting({ status: "dismissing" })} />,
      dispatch,
    )
    const el = container.querySelector(".shiny-chat-greeting") as HTMLElement
    act(() => {
      const event = new Event("animationend")
      Object.defineProperty(event, "animationName", {
        value: "shiny-chat-greeting-dismiss",
      })
      el.dispatchEvent(event)
    })
    expect(dispatch).toHaveBeenCalledWith({ type: "greeting_dismissed" })
  })
})
