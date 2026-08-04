import { describe, expect, it } from "vitest"
import {
  deriveToolGroupIdentity,
  type ToolCallGroup,
  type ToolCallItem,
  type ToolCallSegment,
} from "../../src/chat/tool-model"
import {
  projectToolGroup,
  toolArgumentPreview,
  toolCallGlyph,
  toolCallLabel,
  toolGroupGlyph,
  toolHeaderSegments,
  toolSegmentName,
  toolSegmentNameKey,
} from "../../src/chat/tool-presentation"
import {
  supersededRequestIds,
  type ChatMessageData,
} from "../../src/chat/state"

function call(partial: Partial<ToolCallItem> = {}): ToolCallItem {
  return {
    requestId: "request-1",
    localId: "request-1",
    toolName: "weather",
    status: "success",
    ...partial,
  }
}

function group(calls: ToolCallItem[]): ToolCallGroup {
  const identity = deriveToolGroupIdentity(calls)
  return {
    key: "all",
    toolName: calls[0]?.toolName ?? "",
    calls,
    ...identity,
  }
}

function segment(
  partial: Partial<ToolCallSegment> & { toolName: string },
): ToolCallSegment {
  return {
    count: 1,
    settled: true,
    ...partial,
  }
}

describe("tool presentation projection", () => {
  it("keeps ordinary lifecycle calls in an activity row", () => {
    const first = call({
      requestId: "first",
      localId: "first",
      definitionTitle: "Forecast",
      status: "success",
    })
    const second = call({
      requestId: "second",
      localId: "second",
      definitionTitle: "Forecast",
      status: "error",
    })

    const presentation = projectToolGroup(group([first, second]))

    expect(presentation.standalonePayloads).toEqual([])
    expect(presentation.row).toMatchObject({
      calls: [first, second],
      single: null,
      anyRunning: false,
      failedCount: 1,
      heterogeneous: false,
      hasExpandedCall: false,
      identity: {
        title: "Forecast",
        count: 2,
        segments: [
          {
            toolName: "weather",
            title: "Forecast",
            count: 2,
            settled: true,
          },
        ],
      },
    })
  })

  it("keeps a running custom-display request in the activity row", () => {
    const running = call({
      status: "running",
      customDisplay: true,
      expanded: true,
    })

    const presentation = projectToolGroup(group([running]))

    expect(presentation.standalonePayloads).toEqual([])
    expect(presentation.row).toMatchObject({
      calls: [running],
      single: running,
      anyRunning: true,
      hasExpandedCall: true,
    })
  })

  it("moves a settled custom-display result into a standalone payload", () => {
    const custom = call({
      customDisplay: true,
      value: "<p>Portland</p>",
      valueType: "html",
    })

    const presentation = projectToolGroup(group([custom]))

    expect(presentation.row).toBeNull()
    expect(presentation.standalonePayloads).toEqual([
      {
        key: "request-1",
        call: custom,
        value: "<p>Portland</p>",
        valueType: "html",
        showRequest: false,
      },
    ])
  })

  it("derives mixed-row identity and segments only from calls that stay in the row", () => {
    const migrated = call({
      requestId: "query",
      localId: "query",
      toolName: "query",
      customDisplay: true,
      status: "success",
      value: "<table></table>",
      resolveBlock: 0,
      resolveIndex: 2,
    })
    const failed = call({
      requestId: "weather",
      localId: "weather",
      toolName: "weather",
      definitionTitle: "Weather",
      status: "error",
    })
    const running = call({
      requestId: "lookup",
      localId: "lookup",
      toolName: "lookup",
      status: "running",
    })

    const presentation = projectToolGroup(group([migrated, failed, running]))

    expect(presentation.row).toMatchObject({
      calls: [failed, running],
      identity: {
        count: 2,
        segments: [
          { toolName: "weather", count: 1 },
          { toolName: "lookup", count: 1 },
        ],
      },
      failedCount: 1,
      anyRunning: true,
      heterogeneous: true,
    })
    expect(presentation.row!.segmentTitles.get("weather")).toBe("Weather")
    expect(presentation.row!.segmentTitles.has("query")).toBe(false)
  })

  it("returns no row when every call has migrated", () => {
    const first = call({
      requestId: "first",
      localId: "first",
      customDisplay: true,
      value: "first",
    })
    const second = call({
      requestId: "second",
      localId: "second",
      customDisplay: true,
      value: "second",
    })

    const presentation = projectToolGroup(group([first, second]))

    expect(presentation.row).toBeNull()
    expect(
      presentation.standalonePayloads.map((payload) => payload.key),
    ).toEqual(["first", "second"])
  })

  it("orders standalone payloads by source block, then result offset", () => {
    const laterBlock = call({
      requestId: "later-block",
      localId: "later-block",
      customDisplay: true,
      value: "later block",
      resolveBlock: 1,
      resolveIndex: 5,
    })
    const firstBlockLate = call({
      requestId: "first-block-late",
      localId: "first-block-late",
      customDisplay: true,
      value: "first block late",
      resolveBlock: 0,
      resolveIndex: 300,
    })
    const firstBlockEarly = call({
      requestId: "first-block-early",
      localId: "first-block-early",
      customDisplay: true,
      value: "first block early",
      resolveBlock: 0,
      resolveIndex: 20,
    })

    const presentation = projectToolGroup(
      group([laterBlock, firstBlockLate, firstBlockEarly]),
    )

    expect(
      presentation.standalonePayloads.map((payload) => payload.value),
    ).toEqual(["first block early", "first block late", "later block"])
  })

  it("does not mutate lifecycle calls while projecting their placement", () => {
    const migrated = call({
      requestId: "migrated",
      localId: "migrated",
      customDisplay: true,
      value: "custom",
      resolveBlock: 0,
      resolveIndex: 20,
    })
    const running = call({
      requestId: "running",
      localId: "running",
      status: "running",
    })
    const source = group([migrated, running])
    const originalCalls = [...source.calls]
    Object.freeze(source.calls)
    Object.freeze(source)

    const presentation = projectToolGroup(source)

    expect(source.calls).toEqual(originalCalls)
    expect(source.calls).toEqual([migrated, running])
    expect(presentation.row!.calls).toEqual([running])
  })

  it("leaves settled custom calls available to transcript supersession", () => {
    const custom = call({
      requestId: "settled-custom",
      localId: "settled-custom",
      customDisplay: true,
      value: "custom",
    })
    const lifecycleGroup = group([custom])
    const message: ChatMessageData = {
      id: "message",
      role: "assistant",
      content: "",
      streaming: false,
      blocks: [
        {
          type: "tool_loop",
          content: "",
          contentType: "markdown",
          grouping: "tool",
          groups: [lifecycleGroup],
        },
      ],
    }

    const presentation = projectToolGroup(lifecycleGroup)

    expect(presentation.row).toBeNull()
    expect(lifecycleGroup.calls).toEqual([custom])
    expect(supersededRequestIds([message], null)).toEqual(
      new Set(["settled-custom"]),
    )
  })
})

