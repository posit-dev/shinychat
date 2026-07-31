import { describe, it, expect } from "vitest"
import { renderHook } from "@testing-library/react"
import { useSupersededRequests } from "../../src/chat/useSupersededRequests"
import { routeToolBlocks, type ChatMessageData } from "../../src/chat/state"

const request = (id: string) =>
  `<shiny-tool-request data-shinychat-react request-id="${id}" tool-name="search" arguments="{}"></shiny-tool-request>`
const result = (id: string) =>
  `<shiny-tool-result data-shinychat-react request-id="${id}" tool-name="search" status="success" value="ok" value-type="text"></shiny-tool-result>`

function message(content: string): ChatMessageData {
  return {
    id: "m",
    role: "assistant",
    content,
    streaming: false,
    blocks: routeToolBlocks(
      [{ type: "content", content, contentType: "markdown" }],
      "tool",
      "assistant",
    ),
  }
}

describe("useSupersededRequests", () => {
  it("supersedes a paired request", () => {
    const { result: hook } = renderHook(() =>
      useSupersededRequests(
        [message(request("req-1") + result("req-1"))],
        null,
      ),
    )
    expect(hook.current.has("req-1")).toBe(true)
  })

  it("leaves a request alone when its result never arrives", () => {
    const { result: hook } = renderHook(() =>
      useSupersededRequests([message(request("req-1"))], null),
    )
    expect(hook.current.size).toBe(0)
  })

  // The set reaches every message through context, so a fresh identity on each
  // render would re-render the whole transcript per streaming chunk.
  it("keeps the same Set identity while membership is unchanged", () => {
    const messages = [message(request("req-1") + result("req-1"))]
    const { result: hook, rerender } = renderHook(
      ({ msgs }: { msgs: ChatMessageData[] }) =>
        useSupersededRequests(msgs, null),
      { initialProps: { msgs: messages } },
    )
    const first = hook.current
    rerender({ msgs: [...messages] })
    expect(hook.current).toBe(first)
  })
})
