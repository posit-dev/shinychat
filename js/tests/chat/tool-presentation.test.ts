import { describe, expect, it } from "vitest"
import {
  deriveToolGroupIdentity,
  type ToolCallGroup,
  type ToolCallItem,
} from "../../src/chat/tool-model"
import { projectToolGroup } from "../../src/chat/tool-presentation"
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
