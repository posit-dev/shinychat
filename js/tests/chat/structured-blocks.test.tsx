import { describe, it, expect, vi, afterEach } from "vitest"
import { fireEvent, render, act } from "@testing-library/react"

vi.mock("../../src/chat/TiptapInput", async () => {
  const { FakeTiptapInput } = await import("../helpers/fakeTiptapInput")
  return { TiptapInput: FakeTiptapInput }
})

import { ChatMessages } from "../../src/chat/ChatMessages"
import { ChatToolContext, ShinyLifecycleContext } from "../../src/chat/context"
import {
  chatReducer,
  initialState,
  supersededRequestIds,
  type ChatMessageData,
  type ChatState,
} from "../../src/chat/state"
import type {
  ChatAction,
  HtmlBlock,
  StructuredBlock,
  ToolRequestBlock,
  ToolResultBlock,
  WebFetchBlock,
  WebSearchBlock,
  WebSearchResultsBlock,
} from "../../src/transport/types"
import type { ShinyLifecycle, HtmlDep } from "../../src/transport/types"

// Keystone slice for the structured-content-types epic: `tool_request` and
// `tool_result` structured blocks flow Python → wire → reducer → rendered
// card, both via `message.segments` (settled) and via `block_insert`
// (mid-stream). The envelope — not markup scanned out of a content string —
// is what produces trusted tool UI.

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

const toolRequestBlock = (
  overrides: Partial<ToolRequestBlock> = {},
): ToolRequestBlock => ({
  type: "tool_request",
  version: 1,
  request_id: "call-1",
  tool_name: "get_weather",
  title: "Looking up weather",
  intent: "check weather",
  arguments: '{"location":"Duluth"}',
  ...overrides,
})

const webSearchBlock = (
  overrides: Partial<WebSearchBlock> = {},
): WebSearchBlock => ({
  type: "web_search",
  version: 1,
  query: "weather in Duluth",
  ...overrides,
})

const webSearchResultsBlock = (
  overrides: Partial<WebSearchResultsBlock> = {},
): WebSearchResultsBlock => ({
  type: "web_search_results",
  version: 1,
  sources: [
    { url: "https://example.com/weather", title: "Duluth weather" },
    { url: "https://example.org/forecast" },
  ],
  ...overrides,
})

const webFetchBlock = (
  overrides: Partial<WebFetchBlock> = {},
): WebFetchBlock => ({
  type: "web_fetch",
  version: 1,
  url: "https://example.net/article",
  status: "success",
  ...overrides,
})

const htmlBlock = (overrides: Partial<HtmlBlock> = {}): HtmlBlock => ({
  type: "html_block",
  version: 1,
  content: '<div class="island">Hello from HTML</div>',
  ...overrides,
})

/** A minimal mock ShinyLifecycle for deps-before-innerHTML ordering tests. */
function mockShiny(): ShinyLifecycle {
  return {
    bindAll: vi.fn().mockResolvedValue(undefined),
    unbindAll: vi.fn(),
    renderDependencies: vi.fn().mockResolvedValue(undefined),
    showClientMessage: vi.fn(),
  }
}

