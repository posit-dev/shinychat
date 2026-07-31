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
  // The regression this guards: a `contents_shinychat()` method (R) or a
  // `message_content_chunk` handler (Python) may render a tool result as
  // arbitrary UI, emitting no <shiny-tool-result> at all. Nothing in the
  // transcript then proves the call finished, so the request row spins forever
  // unless the server's signal is honored.
  it("supersedes a request whose result left no element to derive from", () => {
    const { result: hook } = renderHook(() =>
      useSupersededRequests(
        [message(request("req-1"))],
        null,
        new Set(["req-1"]),
      ),
    )
    expect(hook.current.has("req-1")).toBe(true)
  })

  // The other half of the pair: the derivation must keep standing on its own,
  // because the server's action fires only from the live streaming loop and is
  // absent on restore/reload. Deleting it would resurrect every superseded
  // request row in a reloaded transcript.
  it("supersedes a paired request with no signal at all", () => {
    const { result: hook } = renderHook(() =>
      useSupersededRequests(
        [message(request("req-1") + result("req-1"))],
        null,
        new Set(),
      ),
    )
    expect(hook.current.has("req-1")).toBe(true)
  })

  it("unions both sources", () => {
    const { result: hook } = renderHook(() =>
      useSupersededRequests(
        [message(request("derived") + result("derived"))],
        null,
        new Set(["signalled"]),
      ),
    )
    expect([...hook.current].sort()).toEqual(["derived", "signalled"])
  })

  it("leaves a request alone when neither source supersedes it", () => {
    const { result: hook } = renderHook(() =>
      useSupersededRequests([message(request("req-1"))], null, new Set()),
    )
    expect(hook.current.size).toBe(0)
  })

  // The set reaches every message through context, so a fresh identity on each
  // render would re-render the whole transcript per streaming chunk.
  it("keeps the same Set identity while membership is unchanged", () => {
    const messages = [message(request("req-1") + result("req-1"))]
    const { result: hook, rerender } = renderHook(
      ({ msgs }: { msgs: ChatMessageData[] }) =>
        useSupersededRequests(msgs, null, new Set()),
      { initialProps: { msgs: messages } },
    )
    const first = hook.current
    rerender({ msgs: [...messages] })
    expect(hook.current).toBe(first)
  })
})
