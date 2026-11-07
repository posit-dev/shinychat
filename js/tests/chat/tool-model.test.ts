import { describe, expect, it } from "vitest"
import { toolResultBlockToCall } from "../../src/chat/tool-model"
import type { ToolResultBlock } from "../../src/transport/types"

function block(partial: Partial<ToolResultBlock> = {}): ToolResultBlock {
  return {
    type: "tool_result",
    version: 1,
    request_id: "request-1",
    tool_name: "weather",
    status: "success",
    ...partial,
  }
}

const imageItems = JSON.stringify([
  { type: "image", src: "data:image/png;base64,aGk=" },
])

describe("toolResultBlockToCall content-type open policy", () => {
  it("opens image results and collapses their request and details", () => {
    const call = toolResultBlockToCall(
      block({ value: imageItems, value_type: "content_extra" }),
    )
    expect(call.expanded).toBe(true)
    expect(call.requestCollapsed).toBe(true)
    expect(call.detailsOpen).toBe(false)
  })

  it("detects images in html and markdown values", () => {
    const cases: Array<[ToolResultBlock["value_type"], string]> = [
      ["html", '<div><img src="x.png"></div>'],
      ["markdown", "a plot:\n\n![plot](x.png)"],
      ["markdown", '<img src="x.png">'],
    ]
    for (const [value_type, value] of cases) {
      const call = toolResultBlockToCall(block({ value, value_type }))
      expect(call.expanded).toBe(true)
    }
  })

  it("keeps PDF results collapsed: images auto-open, PDFs don't", () => {
    const pdfItems = JSON.stringify([
      { type: "pdf", src: "data:application/pdf;base64,aGk=" },
    ])
    const call = toolResultBlockToCall(
      block({ value: pdfItems, value_type: "content_extra" }),
    )
    expect(call.expanded).toBe(false)
  })

  it("keeps text results collapsed with the details slot open", () => {
    const call = toolResultBlockToCall(
      block({ value: "42", value_type: "text" }),
    )
    expect(call.expanded).toBe(false)
    expect(call.requestCollapsed).toBe(false)
    expect(call.detailsOpen).toBe(true)
  })

  it("lets explicit settings win over the policy", () => {
    const call = toolResultBlockToCall(
      block({
        value: imageItems,
        value_type: "content_extra",
        expanded: false,
        details_open: true,
      }),
    )
    expect(call.expanded).toBe(false)
    expect(call.detailsOpen).toBe(true)
  })

  it("treats malformed content_extra JSON as text", () => {
    const call = toolResultBlockToCall(
      block({ value: "not json", value_type: "content_extra" }),
    )
    expect(call.expanded).toBe(false)
  })
})