/** Minimal HtmlDep stub for tests (the real type is opaque from shiny). */
function fakeDep(name: string): HtmlDep {
  return { name, version: "1.0.0" } as unknown as HtmlDep
}

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
      type: "future_block",
      version: 1,
      content: "<div></div>",
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
        type: "future_block",
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

  it("SET_TOOL_GROUPING keeps both calls of a mixed markup+structured loop", () => {
    // A markup-derived result and a structured block merge into ONE loop on
    // arrival. That loop is mixed: it carries a raw content slice (the
    // markup) AND a call with `structured: true` provenance. Rerouting must
    // not unwind the whole loop into its content slice — that would re-parse
    // the markup call but silently drop the structured one.
    const markup =
      '<shiny-tool-result data-shinychat-react request-id="call-markup" tool-name="get_weather" status="success" value="rain later" value-type="text"></shiny-tool-result>'
    let state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [
          { content: markup, content_type: "html" },
          toolResultBlock({ request_id: "call-structured" }),
        ],
      },
    })

    // On arrival: one merged loop holding both calls, markup slice intact.
    let loop = state.messages[0]!.blocks[0]!
    expect(state.messages[0]!.blocks.map((b) => b.type)).toEqual(["tool_loop"])
    if (loop.type !== "tool_loop") throw new Error("expected tool_loop")
    expect(loop.content).toContain("<shiny-tool-result")
    let calls = loop.groups.flatMap((g) => g.calls)
    expect(calls.map((c) => c.requestId)).toEqual([
      "call-markup",
      "call-structured",
    ])
    expect(calls[1]!.structured).toBe(true)

    state = chatReducer(state, { type: "SET_TOOL_GROUPING", grouping: "all" })

    // After the regroup: still one loop, and BOTH calls survive — the
    // markup-derived one re-parsed from the content slice and the
    // structured-derived one re-grouped from its stored call data.
    const blocks = state.messages[0]!.blocks
    expect(blocks.map((b) => b.type)).toEqual(["tool_loop"])
    loop = blocks[0]!
    if (loop.type !== "tool_loop") throw new Error("expected tool_loop")
    calls = loop.groups.flatMap((g) => g.calls)
    expect(calls.map((c) => c.requestId)).toEqual([
      "call-markup",
      "call-structured",
    ])
    expect(
      calls.find((c) => c.requestId === "call-structured")!.structured,
    ).toBe(true)

    const { container } = renderMessages(state.messages)
    expectToolCard(container, "72F and sunny")
  })
})

describe("structured tool_request block via message.segments", () => {
  it("reduces to a running tool_loop call and renders the running row", () => {
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [
          { content: "Before the call. ", content_type: "markdown" },
          toolRequestBlock(),
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

    // An unpaired request derives a running call (pairToolEvents' convention
    // for new request ids); "running" is never a wire value.
    const loop = blocks[1]!
    if (loop.type !== "tool_loop") throw new Error("expected tool_loop")
    const call = loop.groups.flatMap((g) => g.calls)[0]!
    expect(call.status).toBe("running")
    expect(call.structured).toBe(true)

    const { container } = renderMessages(state.messages)
    // The condensed row renders the running call under its definition title.
    expect(container.querySelector(".shiny-chat-tool-group")).not.toBeNull()
    expect(container.textContent).toContain("Looking up weather")
    expect(container.textContent).toContain("Running…")

    // Content renders in segment order around the row.
    const text = container.textContent ?? ""
    expect(text.indexOf("Before the call.")).toBeLessThan(
      text.indexOf("Looking up weather"),
    )
    expect(text.indexOf("Looking up weather")).toBeLessThan(
      text.indexOf("After the call."),
    )
  })

  it("maps the full field surface onto the ToolCallItem", () => {
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [
          toolRequestBlock({
            icon: "<svg></svg>",
            grouping: "none",
          }),
        ],
      },
    })

    const loop = state.messages[0]!.blocks[0]!
    if (loop.type !== "tool_loop") throw new Error("expected tool_loop")
    const call = loop.groups.flatMap((g) => g.calls)[0]!
    // The request carries the tool *definition's* title/icon; the result's
    // own title/icon settle over them when it arrives.
    expect(call).toMatchObject({
      requestId: "call-1",
      localId: "call-1",
      toolName: "get_weather",
      status: "running",
      definitionTitle: "Looking up weather",
      definitionIcon: "<svg></svg>",
      intent: "check weather",
      arguments: '{"location":"Duluth"}',
      grouping: "none",
      structured: true,
    })
    // A request carries no result-level fields.
    expect(call.title).toBeUndefined()
    expect(call.icon).toBeUndefined()
    expect(call.value).toBeUndefined()
  })

  it("hides the running request row once its result arrives", () => {
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [toolRequestBlock(), toolResultBlock()],
      },
    })

    // Both calls land in one merged loop — the request stays running in the
    // lifecycle model (pairing is a presentation concern)…
    const blocks = state.messages[0]!.blocks
    expect(blocks.map((b) => b.type)).toEqual(["tool_loop"])
    const loop = blocks[0]!
    if (loop.type !== "tool_loop") throw new Error("expected tool_loop")
    const calls = loop.groups.flatMap((g) => g.calls)
    expect(
      calls.map((c) => ({ requestId: c.requestId, status: c.status })),
    ).toEqual([
      { requestId: "call-1", status: "running" },
      { requestId: "call-1", status: "success" },
    ])

    // …but transcript-wide supersession (derived from the structured result
    // block) hides the running request row, leaving the settled result card.
    const superseded = supersededRequestIds(state.messages, null)
    expect([...superseded]).toEqual(["call-1"])
    const { container } = render(
      <ChatToolContext.Provider value={{ supersededRequests: superseded }}>
        <ChatMessages messages={state.messages} inputId="test-input" />
      </ChatToolContext.Provider>,
    )
    expectToolCard(container, "72F and sunny")
    expect(container.textContent).not.toContain("Running…")
  })
})

