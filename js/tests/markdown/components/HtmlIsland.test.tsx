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
})
