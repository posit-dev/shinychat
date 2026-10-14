import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, act } from "@testing-library/react"
import { ChatGreeting } from "../../src/chat/ChatGreeting"
import {
  ChatDispatchContext,
  ShinyLifecycleContext,
} from "../../src/chat/context"
import type { GreetingData } from "../../src/chat/state"
import type { AnyAction } from "../../src/chat/state"
import type { ShinyLifecycle } from "../../src/transport/types"

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

  it("renders greeting content text", () => {
    const { container } = renderWithDispatch(
      <ChatGreeting
        greeting={makeGreeting({
          content: "Welcome!",
          blocks: [
            { type: "content", content: "Welcome!", contentType: "markdown" },
          ],
        })}
      />,
    )
    const content = container.querySelector(".shiny-chat-greeting-content")
    expect(content).not.toBeNull()
    expect(content?.textContent).toContain("Welcome!")
  })

  it("binds Shiny UI in html-typed greeting content, scoped to the greeting", () => {
    const shiny: ShinyLifecycle = {
      bindAll: vi.fn(async () => {}),
      unbindAll: vi.fn(),
      renderDependencies: vi.fn(async () => {}),
      showClientMessage: vi.fn(),
    }
    const html =
      '<div class="shiny-plot-output" id="greeting-plot" style="width:100%;height:200px"></div>'

    const { container, unmount } = render(
      <ChatDispatchContext.Provider value={() => {}}>
        <ShinyLifecycleContext.Provider value={shiny}>
          <ChatGreeting
            greeting={makeGreeting({
              content: html,
              contentType: "html",
              blocks: [{ type: "content", content: html, contentType: "html" }],
            })}
          />
        </ShinyLifecycleContext.Provider>
      </ChatDispatchContext.Provider>,
    )

    const output = container.querySelector("#greeting-plot")
    expect(output).not.toBeNull()
    expect(shiny.bindAll).toHaveBeenCalledOnce()
    const bindScope = vi.mocked(shiny.bindAll).mock.calls[0]![0] as HTMLElement
    expect(bindScope.contains(output)).toBe(true)
    const content = container.querySelector(".shiny-chat-greeting-content")
    expect(content?.contains(bindScope)).toBe(true)

    unmount()
    expect(shiny.unbindAll).toHaveBeenCalledOnce()
    const unbindScope = vi.mocked(shiny.unbindAll).mock
      .calls[0]![0] as HTMLElement
    expect(unbindScope).toBe(bindScope)
  })

  it("resolves react carriers in html-typed greeting content (shiny-aside → AsideGroup)", () => {
    const html =
      '<p>Welcome!</p><shiny-aside label="Docs" url="https://example.com">Extra info</shiny-aside>'

    const { container } = renderWithDispatch(
      <ChatGreeting
        greeting={makeGreeting({
          content: html,
          contentType: "html",
          blocks: [{ type: "content", content: html, contentType: "html" }],
        })}
      />,
    )

    const pill = container.querySelector(".shiny-aside-pill")
    expect(pill).not.toBeNull()
    expect(pill?.textContent).toContain("Docs")
    expect(container.querySelector("shiny-aside")).toBeNull()
    expect(container.querySelector("shiny-aside-group")).toBeNull()
    expect(container.textContent).toContain("Welcome!")
  })

  it("rebinds when html greeting content is replaced while visible", () => {
    const shiny: ShinyLifecycle = {
      bindAll: vi.fn(async () => {}),
      unbindAll: vi.fn(),
      renderDependencies: vi.fn(async () => {}),
      showClientMessage: vi.fn(),
    }
    const firstHtml =
      '<div class="shiny-plot-output" id="plot-a" style="width:100%;height:200px"></div>'
    const secondHtml =
      '<div class="shiny-plot-output" id="plot-b" style="width:100%;height:200px"></div>'

    const { container, rerender } = render(
      <ChatDispatchContext.Provider value={() => {}}>
        <ShinyLifecycleContext.Provider value={shiny}>
          <ChatGreeting
            greeting={makeGreeting({
              content: firstHtml,
              contentType: "html",
              blocks: [
                { type: "content", content: firstHtml, contentType: "html" },
              ],
            })}
          />
        </ShinyLifecycleContext.Provider>
      </ChatDispatchContext.Provider>,
    )
    expect(container.querySelector("#plot-a")).not.toBeNull()
    expect(shiny.bindAll).toHaveBeenCalledOnce()

    rerender(
      <ChatDispatchContext.Provider value={() => {}}>
        <ShinyLifecycleContext.Provider value={shiny}>
          <ChatGreeting
            greeting={makeGreeting({
              content: secondHtml,
              contentType: "html",
              blocks: [
                { type: "content", content: secondHtml, contentType: "html" },
              ],
            })}
          />
        </ShinyLifecycleContext.Provider>
      </ChatDispatchContext.Provider>,
    )

    expect(container.querySelector("#plot-b")).not.toBeNull()
    expect(shiny.unbindAll).toHaveBeenCalledOnce()
    expect(shiny.bindAll).toHaveBeenCalledTimes(2)
    const rebindingScope = vi.mocked(shiny.bindAll).mock
      .calls[1]![0] as HTMLElement
    expect(rebindingScope.contains(container.querySelector("#plot-b"))).toBe(
      true,
    )
  })

  it("does not bind markdown-typed greeting content", () => {
    const shiny: ShinyLifecycle = {
      bindAll: vi.fn(async () => {}),
      unbindAll: vi.fn(),
      renderDependencies: vi.fn(async () => {}),
      showClientMessage: vi.fn(),
    }

    const { unmount } = render(
      <ChatDispatchContext.Provider value={() => {}}>
        <ShinyLifecycleContext.Provider value={shiny}>
          <ChatGreeting greeting={makeGreeting()} />
        </ShinyLifecycleContext.Provider>
      </ChatDispatchContext.Provider>,
    )

    expect(shiny.bindAll).not.toHaveBeenCalled()
    unmount()
    expect(shiny.unbindAll).not.toHaveBeenCalled()
  })

  it("renders nothing when blocks are empty", () => {
    const { container } = renderWithDispatch(
      <ChatGreeting greeting={makeGreeting({ blocks: [] })} />,
    )
    const content = container.querySelector(".shiny-chat-greeting-content")
    expect(content).not.toBeNull()
    expect(content?.children.length).toBe(0)
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