describe("structured tool_request block via block_insert mid-stream", () => {
  function startStream(state: ChatState): ChatState {
    return chatReducer(state, {
      type: "chunk_start",
      message: { role: "assistant", segments: [] },
    })
  }

  it("appends a render-ready running tool loop to the in-flight message", () => {
    let state = startStream(makeState())
    state = chatReducer(state, {
      type: "chunk",
      content: "Checking the weather. ",
      operation: "append",
    })
    state = chatReducer(state, {
      type: "block_insert",
      block: toolRequestBlock(),
    })

    // Mid-stream: the block is already render-ready in the streaming message.
    const blocks = state.streamingMessage!.blocks
    expect(blocks.map((b) => b.type)).toEqual(["content", "tool_loop"])
    const loop = blocks[1]!
    if (loop.type !== "tool_loop") throw new Error("expected tool_loop")
    const call = loop.groups.flatMap((g) => g.calls)[0]!
    expect(call.status).toBe("running")
    expect(call.structured).toBe(true)

    state = chatReducer(state, { type: "chunk_end" })
    expect(state.streamingMessage).toBeNull()
    const { container } = renderMessages(state.messages)
    expect(container.querySelector(".shiny-chat-tool-group")).not.toBeNull()
    expect(container.textContent).toContain("Running…")
  })

  it("a result block for the same request merges into the request's loop", () => {
    let state = startStream(makeState())
    state = chatReducer(state, {
      type: "block_insert",
      block: toolRequestBlock(),
    })
    state = chatReducer(state, {
      type: "block_insert",
      block: toolResultBlock(),
    })

    const blocks = state.streamingMessage!.blocks
    expect(blocks.map((b) => b.type)).toEqual(["tool_loop"])
    const loop = blocks[0]!
    if (loop.type !== "tool_loop") throw new Error("expected tool_loop")
    const calls = loop.groups.flatMap((g) => g.calls)
    expect(
      calls.map((c) => ({ requestId: c.requestId, status: c.status })),
    ).toEqual([
      { requestId: "call-1", status: "running" },
      { requestId: "call-1", status: "success" },
    ])

    state = chatReducer(state, { type: "chunk_end" })
    const superseded = supersededRequestIds(state.messages, null)
    const { container } = render(
      <ChatToolContext.Provider value={{ supersededRequests: superseded }}>
        <ChatMessages messages={state.messages} inputId="test-input" />
      </ChatToolContext.Provider>,
    )
    expectToolCard(container, "72F and sunny")
    expect(container.textContent).not.toContain("Running…")
  })

  it("adjacent structured requests merge into one tool loop", () => {
    let state = startStream(makeState())
    state = chatReducer(state, {
      type: "block_insert",
      block: toolRequestBlock({ request_id: "call-1" }),
    })
    state = chatReducer(state, {
      type: "block_insert",
      block: toolRequestBlock({
        request_id: "call-2",
        tool_name: "get_time",
        title: "Checking the time",
      }),
    })

    const blocks = state.streamingMessage!.blocks
    expect(blocks.map((b) => b.type)).toEqual(["tool_loop"])
    const loop = blocks[0]!
    if (loop.type !== "tool_loop") throw new Error("expected tool_loop")
    const calls = loop.groups.flatMap((g) => g.calls)
    expect(calls.map((c) => c.requestId)).toEqual(["call-1", "call-2"])
    expect(calls.every((c) => c.status === "running")).toBe(true)
  })
})

