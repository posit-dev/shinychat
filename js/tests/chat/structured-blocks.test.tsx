import { describe, it, expect, vi, afterEach } from "vitest"
import { render } from "@testing-library/react"

vi.mock("../../src/chat/TiptapInput", async () => {
  const { FakeTiptapInput } = await import("../helpers/fakeTiptapInput")
  return { TiptapInput: FakeTiptapInput }
})

import { ChatMessages } from "../../src/chat/ChatMessages"
import {
  chatReducer,
  initialState,
  type ChatMessageData,
  type ChatState,
} from "../../src/chat/state"
import type {
  ChatAction,
  StructuredBlock,
  ToolResultBlock,
} from "../../src/transport/types"

// Keystone slice for the structured-content-types epic: a `tool_result`
// structured block flows Python → wire → reducer → rendered card, both via
// `message.segments` (settled) and via `block_insert` (mid-stream). The
// envelope — not markup scanned out of a content string — is what produces
// trusted tool UI.

const toolResultBlock = (
  overrides: Partial<ToolResultBlock> = {},
): ToolResultBlock => ({
  type: "tool_result",
  version: 1,
  request_id: "call-1",
  tool_name: "get_weather",
  status: "success",
  value: "72F and sunny",
  value_type: "text",
  title: "Looked up weather",
  expanded: true,
  ...overrides,
})

function makeState(overrides: Partial<ChatState> = {}): ChatState {
  return { ...initialState, ...overrides }
}

function renderMessages(messages: ChatMessageData[]) {
  return render(<ChatMessages messages={messages} inputId="test-input" />)
}

function expectToolCard(container: HTMLElement, value: string) {
  // The tool-loop chrome (condensed row)…
  expect(container.querySelector(".shiny-chat-tool-group")).not.toBeNull()
  // …and, because the block is `expanded`, the drill-down card with the value.
  expect(container.querySelector(".shiny-tool-card")).not.toBeNull()
  expect(container.textContent).toContain(value)
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe("structured tool_result block via message.segments", () => {
  it("reduces to a tool_loop block and renders a real tool card", () => {
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [
          { content: "Before the call. ", content_type: "markdown" },
          toolResultBlock(),
          { content: " After the call.", content_type: "markdown" },
        ],
      },
    })

    expect(state.messages).toHaveLength(1)
    const blocks = state.messages[0]!.blocks
    expect(blocks.map((b) => b.type)).toEqual([
      "content",
      "tool_loop",
      "content",
    ])

    const { container } = renderMessages(state.messages)
    expectToolCard(container, "72F and sunny")

    // Content renders in segment order around the card.
    const text = container.textContent ?? ""
    expect(text.indexOf("Before the call.")).toBeLessThan(
      text.indexOf("72F and sunny"),
    )
    expect(text.indexOf("72F and sunny")).toBeLessThan(
      text.indexOf("After the call."),
    )
  })

  it("adjacent structured blocks merge into one tool loop", () => {
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [
          toolResultBlock({ request_id: "call-1" }),
          toolResultBlock({ request_id: "call-2", value: "rain later" }),
        ],
      },
    })

    const blocks = state.messages[0]!.blocks
    expect(blocks.map((b) => b.type)).toEqual(["tool_loop"])
    const loop = blocks[0]!
    if (loop.type !== "tool_loop") throw new Error("expected tool_loop")
    const calls = loop.groups.flatMap((g) => g.calls)
    expect(calls.map((c) => c.requestId)).toEqual(["call-1", "call-2"])
  })

  it("maps the full field surface onto the ToolCallItem", () => {
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [
          toolResultBlock({
            icon: "<svg></svg>",
            intent: "check weather",
            label: "duluth.txt",
            value_preview: "72F",
            request_call: 'get_weather("Duluth")',
            show_request: true,
            full_screen: true,
            open_style: "framed",
            custom_display: true,
            footer: "<em>footer</em>",
            grouping: "none",
          }),
        ],
      },
    })

    const loop = state.messages[0]!.blocks[0]!
    if (loop.type !== "tool_loop") throw new Error("expected tool_loop")
    const call = loop.groups.flatMap((g) => g.calls)[0]!
    expect(call).toMatchObject({
      requestId: "call-1",
      localId: "call-1",
      toolName: "get_weather",
      status: "success",
      title: "Looked up weather",
      icon: "<svg></svg>",
      intent: "check weather",
      label: "duluth.txt",
      valuePreview: "72F",
      value: "72F and sunny",
      valueType: "text",
      requestCall: 'get_weather("Duluth")',
      showRequest: true,
      fullScreen: true,
      openStyle: "framed",
      expanded: true,
      customDisplay: true,
      footer: "<em>footer</em>",
      grouping: "none",
    })
  })

  it("ignores unknown block types and unsupported versions with a warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const unknownType = {
      type: "web_search",
      version: 1,
      query: "kittens",
    } as unknown as StructuredBlock
    const unknownVersion = {
      ...toolResultBlock(),
      version: 2,
    } as unknown as StructuredBlock

    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [
          { content: "just text", content_type: "markdown" },
          unknownType,
          unknownVersion,
        ],
      },
    })

    const blocks = state.messages[0]!.blocks
    expect(blocks.map((b) => b.type)).toEqual(["content"])
    expect(warn).toHaveBeenCalledTimes(2)
  })
})

