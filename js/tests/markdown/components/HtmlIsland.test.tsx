import { describe, it, expect } from "vitest"
import { render } from "@testing-library/react"
import type { Element } from "hast"
import { HtmlIsland } from "../../../src/markdown/components/HtmlIsland"

function makeIslandNode(children: Element["children"]): Element {
  return {
    type: "element",
    tagName: "shinychat-html",
    properties: {},
    children,
  }
}

describe("HtmlIsland", () => {
  it("renders HTML content via innerHTML", () => {
    const node = makeIslandNode([
      {
        type: "element",
        tagName: "p",
        properties: {},
        children: [{ type: "text", value: "hello" }],
      },
      {
        type: "element",
        tagName: "p",
        properties: {},
        children: [{ type: "text", value: "world" }],
      },
    ])

    const { container } = render(<HtmlIsland node={node} />)

    const paragraphs = container.querySelectorAll("p")
    expect(paragraphs.length).toBe(2)
    expect(paragraphs.item(0).textContent).toBe("hello")
    expect(paragraphs.item(1).textContent).toBe("world")
  })

  it("renders nothing when node is undefined", () => {
    const { container } = render(<HtmlIsland />)
    expect(container.textContent).toBe("")
  })

  it("renders nothing when node has no children", () => {
    const node = makeIslandNode([])
    const { container } = render(<HtmlIsland node={node} />)
    expect(container.textContent).toBe("")
  })

  it("always uses display:contents", () => {
    const node = makeIslandNode([{ type: "text", value: "hello" }])
    const { container } = render(<HtmlIsland node={node} />)
    const div = container.firstElementChild as HTMLElement
    expect(div.style.display).toBe("contents")
  })

  it("adds fill carrier classes when parent is a fill container", () => {
    const node = makeIslandNode([{ type: "text", value: "hello" }])
    const { container } = render(
      <div className="html-fill-container">
        <HtmlIsland node={node} />
      </div>,
    )
    const island = container.querySelector(
      ".html-fill-item.html-fill-container",
    )
    expect(island).not.toBeNull()
    expect((island as HTMLElement).style.display).toBe("contents")
  })

  it("does not add fill carrier classes when parent is not a fill container", () => {
    const node = makeIslandNode([{ type: "text", value: "hello" }])
    const { container } = render(
      <div>
        <HtmlIsland node={node} />
      </div>,
    )
    const div = container.querySelector("div > div") as HTMLElement
    expect(div.classList.contains("html-fill-item")).toBe(false)
    expect(div.classList.contains("html-fill-container")).toBe(false)
  })
})