describe("structured web_* blocks via message.segments", () => {
  it("groups adjacent web blocks into one web_activity, pairing results with the pending search", () => {
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [
          { content: "Before the burst. ", content_type: "markdown" },
          webSearchBlock(),
          webSearchResultsBlock(),
          webFetchBlock(),
          { content: " After the burst.", content_type: "markdown" },
        ],
      },
    })

    expect(state.messages).toHaveLength(1)
    const blocks = state.messages[0]!.blocks
    expect(blocks.map((b) => b.type)).toEqual([
      "content",
      "web_activity",
      "content",
    ])

    // The results block attached its sources to the still-pending search;
    // the fetch appended a standalone item (parseItems' adjacency pairing,
    // re-expressed over structured arrival).
    const activity = blocks[1]!
    if (activity.type !== "web_activity")
      throw new Error("expected web_activity")
    expect(activity.items).toEqual([
      {
        kind: "search",
        query: "weather in Duluth",
        sources: [
          { url: "https://example.com/weather", title: "Duluth weather" },
          { url: "https://example.org/forecast" },
        ],
        citedSources: [],
      },
      { kind: "fetch", url: "https://example.net/article", status: "success" },
    ])

    // The grouped activity renders without a markup round-trip.
    const { container } = renderMessages(state.messages)
    expect(container.querySelector(".shiny-web-activity")).not.toBeNull()
    const text = container.textContent ?? ""
    expect(text.indexOf("Before the burst.")).toBeLessThan(
      text.indexOf("Searched the web"),
    )
    expect(text.indexOf("Searched the web")).toBeLessThan(
      text.indexOf("After the burst."),
    )
  })

  it("tolerates whitespace-only content between carriers", () => {
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [
          webSearchBlock(),
          // rehypeGroupWebActivity tolerates whitespace text nodes between
          // carriers; the structured path drops the whitespace-only block.
          { content: " \n", content_type: "markdown" },
          webSearchResultsBlock(),
          webFetchBlock(),
        ],
      },
    })

    const blocks = state.messages[0]!.blocks
    expect(blocks.map((b) => b.type)).toEqual(["web_activity"])
    const activity = blocks[0]!
    if (activity.type !== "web_activity")
      throw new Error("expected web_activity")
    expect(activity.items.map((it) => it.kind)).toEqual(["search", "fetch"])
    // The dropped separator leaves no stray content behind.
    expect(state.messages[0]!.content).toBe("")

    // A web-activity-only message still renders (hasContent counts it).
    const { container } = renderMessages(state.messages)
    expect(container.querySelector(".shiny-web-activity")).not.toBeNull()
  })

  it("ends the activity run when prose intervenes", () => {
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [
          webSearchBlock(),
          { content: " Some prose. ", content_type: "markdown" },
          webFetchBlock(),
        ],
      },
    })

    const blocks = state.messages[0]!.blocks
    expect(blocks.map((b) => b.type)).toEqual([
      "web_activity",
      "content",
      "web_activity",
    ])
    const first = blocks[0]!
    if (first.type !== "web_activity") throw new Error("expected web_activity")
    // The first run's search never met its results: it stays pending.
    expect(first.items).toEqual([
      {
        kind: "search",
        query: "weather in Duluth",
        sources: null,
        citedSources: [],
      },
    ])
    const second = blocks[2]!
    if (second.type !== "web_activity") throw new Error("expected web_activity")
    expect(second.items).toEqual([
      { kind: "fetch", url: "https://example.net/article", status: "success" },
    ])
  })

  it("attaches a search block's cited_sources as the cited-sources fallback", () => {
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [
          webSearchBlock({
            cited_sources: [
              { url: "https://example.com/cited", title: "Cited page" },
              { url: "https://example.org/also-cited" },
            ],
          }),
        ],
      },
    })

    const activity = state.messages[0]!.blocks[0]!
    if (activity.type !== "web_activity")
      throw new Error("expected web_activity")
    expect(activity.items).toEqual([
      {
        kind: "search",
        query: "weather in Duluth",
        sources: null,
        citedSources: [
          { url: "https://example.com/cited", title: "Cited page" },
          { url: "https://example.org/also-cited" },
        ],
      },
    ])

    // With no results attached, the fallback renders as cited sources.
    const { container } = renderMessages(state.messages)
    fireEvent.click(container.querySelector(".shiny-web-activity__header")!)
    expect(container.textContent).toContain("Cited sources")
    expect(container.textContent).toContain("Cited page")
  })

  it("results pairing overrides the cited_sources fallback", () => {
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [
          webSearchBlock({
            cited_sources: [
              { url: "https://example.com/cited", title: "Cited page" },
            ],
          }),
          webSearchResultsBlock(),
        ],
      },
    })

    const activity = state.messages[0]!.blocks[0]!
    if (activity.type !== "web_activity")
      throw new Error("expected web_activity")
    const search = activity.items[0]!
    if (search.kind !== "search") throw new Error("expected search item")
    // The results' sources pair onto the search; the cited sources stay on
    // the item but lose to the real result list (`sources ?? citedSources`).
    expect(search.sources).toHaveLength(2)
    expect(search.citedSources).toEqual([
      { url: "https://example.com/cited", title: "Cited page" },
    ])

    const { container } = renderMessages(state.messages)
    fireEvent.click(container.querySelector(".shiny-web-activity__header")!)
    expect(container.textContent).toContain("2 results")
    expect(container.textContent).toContain("Duluth weather")
    expect(container.textContent).not.toContain("Cited sources")
    expect(container.textContent).not.toContain("Cited page")
  })

  it("ignores web blocks with unsupported versions with a warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [
          { content: "just text", content_type: "markdown" },
          { ...webSearchBlock(), version: 2 } as unknown as StructuredBlock,
          { ...webFetchBlock(), version: 2 } as unknown as StructuredBlock,
        ],
      },
    })

    const blocks = state.messages[0]!.blocks
    expect(blocks.map((b) => b.type)).toEqual(["content"])
    expect(warn).toHaveBeenCalledTimes(2)
  })
})

