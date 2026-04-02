import { describe, it, expect, vi } from "vitest"
import { render, cleanup } from "@testing-library/react"
import { RawHTML } from "../../src/chat/RawHTML"
import { ShinyLifecycleContext } from "../../src/chat/context"
import type { ShinyLifecycle } from "../../src/transport/types"

function mockShiny(): ShinyLifecycle {
  return {
    bindAll: vi.fn().mockResolvedValue(undefined),
    unbindAll: vi.fn(),
    renderDependencies: vi.fn().mockResolvedValue(undefined),
    showClientMessage: vi.fn(),
  }
}

describe("RawHTML", () => {
  it("renders HTML content via innerHTML", () => {
    const { container } = render(<RawHTML html="<p>hello</p><p>world</p>" />)
    const paragraphs = container.querySelectorAll("p")
    expect(paragraphs.length).toBe(2)
    expect(paragraphs.item(0).textContent).toBe("hello")
    expect(paragraphs.item(1).textContent).toBe("world")
  })

  it("renders empty string without error", () => {
    const { container } = render(<RawHTML html="" />)
    expect(container.textContent).toBe("")
  })

  it("passes className through", () => {
    const { container } = render(
      <RawHTML html="hello" className="card-footer" />,
    )
    const div = container.firstElementChild as HTMLElement
    expect(div.className).toBe("card-footer")
  })

  it("applies display:contents by default", () => {
    const { container } = render(<RawHTML html="hello" />)
    const div = container.firstElementChild as HTMLElement
    expect(div.style.display).toBe("contents")
  })

  it("does not apply display:contents when displayContents is false", () => {
    const { container } = render(
      <RawHTML html="hello" displayContents={false} />,
    )
    const div = container.firstElementChild as HTMLElement
    expect(div.style.display).toBe("")
  })

  it("adds fill carrier classes when parent is a fill container", () => {
    const { container } = render(
      <div className="html-fill-container">
        <RawHTML html="hello" displayContents />
      </div>,
    )
    const island = container.querySelector(
      ".html-fill-item.html-fill-container",
    )
    expect(island).not.toBeNull()
    expect((island as HTMLElement).style.display).toBe("contents")
  })

  it("does not add fill carrier classes when parent is not a fill container", () => {
    const { container } = render(
      <div>
        <RawHTML html="hello" displayContents />
      </div>,
    )
    const div = container.querySelector("div > div") as HTMLElement
    expect(div.classList.contains("html-fill-item")).toBe(false)
    expect(div.classList.contains("html-fill-container")).toBe(false)
  })

  it("does not add fill carrier classes when displayContents is false", () => {
    const { container } = render(
      <div className="html-fill-container">
        <RawHTML html="hello" />
      </div>,
    )
    const div = container.querySelector("div > div") as HTMLElement
    expect(div.classList.contains("html-fill-item")).toBe(false)
  })

  it("combines fill carrier classes with className", () => {
    const { container } = render(
      <div className="html-fill-container">
        <RawHTML html="hello" displayContents className="extra" />
      </div>,
    )
    const div = container.querySelector(
      ".html-fill-item.html-fill-container",
    ) as HTMLElement
    expect(div).not.toBeNull()
    expect(div.classList.contains("extra")).toBe(true)
  })

  it("works without ShinyLifecycleContext (no throw)", () => {
    expect(() => {
      render(<RawHTML html="<p>hello</p>" />)
    }).not.toThrow()
  })

  it("calls bindAll after setting innerHTML when context is provided", () => {
    const shiny = mockShiny()
    const { container } = render(
      <ShinyLifecycleContext.Provider value={shiny}>
        <RawHTML html="<p>hello</p>" />
      </ShinyLifecycleContext.Provider>,
    )
    const div = container.querySelector("div") as HTMLElement
    expect(div.innerHTML).toBe("<p>hello</p>")
    expect(shiny.bindAll).toHaveBeenCalledWith(div)
  })

  it("does not call bindAll when html is empty", () => {
    const shiny = mockShiny()
    render(
      <ShinyLifecycleContext.Provider value={shiny}>
        <RawHTML html="" />
      </ShinyLifecycleContext.Provider>,
    )
    expect(shiny.bindAll).not.toHaveBeenCalled()
  })

  it("calls unbindAll on unmount", () => {
    const shiny = mockShiny()
    const { unmount, container } = render(
      <ShinyLifecycleContext.Provider value={shiny}>
        <RawHTML html="<p>hello</p>" />
      </ShinyLifecycleContext.Provider>,
    )
    const div = container.querySelector("div") as HTMLElement
    unmount()
    expect(shiny.unbindAll).toHaveBeenCalledWith(div)
  })

  it("calls unbindAll then bindAll when html changes", () => {
    const shiny = mockShiny()
    const { rerender, container } = render(
      <ShinyLifecycleContext.Provider value={shiny}>
        <RawHTML html="<p>first</p>" />
      </ShinyLifecycleContext.Provider>,
    )
    const div = container.querySelector("div") as HTMLElement

    // Reset mocks to track only the rerender calls
    vi.mocked(shiny.bindAll).mockClear()
    vi.mocked(shiny.unbindAll).mockClear()

    rerender(
      <ShinyLifecycleContext.Provider value={shiny}>
        <RawHTML html="<p>second</p>" />
      </ShinyLifecycleContext.Provider>,
    )

    expect(shiny.unbindAll).toHaveBeenCalledWith(div)
    expect(shiny.bindAll).toHaveBeenCalledWith(div)
    expect(div.innerHTML).toBe("<p>second</p>")
  })
})
