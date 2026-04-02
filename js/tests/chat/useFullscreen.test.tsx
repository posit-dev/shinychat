import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, act, fireEvent } from "@testing-library/react"
import { useFullscreen } from "../../src/chat/useFullscreen"
import { useRef } from "react"

// Wrapper component that renders the hook's overlay Portal
function TestHarness({
  cardEl,
  onReady,
}: {
  cardEl: HTMLElement
  onReady: (api: ReturnType<typeof useFullscreen>) => void
}) {
  const cardRef = useRef(cardEl)
  const api = useFullscreen(cardRef)
  onReady(api)
  return <>{api.overlay}</>
}

describe("useFullscreen", () => {
  let cardEl: HTMLDivElement

  beforeEach(() => {
    cardEl = document.createElement("div")
    cardEl.className = "shiny-tool-card"
    cardEl.innerHTML =
      '<button class="tool-fullscreen-toggle">Toggle</button><div class="card-body">Content</div>'
    document.body.appendChild(cardEl)
  })

  afterEach(() => {
    // RTL's automatic cleanup unmounts React trees (including portals) first.
    // Only then remove the card element we added manually.
    cardEl.remove()
    vi.restoreAllMocks()
  })

  it("enterFullscreen adds overlay and fullscreen attribute", () => {
    let api: ReturnType<typeof useFullscreen>
    render(<TestHarness cardEl={cardEl} onReady={(a) => (api = a)} />)

    act(() => {
      api!.enterFullscreen(cardEl.querySelector(".tool-fullscreen-toggle")!)
    })

    expect(cardEl.hasAttribute("fullscreen")).toBe(true)
    expect(
      document.querySelector(".shiny-tool-fullscreen-backdrop"),
    ).toBeTruthy()
  })

  it("exitFullscreen removes overlay and fullscreen attribute", () => {
    let api: ReturnType<typeof useFullscreen>
    render(<TestHarness cardEl={cardEl} onReady={(a) => (api = a)} />)

    act(() => {
      api!.enterFullscreen(cardEl.querySelector(".tool-fullscreen-toggle")!)
    })
    act(() => {
      api!.exitFullscreen()
    })

    expect(cardEl.hasAttribute("fullscreen")).toBe(false)
    expect(document.querySelector(".shiny-tool-fullscreen-backdrop")).toBeNull()
  })

  it("Escape key exits fullscreen", () => {
    let api: ReturnType<typeof useFullscreen>
    render(<TestHarness cardEl={cardEl} onReady={(a) => (api = a)} />)

    act(() => {
      api!.enterFullscreen(cardEl.querySelector(".tool-fullscreen-toggle")!)
    })

    act(() => {
      fireEvent.keyDown(document, { key: "Escape" })
    })

    expect(cardEl.hasAttribute("fullscreen")).toBe(false)
    expect(document.querySelector(".shiny-tool-fullscreen-backdrop")).toBeNull()
  })

  it("removes the keydown listener when ref identity changes between enter and exit", () => {
    const addSpy = vi.spyOn(document, "addEventListener")
    const removeSpy = vi.spyOn(document, "removeEventListener")

    let api: ReturnType<typeof useFullscreen>

    // Wrapper that accepts cardRef as a prop so we can change identity
    function RefHarness({
      cardRef,
      onReady,
    }: {
      cardRef: React.RefObject<HTMLElement | null>
      onReady: (a: ReturnType<typeof useFullscreen>) => void
    }) {
      const a = useFullscreen(cardRef)
      onReady(a)
      return <>{a.overlay}</>
    }

    const ref1 = { current: cardEl } as React.RefObject<HTMLElement | null>
    const { rerender } = render(
      <RefHarness cardRef={ref1} onReady={(a) => (api = a)} />,
    )

    act(() => {
      api!.enterFullscreen(cardEl.querySelector(".tool-fullscreen-toggle")!)
    })

    const addCalls = addSpy.mock.calls.filter(
      ([event, , capture]) => event === "keydown" && capture === true,
    )
    expect(addCalls.length).toBe(1)

    // Rerender with new ref object — same element, different identity
    const ref2 = { current: cardEl } as React.RefObject<HTMLElement | null>
    rerender(<RefHarness cardRef={ref2} onReady={(a) => (api = a)} />)

    act(() => {
      api!.exitFullscreen()
    })

    const removeCalls = removeSpy.mock.calls.filter(
      ([event, , capture]) => event === "keydown" && capture === true,
    )
    expect(removeCalls.length).toBeGreaterThanOrEqual(1)
    const addedHandler = addCalls[0]![1]
    for (const call of removeCalls) {
      expect(call[1]).toBe(addedHandler)
    }
  })

  it("cleanup on unmount exits fullscreen", () => {
    let api: ReturnType<typeof useFullscreen>
    const { unmount } = render(
      <TestHarness cardEl={cardEl} onReady={(a) => (api = a)} />,
    )

    act(() => {
      api!.enterFullscreen(cardEl.querySelector(".tool-fullscreen-toggle")!)
    })

    unmount()

    expect(cardEl.hasAttribute("fullscreen")).toBe(false)
    expect(document.querySelector(".shiny-tool-fullscreen-backdrop")).toBeNull()
  })
})