describe("structured web_* blocks via block_insert mid-stream", () => {
  function startStream(state: ChatState): ChatState {
    return chatReducer(state, {
      type: "chunk_start",
      message: { role: "assistant", segments: [] },
    })
  }

  it("pairs a results block with a search inserted earlier in the stream", () => {
    let state = startStream(makeState())
    state = chatReducer(state, {
      type: "block_insert",
      block: webSearchBlock(),
    })

    // The search sits pending in a fresh activity until its results arrive.
    const midBlocks = state.streamingMessage!.blocks
    expect(midBlocks.map((b) => b.type)).toEqual(["web_activity"])
    const midActivity = midBlocks[0]!
    if (midActivity.type !== "web_activity")
      throw new Error("expected web_activity")
    expect(midActivity.items).toEqual([
      {
        kind: "search",
        query: "weather in Duluth",
        sources: null,
        citedSources: [],
      },
    ])

    state = chatReducer(state, {
      type: "block_insert",
      block: webSearchResultsBlock(),
    })

    // Pairing works across the block_insert boundary: the pending state
    // lives in the item itself (sources === null).
    const blocks = state.streamingMessage!.blocks
    expect(blocks.map((b) => b.type)).toEqual(["web_activity"])
    const activity = blocks[0]!
    if (activity.type !== "web_activity")
      throw new Error("expected web_activity")
    expect(activity.items).toHaveLength(1)
    const search = activity.items[0]!
    if (search.kind !== "search") throw new Error("expected search item")
    expect(search.sources).toHaveLength(2)

    // A later search starts a new pending item; it doesn't disturb the
    // already-paired one.
    state = chatReducer(state, {
      type: "block_insert",
      block: webSearchBlock({ query: "second query" }),
    })
    const after = state.streamingMessage!.blocks[0]!
    if (after.type !== "web_activity") throw new Error("expected web_activity")
    expect(after.items.map((it) => it.kind)).toEqual(["search", "search"])
    const secondSearch = after.items[1]!
    if (secondSearch.kind !== "search") throw new Error("expected search item")
    expect(secondSearch.query).toBe("second query")
    expect(secondSearch.sources).toBeNull()
  })

  it("renders an expandable activity that survives chunk_end", () => {
    let state = startStream(makeState())
    state = chatReducer(state, {
      type: "chunk",
      content: "Checking the web. ",
      operation: "append",
    })
    state = chatReducer(state, {
      type: "block_insert",
      block: webSearchBlock(),
    })
    state = chatReducer(state, {
      type: "block_insert",
      block: webSearchResultsBlock(),
    })
    state = chatReducer(state, {
      type: "block_insert",
      block: webFetchBlock(),
    })

    // Mid-stream: the burst is already grouped render-ready.
    expect(state.streamingMessage!.blocks.map((b) => b.type)).toEqual([
      "content",
      "web_activity",
    ])

    state = chatReducer(state, { type: "chunk_end" })
    expect(state.streamingMessage).toBeNull()
    expect(state.messages[0]!.blocks.map((b) => b.type)).toEqual([
      "content",
      "web_activity",
    ])

    const { container } = renderMessages(state.messages)
    const header = container.querySelector(".shiny-web-activity__header")
    expect(header).not.toBeNull()
    expect(container.textContent).toContain("Searched the web")

    // Collapsed by default; clicking the header expands the timeline.
    expect(container.querySelector(".shiny-web-activity__timeline")).toBeNull()
    fireEvent.click(header!)
    expect(header!.getAttribute("aria-expanded")).toBe("true")
    expect(
      container.querySelector(".shiny-web-activity__timeline"),
    ).not.toBeNull()
    expect(container.textContent).toContain("weather in Duluth")
    expect(container.textContent).toContain("2 results")
    expect(container.textContent).toContain("Duluth weather")
    // The title-less source falls back to its derived domain.
    expect(container.textContent).toContain("example.org")
    // The fetch item renders with its URL and success status.
    expect(container.querySelector(".shiny-web-activity__fetch")).not.toBeNull()
    expect(container.textContent).toContain("https://example.net/article")
    expect(
      container.querySelector(".shiny-web-activity__status--ok"),
    ).not.toBeNull()

    // Segment order around the activity is preserved.
    const text = container.textContent ?? ""
    expect(text.indexOf("Checking the web.")).toBeLessThan(
      text.indexOf("Searched the web"),
    )
  })

  it("ignores web blocks with unsupported versions with a warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    let state = startStream(makeState())
    state = chatReducer(state, {
      type: "block_insert",
      block: { ...webSearchBlock(), version: 2 } as unknown as StructuredBlock,
    })

    expect(state.streamingMessage!.blocks).toHaveLength(0)
    expect(warn).toHaveBeenCalledTimes(1)
  })
})

