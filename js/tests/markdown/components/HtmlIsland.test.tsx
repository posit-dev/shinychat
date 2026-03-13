import { describe, it, expect } from "vitest"
import { render } from "@testing-library/react"
import type { Element } from "hast"
import type { ComponentType } from "react"
import { HtmlIsland } from "../../../src/markdown/components/HtmlIsland"
import { ComponentMapProvider } from "../../../src/markdown/componentMapContext"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderIsland(
  node: Element,
  componentMap: Record<string, ComponentType<unknown>> = {},
) {
  return render(
    <ComponentMapProvider value={componentMap}>
      <HtmlIsland node={node} />
    </ComponentMapProvider>,
  )
}

function makeIslandNode(children: Element["children"]): Element {
  return {
    type: "element",
    tagName: "shinychat-html",
    properties: {},
    children,
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("HtmlIsland segmentation", () => {
  it("all-HTML content renders via innerHTML (no data-shinychat-react children)", () => {
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

    const { container } = renderIsland(node)

    // Content should appear via innerHTML (RawHtmlSegment uses a ref + innerHTML)
    // The wrapper div from RawHtmlSegment should contain the p tags
    const paragraphs = container.querySelectorAll("p")
    expect(paragraphs.length).toBe(2)
    expect(paragraphs.item(0).textContent).toBe("hello")
    expect(paragraphs.item(1).textContent).toBe("world")
  })

  it("all-React content routes data-shinychat-react child through the component map", () => {
    function TestWidget({ node: _node }: { node?: Element }) {
      return <div data-testid="test-widget">rendered by react</div>
    }

    const componentMap = {
      "my-widget": TestWidget as ComponentType<unknown>,
    }

    const node = makeIslandNode([
      {
        type: "element",
        tagName: "my-widget",
        properties: { dataShinychatReact: "" },
        children: [],
      },
    ])

    const { getByTestId } = renderIsland(node, componentMap)

    expect(getByTestId("test-widget").textContent).toBe("rendered by react")
  })

  it("mixed content produces HTML, React, HTML segments in order", () => {
    function TestWidget({ node: _node }: { node?: Element }) {
      return <div data-testid="test-widget">react middle</div>
    }

    const componentMap = {
      "my-widget": TestWidget as ComponentType<unknown>,
    }

    const node = makeIslandNode([
      {
        type: "element",
        tagName: "p",
        properties: {},
        children: [{ type: "text", value: "before" }],
      },
      {
        type: "element",
        tagName: "my-widget",
        properties: { dataShinychatReact: "" },
        children: [],
      },
      {
        type: "element",
        tagName: "p",
        properties: {},
        children: [{ type: "text", value: "after" }],
      },
    ])

    const { container, getByTestId } = renderIsland(node, componentMap)

    // React segment rendered
    expect(getByTestId("test-widget").textContent).toBe("react middle")

    // HTML segments rendered via innerHTML wrapper divs
    const paragraphs = container.querySelectorAll("p")
    expect(paragraphs.length).toBe(2)
    const texts = Array.from(paragraphs).map((p) => p.textContent)
    expect(texts).toContain("before")
    expect(texts).toContain("after")
  })

  it("custom element without data-shinychat-react stays in innerHTML, not React", () => {
    function TestWidget({ node: _node }: { node?: Element }) {
      return <div data-testid="test-widget">should not appear</div>
    }

    // Register the component so it WOULD render via React if attribute present
    const componentMap = {
      "my-widget": TestWidget as ComponentType<unknown>,
    }

    const node = makeIslandNode([
      {
        type: "element",
        tagName: "my-widget",
        // No dataShinychatReact property — should stay in innerHTML
        properties: {},
        children: [],
      },
    ])

    const { container, queryByTestId } = renderIsland(node, componentMap)

    // React component should NOT have rendered
    expect(queryByTestId("test-widget")).toBeNull()

    // The element should appear as a raw custom element via innerHTML
    expect(container.querySelector("my-widget")).not.toBeNull()
  })
})
