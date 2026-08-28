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

  it("does not add fill carrier classes when fillable is false", () => {
    const { container } = render(
      <div className="html-fill-container">
        <RawHTML html="hello" className="card-footer" fillable={false} />
      </div>,
    )
    const div = container.querySelector(".card-footer") as HTMLElement
    expect(div).not.toBeNull()
    expect(div.classList.contains("html-fill-item")).toBe(false)
    expect(div.classList.contains("html-fill-container")).toBe(false)
  })

  it("still promotes a boxed island when fillable is left default", () => {
    const { container } = render(
      <div className="html-fill-container">
        <RawHTML html="hello" className="payload" displayContents={false} />
      </div>,
    )
    const div = container.querySelector(".payload") as HTMLElement
    expect(div.classList.contains("html-fill-item")).toBe(true)
    expect(div.classList.contains("html-fill-container")).toBe(true)
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

  it("renders a div by default and a span when as='span'", () => {
    const { container, rerender } = render(<RawHTML html="hello" />)
    expect(container.firstElementChild?.tagName).toBe("DIV")

    rerender(<RawHTML html="hello" as="span" />)
    const el = container.firstElementChild as HTMLElement
    expect(el.tagName).toBe("SPAN")
    expect(el.textContent).toBe("hello")
  })

  it("sets innerHTML but does not bind or unbind when bind is false", () => {
    const shiny = mockShiny()
    const { container, unmount } = render(
      <ShinyLifecycleContext.Provider value={shiny}>
        <RawHTML html="<p>hello</p>" bind={false} />
      </ShinyLifecycleContext.Provider>,
    )
    const div = container.querySelector("div") as HTMLElement
    expect(div.innerHTML).toBe("<p>hello</p>")
    expect(shiny.bindAll).not.toHaveBeenCalled()
    unmount()
    expect(shiny.unbindAll).not.toHaveBeenCalled()
  })

  it("unbinds when bind flips to false and rebinds when it flips back", () => {
    // The tool row/card handoff: while a row is expanded the mounted card owns
    // the bindings, so the row's copy lets them go — and takes them back when
    // it is again the only mounted copy.
    const shiny = mockShiny()
    const { rerender, container } = render(
      <ShinyLifecycleContext.Provider value={shiny}>
        <RawHTML html="<p>hello</p>" bind={true} />
      </ShinyLifecycleContext.Provider>,
    )
    const div = container.querySelector("div") as HTMLElement
    expect(shiny.bindAll).toHaveBeenCalledWith(div)

    rerender(
      <ShinyLifecycleContext.Provider value={shiny}>
        <RawHTML html="<p>hello</p>" bind={false} />
      </ShinyLifecycleContext.Provider>,
    )
    expect(shiny.unbindAll).toHaveBeenCalledWith(div)
    expect(vi.mocked(shiny.bindAll).mock.calls.length).toBe(1)

    rerender(
      <ShinyLifecycleContext.Provider value={shiny}>
        <RawHTML html="<p>hello</p>" bind={true} />
      </ShinyLifecycleContext.Provider>,
    )
    expect(vi.mocked(shiny.bindAll).mock.calls.length).toBe(2)
    expect(vi.mocked(shiny.bindAll).mock.calls[1]![0]).toBe(div)
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