describe("structured html_block via message.segments", () => {
  it("reduces to an html_block and renders innerHTML in segment order", () => {
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [
          { content: "Before the island. ", content_type: "markdown" },
          htmlBlock({ content: "<p class='island'>Island HTML</p>" }),
          { content: " After the island.", content_type: "markdown" },
        ],
      },
    })

    expect(state.messages).toHaveLength(1)
    const blocks = state.messages[0]!.blocks
    expect(blocks.map((b) => b.type)).toEqual([
      "content",
      "html_block",
      "content",
    ])

    const block = blocks[1]!
    if (block.type !== "html_block") throw new Error("expected html_block")
    expect(block.content).toBe("<p class='island'>Island HTML</p>")
    expect(block.contentType).toBe("html")

    const { container } = renderMessages(state.messages)
    const island = container.querySelector(".island")
    expect(island).not.toBeNull()
    expect(island!.innerHTML).toBe("Island HTML")

    // Content renders in segment order around the island.
    const text = container.textContent ?? ""
    expect(text.indexOf("Before the island.")).toBeLessThan(
      text.indexOf("Island HTML"),
    )
    expect(text.indexOf("Island HTML")).toBeLessThan(
      text.indexOf("After the island."),
    )
  })

  it("merges block-level html_deps into the message htmlDeps", () => {
    const dep = fakeDep("island-dep")
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [htmlBlock({ html_deps: [dep] })],
      },
    })

    // Block-level deps ride the message envelope so snapshots retain them.
    expect(state.messages[0]!.htmlDeps).toEqual([dep])
  })

  it("merges block-level deps with envelope-level html_deps", () => {
    const blockDep = fakeDep("block-dep")
    const envDep = fakeDep("env-dep")
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [htmlBlock({ html_deps: [blockDep] })],
      },
      html_deps: [envDep],
    })

    // Both sets merge onto the message.
    expect(state.messages[0]!.htmlDeps).toEqual([blockDep, envDep])
  })

  it("ignores html_block in a user-role message with a warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "user",
        segments: [htmlBlock()],
      },
    })

    expect(state.messages[0]!.blocks.map((b) => b.type)).toEqual([])
    expect(warn).toHaveBeenCalled()
  })

  it("ignores html_block with unsupported version with a warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [
          { content: "just text", content_type: "markdown" },
          { ...htmlBlock(), version: 2 } as unknown as StructuredBlock,
        ],
      },
    })

    expect(state.messages[0]!.blocks.map((b) => b.type)).toEqual(["content"])
    expect(warn).toHaveBeenCalledTimes(1)
  })
})