describe("tool presentation policy", () => {
  it("rejects invalid and non-object argument JSON previews", () => {
    for (const argumentsJson of [
      undefined,
      "",
      "not json",
      "null",
      '"scalar"',
      "42",
      "false",
    ]) {
      expect(toolArgumentPreview(argumentsJson)).toBeNull()
    }
  })

  it("keeps only the first three public scalar arguments", () => {
    expect(
      toolArgumentPreview(
        '{"_intent":"hidden",".internal":true,"query":"glucose","page":2,"exact":false,"ignored":"later","nested":{"value":1}}',
      ),
    ).toBe("query: glucose, page: 2, exact: false")
  })

  it("truncates a complete argument preview to the compact row budget", () => {
    expect(
      toolArgumentPreview(
        '{"query":"0123456789012345678901234567890123456789"}',
      ),
    ).toBe("query: 01234567890123456789012345678901…")
  })

  it("chooses labels differently for single and multi-call rows", () => {
    const callWithLabel = call({ label: "Portland" })
    const titled = call({
      title: "Weather Forecast for Portland",
      arguments: '{"city":"Portland"}',
    })
    const bare = call({ toolName: "run_sql", arguments: "{}" })

    expect(toolCallLabel(callWithLabel, "Weather", false)).toEqual({
      text: "Portland",
    })
    expect(toolCallLabel(titled, "Weather Forecast", false)).toEqual({
      text: "Weather Forecast for Portland",
    })
    expect(
      toolCallLabel(titled, "Weather Forecast for Portland", false),
    ).toEqual({ text: "city: Portland", code: true })
    expect(
      toolCallLabel(titled, "Weather Forecast for Portland", true),
    ).toBeNull()
    expect(toolCallLabel(bare, undefined, false)).toEqual({
      text: "run_sql",
      code: true,
    })
    expect(toolCallLabel(bare, undefined, true)).toBeNull()
  })

  it("uses a dynamic title only when its own segment does not already show it", () => {
    const callWithTitle = call({
      toolName: "read_page",
      title: "Read page: docs",
      arguments: "{}",
    })

    expect(toolCallLabel(callWithTitle, "Read page", false)).toEqual({
      text: "Read page: docs",
    })
    expect(
      toolCallLabel(
        { ...callWithTitle, title: "Read page" },
        "Read page",
        false,
      ),
    ).toEqual({ text: "read_page", code: true })
  })

  it("selects row glyph semantics with result-specific and running precedence", () => {
    const definitionIcon = '<svg class="definition"></svg>'
    const resultIcon = '<svg class="result"></svg>'

    expect(
      toolCallGlyph(
        call({ definitionIcon, icon: definitionIcon, status: "success" }),
        false,
      ),
    ).toEqual({ kind: "status", status: "success" })
    expect(
      toolCallGlyph(
        call({ definitionIcon, icon: definitionIcon, status: "error" }),
        true,
      ),
    ).toEqual({ kind: "icon", icon: definitionIcon })
    expect(
      toolCallGlyph(
        call({ definitionIcon, icon: resultIcon, status: "error" }),
        false,
      ),
    ).toEqual({ kind: "icon", icon: resultIcon })
    expect(
      toolCallGlyph(
        call({ definitionIcon, icon: resultIcon, status: "running" }),
        true,
      ),
    ).toEqual({ kind: "status", status: "running" })
    expect(toolCallGlyph(call({ status: "error" }), true)).toEqual({
      kind: "status",
      status: "error",
    })
  })

  it("selects only stable identity for group glyphs", () => {
    const homogeneous = projectToolGroup(
      group([call({ definitionIcon: "definition", icon: "definition" })]),
    ).row!
    const heterogeneous = projectToolGroup(
      group([
        call({ requestId: "one", localId: "one", toolName: "search" }),
        call({ requestId: "two", localId: "two", toolName: "read" }),
      ]),
    ).row!
    const running = projectToolGroup(
      group([
        call({ definitionIcon: "definition", icon: "definition" }),
        call({
          requestId: "running",
          localId: "running",
          status: "running",
        }),
      ]),
    ).row!

    expect(toolGroupGlyph(homogeneous)).toEqual({
      kind: "icon",
      icon: "definition",
    })
    expect(toolGroupGlyph(heterogeneous)).toEqual({ kind: "default" })
    expect(toolGroupGlyph(running)).toEqual({
      kind: "status",
      status: "running",
    })
  })

  it("projects whole header segments, verb placement, and overflow copy", () => {
    const visible = toolHeaderSegments([
      segment({
        toolName: "reconcile",
        title: "Reconciled the quarterly ledger against the general ledger",
      }),
      segment({ toolName: "notify", title: "Notified" }),
    ])
    const capped = toolHeaderSegments(
      ["Alpha", "Beta", "Gamma", "Delta"].map((title, i) =>
        segment({ toolName: `tool-${i}`, title }),
      ),
    )

    expect(visible.shown.map(({ segment }) => segment.toolName)).toEqual([
      "reconcile",
    ])
    expect(visible.shown[0]!.showVerb).toBe(true)
    expect(visible.overflowText).toBe(", and 1 other")
    expect(capped.shown.map(({ segment }) => segment.title)).toEqual([
      "Alpha",
      "Beta",
      "Gamma",
    ])
    expect(capped.shown.map(({ showVerb }) => showVerb)).toEqual([
      true,
      true,
      true,
    ])
    expect(capped.overflowText).toBe(", and 1 other")

    const untitled = toolHeaderSegments([
      segment({ toolName: "search", settled: true }),
      segment({ toolName: "read", settled: false }),
    ])
    expect(untitled.shown.map(({ showVerb }) => showVerb)).toEqual([
      true,
      false,
    ])
  })

  it("uses one leading verb for untitled segments and stable title keys", () => {
    const first = segment({ toolName: "search", settled: true })
    const second = segment({ toolName: "read", settled: false })
    const title = segment({ toolName: "weather", title: "Weather" })

    const firstName = toolSegmentName(first, true)
    expect(firstName).toEqual({
      toolName: "search",
      verb: "Used ",
      title: undefined,
    })
    expect(toolSegmentName(second, false)).toEqual({
      toolName: "read",
      verb: "",
      title: undefined,
    })
    expect(toolSegmentNameKey(firstName)).toBe("tool:Used |search")
    expect(toolSegmentNameKey(toolSegmentName(title, true))).toBe(
      "title:Weather",
    )
  })
})
