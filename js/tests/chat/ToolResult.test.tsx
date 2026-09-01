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

  it("renders the request call in the expanded card", () => {
    const { container } = render(
      <ToolResult
        toolName="my_tool"
        status="success"
        value="done"
        valueType="text"
        requestCall={"my_tool(x = 1)"}
        showRequest={true}
        expanded={true}
      />,
    )
    expect(container.textContent).toContain("my_tool(x = 1)")
  })

  // Regression: a server once sent request_call as an array of wrapped lines;
  // requestCall.split() threw and the per-message boundary wiped the whole
  // chat message. The card body boundary must contain it instead.
  it("a malformed requestCall degrades the card body, not the card", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {})
    vi.spyOn(console, "error").mockImplementation(() => {})

    const { container, getByRole } = render(
      <ToolResult
        toolName="my_tool"
        status="success"
        value="done"
        valueType="text"
        requestCall={["my_tool(", "  x = 1)"] as unknown as string}
        showRequest={true}
        expanded={true}
      />,
    )

    const header = container.querySelector(".card-header")
    expect(header).toBeTruthy()
    expect(header!.textContent).toContain("my_tool")
    expect(getByRole("alert").textContent).toContain("couldn’t be displayed")
  })

  it("recovers when a malformed requestCall is corrected with an unchanged value", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {})
    vi.spyOn(console, "error").mockImplementation(() => {})

    const props = {
      toolName: "my_tool",
      status: "success",
      value: "done",
      valueType: "text",
      showRequest: true,
      expanded: true,
    }
    const { rerender, getByRole, queryByRole, container } = render(
      <ToolResult
        {...props}
        requestCall={["my_tool(", "  x = 1)"] as unknown as string}
      />,
    )
    expect(getByRole("alert")).toBeTruthy()

    // Same result value, corrected request call: the body must retry.
    rerender(<ToolResult {...props} requestCall={"my_tool(x = 1)"} />)
    expect(queryByRole("alert")).toBeNull()
    expect(container.textContent).toContain("my_tool(x = 1)")
  })
})