describe("structured html_block via block_insert mid-stream", () => {
  function startStream(state: ChatState): ChatState {
    return chatReducer(state, {
      type: "chunk_start",
      message: { role: "assistant", segments: [] },
    })
  }

  it("appends a render-ready html_block to the in-flight message", () => {
    let state = startStream(makeState())
    state = chatReducer(state, {
      type: "chunk",
      content: "Before the island. ",
      operation: "append",
    })
    state = chatReducer(state, {
      type: "block_insert",
      block: htmlBlock({ content: "<p class='island'>Mid-stream island</p>" }),
    })

    // Mid-stream: the block is already render-ready.
    const midBlocks = state.streamingMessage!.blocks
    expect(midBlocks.map((b) => b.type)).toEqual(["content", "html_block"])

    // A string chunk after a block_insert starts a NEW content block.
    state = chatReducer(state, {
      type: "chunk",
      content: " After the island.",
      operation: "append",
    })
    expect(state.streamingMessage!.blocks.map((b) => b.type)).toEqual([
      "content",
      "html_block",
      "content",
    ])

    state = chatReducer(state, { type: "chunk_end" })
    expect(state.streamingMessage).toBeNull()
    expect(state.messages[0]!.blocks.map((b) => b.type)).toEqual([
      "content",
      "html_block",
      "content",
    ])

    const { container } = renderMessages(state.messages)
    expect(container.querySelector(".island")).not.toBeNull()
    expect(container.textContent).toContain("Mid-stream island")

    const text = container.textContent ?? ""
    expect(text.indexOf("Before the island.")).toBeLessThan(
      text.indexOf("Mid-stream island"),
    )
    expect(text.indexOf("Mid-stream island")).toBeLessThan(
      text.indexOf("After the island."),
    )
  })

  it("does not disturb thinking-tag/fence stream state", () => {
    let state = startStream(makeState())
    // Open a code fence, then insert an html_block: the fence state survives.
    state = chatReducer(state, {
      type: "chunk",
      content: "```\nsome code",
      operation: "append",
    })
    expect(state.streamingMessage!.insideFence).toBe(true)

    state = chatReducer(state, {
      type: "block_insert",
      block: htmlBlock(),
    })
    // The block is opaque to the fence state machine.
    expect(state.streamingMessage!.insideFence).toBe(true)
    expect(state.streamingMessage!.blocks.map((b) => b.type)).toEqual([
      "content",
      "html_block",
    ])
  })

  it("merges block-level deps into the streaming message htmlDeps", () => {
    const dep = fakeDep("island-dep")
    let state = startStream(makeState())
    state = chatReducer(state, {
      type: "block_insert",
      block: htmlBlock({ html_deps: [dep] }),
    })

    expect(state.streamingMessage!.htmlDeps).toEqual([dep])

    state = chatReducer(state, { type: "chunk_end" })
    expect(state.messages[0]!.htmlDeps).toEqual([dep])
  })

  it("ignores html_block with unsupported version with a warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    let state = startStream(makeState())
    state = chatReducer(state, {
      type: "block_insert",
      block: { ...htmlBlock(), version: 2 } as unknown as StructuredBlock,
    })

    expect(state.streamingMessage!.blocks).toHaveLength(0)
    expect(warn).toHaveBeenCalledTimes(1)
  })
})

