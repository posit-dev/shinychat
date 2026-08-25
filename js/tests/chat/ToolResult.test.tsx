import { describe, it, expect, vi } from "vitest"
import { render, fireEvent } from "@testing-library/react"
import { ToolResult } from "../../src/chat/ToolResult"
import { ChatScrollContext } from "../../src/chat/context"

describe("ToolResult", () => {
  it("disengages the outer chat's stick-to-bottom before toggling the long tool-call preview", () => {
    // The "Tool call" argument preview collapses into a native <details> when
    // long. Opening it resizes the chat message list exactly like the card
    // itself, so it needs the same guard against the outer auto-scroll.
    const stopScroll = vi.fn()
    const requestCall = "line 1\nline 2\nline 3"
    const { container } = render(
      <ChatScrollContext.Provider value={stopScroll}>
        <ToolResult
          toolName="my_tool"
          status="success"
          value="result"
          valueType="text"
          requestCall={requestCall}
          showRequest={true}
        />
      </ChatScrollContext.Provider>,
    )
    const details = container.querySelector("details") as HTMLDetailsElement
    expect(details).toBeTruthy()
    fireEvent(details, new Event("toggle", { bubbles: false }))
    expect(stopScroll).toHaveBeenCalled()
  })
})
