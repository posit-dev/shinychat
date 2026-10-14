import { describe, it, expect } from "vitest"
import { renderHook } from "@testing-library/react"
import { useSupersededRequests } from "../../src/chat/useSupersededRequests"
import {
  structuredBlockToLoop,
  type ChatMessageData,
} from "../../src/chat/state"
import type {
  ToolRequestBlock,
  ToolResultBlock,
} from "../../src/transport/types"

const request = (id: string): ToolRequestBlock => ({
  type: "tool_request",
  version: 1,
  request_id: id,
  tool_name: "search",
  arguments: "{}",
})

const result = (id: string): ToolResultBlock => ({
  type: "tool_result",
  version: 1,
  request_id: id,
  tool_name: "search",
  status: "success",
  value: "ok",
  value_type: "text",
})

function loopMessage(
  blocks: Array<ToolRequestBlock | ToolResultBlock>,
): ChatMessageData {
  const loops = blocks
    .map((b) => structuredBlockToLoop(b, "tool"))
    .filter((l) => l !== null)
  return {
    id: "m",
    role: "assistant",
    content: "",
    streaming: false,
    blocks: loops,
  }
}

describe("useSupersededRequests", () => {
  it("supersedes a paired request", () => {
    const { result: hook } = renderHook(() =>
      useSupersededRequests(
        [loopMessage([request("req-1"), result("req-1")])],
        null,
      ),
    )
    expect(hook.current.has("req-1")).toBe(true)
  })

  it("leaves a request alone when its result never arrives", () => {
    const { result: hook } = renderHook(() =>
      useSupersededRequests([loopMessage([request("req-1")])], null),
    )
    expect(hook.current.size).toBe(0)
  })

  // The set reaches every message through context, so a fresh identity on each
  // render would re-render the whole transcript per streaming chunk.
  it("keeps the same Set identity while membership is unchanged", () => {
    const messages = [loopMessage([request("req-1"), result("req-1")])]
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