describe("structured tool_result block via block_insert mid-stream", () => {
  function startStream(state: ChatState): ChatState {
    return chatReducer(state, {
      type: "chunk_start",
      message: { role: "assistant", segments: [] },
    })
  }

  it("appends a render-ready tool loop to the in-flight message", () => {
    let state = startStream(makeState())
    state = chatReducer(state, {
      type: "chunk",
      content: "Before the call. ",
      operation: "append",
    })
    state = chatReducer(state, {
      type: "block_insert",
      block: toolResultBlock(),
    })

    // Mid-stream: the block is already render-ready in the streaming message.
    const midBlocks = state.streamingMessage!.blocks
    expect(midBlocks.map((b) => b.type)).toEqual(["content", "tool_loop"])

    state = chatReducer(state, {
      type: "chunk",
      content: " After the call.",
      operation: "append",
    })

    // A string chunk after a block_insert starts a NEW content block.
    const blocks = state.streamingMessage!.blocks
    expect(blocks.map((b) => b.type)).toEqual([
      "content",
      "tool_loop",
      "content",
    ])

    state = chatReducer(state, { type: "chunk_end" })
    expect(state.streamingMessage).toBeNull()
    expect(state.messages).toHaveLength(1)
    expect(state.messages[0]!.blocks.map((b) => b.type)).toEqual([
      "content",
      "tool_loop",
      "content",
    ])

    const { container } = renderMessages(state.messages)
    expectToolCard(container, "72F and sunny")

    const text = container.textContent ?? ""
    expect(text.indexOf("Before the call.")).toBeLessThan(
      text.indexOf("72F and sunny"),
    )
    expect(text.indexOf("72F and sunny")).toBeLessThan(
      text.indexOf("After the call."),
    )
  })

  it("merges into an adjacent trailing tool loop", () => {
    let state = startStream(makeState())
    state = chatReducer(state, {
      type: "block_insert",
      block: toolResultBlock({ request_id: "call-1" }),
    })
    state = chatReducer(state, {
      type: "block_insert",
      block: toolResultBlock({ request_id: "call-2", value: "rain later" }),
    })

    const blocks = state.streamingMessage!.blocks
    expect(blocks.map((b) => b.type)).toEqual(["tool_loop"])
    const loop = blocks[0]!
    if (loop.type !== "tool_loop") throw new Error("expected tool_loop")
    const calls = loop.groups.flatMap((g) => g.calls)
    expect(calls.map((c) => c.requestId)).toEqual(["call-1", "call-2"])
  })

  it("does not disturb thinking-tag/fence stream state", () => {
    let state = startStream(makeState())
    // Open a code fence, then insert a block: the fence state must survive.
    state = chatReducer(state, {
      type: "chunk",
      content: "```\nsome code",
      operation: "append",
    })
    expect(state.streamingMessage!.insideFence).toBe(true)

    state = chatReducer(state, {
      type: "block_insert",
      block: toolResultBlock(),
    })
    expect(state.streamingMessage!.insideFence).toBe(true)
    expect(state.streamingMessage!.blocks.map((b) => b.type)).toEqual([
      "content",
      "tool_loop",
    ])
  })

  it("is a no-op with a warning when no stream is in flight", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const before = makeState()
    const state = chatReducer(before, {
      type: "block_insert",
      block: toolResultBlock(),
    })
    expect(state).toBe(before) // reference equality: untouched
    expect(warn).toHaveBeenCalled()
  })

  it("ignores unknown block types and unsupported versions with a warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    let state = startStream(makeState())
    state = chatReducer(state, {
      type: "block_insert",
      block: {
        type: "html_block",
        version: 1,
        content: "<div></div>",
      } as unknown as StructuredBlock,
    })
    state = chatReducer(state, {
      type: "block_insert",
      block: { ...toolResultBlock(), version: 2 } as unknown as StructuredBlock,
    })

    expect(state.streamingMessage!.blocks).toHaveLength(0)
    expect(warn).toHaveBeenCalledTimes(2)
  })
})

describe("structured loops survive regrouping", () => {
  it("SET_TOOL_GROUPING keeps the structured tool_loop block", () => {
    let state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [toolResultBlock()],
      },
    })
    state = chatReducer(state, { type: "SET_TOOL_GROUPING", grouping: "all" })

    const blocks = state.messages[0]!.blocks
    expect(blocks.map((b) => b.type)).toEqual(["tool_loop"])
    const loop = blocks[0]!
    if (loop.type !== "tool_loop") throw new Error("expected tool_loop")
    expect(loop.groups.flatMap((g) => g.calls)).toHaveLength(1)

    const { container } = renderMessages(state.messages)
    expectToolCard(container, "72F and sunny")
  })
})