describe("html_block deps-before-innerHTML ordering", () => {
  it("renders dependencies before mounting innerHTML", async () => {
    const shiny = mockShiny()
    const dep = fakeDep("island-dep")
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [htmlBlock({ html_deps: [dep] })],
      },
    })

    const { container } = render(
      <ShinyLifecycleContext.Provider value={shiny}>
        <ChatMessages messages={state.messages} inputId="test-input" />
      </ShinyLifecycleContext.Provider>,
    )

    // While deps are pending, the island's innerHTML is NOT mounted.
    // The HtmlBlockContent component returns null until depsReady.
    expect(container.querySelector(".island")).toBeNull()
    expect(shiny.renderDependencies).toHaveBeenCalledWith([dep])

    // After deps resolve, the innerHTML mounts and Shiny binds it.
    // The renderDependencies mock resolves on the next microtask; flush it
    // so the component's useEffect callback runs and setDepsReady(true)
    // re-renders with the island mounted.
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(container.querySelector(".island")).not.toBeNull()
    expect(shiny.bindAll).toHaveBeenCalled()
  })

  it("mounts innerHTML immediately when no deps", () => {
    const shiny = mockShiny()
    const state = chatReducer(makeState(), {
      type: "message",
      message: {
        role: "assistant",
        segments: [htmlBlock({ content: "<p class='island'>No deps</p>" })],
      },
    })

    const { container } = render(
      <ShinyLifecycleContext.Provider value={shiny}>
        <ChatMessages messages={state.messages} inputId="test-input" />
      </ShinyLifecycleContext.Provider>,
    )

    // No deps → no deferred render; innerHTML is mounted immediately.
    expect(container.querySelector(".island")).not.toBeNull()
    expect(shiny.renderDependencies).not.toHaveBeenCalled()
    expect(shiny.bindAll).toHaveBeenCalled()
  })
})
