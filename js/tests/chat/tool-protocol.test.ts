import { describe, expect, it } from "vitest"
import {
  isRoutableContentType,
  parseToolEvents,
  type ToolRequestEvent,
  type ToolResultEvent,
} from "../../src/chat/tool-protocol"

const request = (attributes = "") =>
  `<shiny-tool-request ${attributes}></shiny-tool-request>`
const result = (attributes = "") =>
  `<shiny-tool-result ${attributes}></shiny-tool-result>`

describe("tool protocol", () => {
  it("normalizes request events into typed camelCase fields", () => {
    const content = request(
      'request-id="r1" tool-name="search" tool-title="Search" icon="magnify" grouping="all" intent="" arguments="{&quot;q&quot;:&quot;hi&quot;}"',
    )
    const [event] = parseToolEvents(content, "markdown")

    expect(event).toEqual({
      kind: "request",
      requestId: "r1",
      toolName: "search",
      definitionTitle: "Search",
      definitionIcon: "magnify",
      grouping: "all",
      intent: "",
      arguments: '{"q":"hi"}',
      start: 0,
      end: content.length,
    } satisfies ToolRequestEvent)
  })

  it("normalizes result payloads and preserves empty present values", () => {
    const content = result(
      'request-id="r1" tool-name="search" tool-title="Done" icon="check" label="" value-preview="" value="" value-type="text" request-call="" footer="" show-request full-screen expanded custom-display',
    )
    const [event] = parseToolEvents(content, "markdown")

    expect(event).toEqual({
      kind: "result",
      requestId: "r1",
      toolName: "search",
      title: "Done",
      icon: "check",
      status: "success",
      label: "",
      valuePreview: "",
      value: "",
      valueType: "text",
      requestCall: "",
      showRequest: true,
      fullScreen: true,
      presentation: "default",
      expanded: true,
      customDisplay: true,
      footer: "",
      start: 0,
      end: content.length,
    } satisfies ToolResultEvent)
  })

  it("omits invalid grouping and applies status fallback", () => {
    const [invalidGrouping, absentStatus, otherStatus] = parseToolEvents(
      result('grouping="sometimes"') +
        result('request-id="r2"') +
        result('request-id="r3" status="pending"'),
      "markdown",
    )

    expect(invalidGrouping).not.toHaveProperty("grouping")
    expect(invalidGrouping).toMatchObject({
      kind: "result",
      status: "success",
    })
    expect(absentStatus).toMatchObject({ status: "success" })
    expect(otherStatus).toMatchObject({ status: "success" })
  })

  it("normalizes result presentation to framed or default", () => {
    const [framed, absent, invalid] = [
      parseToolEvents(result('presentation="framed"'), "markdown")[0],
      parseToolEvents(result(), "markdown")[0],
      parseToolEvents(result('presentation="panel"'), "markdown")[0],
    ]

    expect(framed).toMatchObject({ kind: "result", presentation: "framed" })
    expect(absent).toMatchObject({
      kind: "result",
      presentation: "default",
    })
    expect(invalid).toMatchObject({
      kind: "result",
      presentation: "default",
    })
  })

  it('accepts only "" and "true" as true boolean values', () => {
    const [empty, explicitTrue, falseString, explicitFalse] = parseToolEvents(
      result("show-request full-screen expanded custom-display") +
        result(
          'show-request="true" full-screen="true" expanded="true" custom-display="true"',
        ) +
        result(
          'show-request="false" full-screen="1" expanded="yes" custom-display="FALSE"',
        ) +
        result(
          'show-request="false" full-screen="false" expanded="false" custom-display="false"',
        ),
      "markdown",
    )

    expect(empty).toMatchObject({
      showRequest: true,
      fullScreen: true,
      expanded: true,
      customDisplay: true,
    })
    expect(explicitTrue).toMatchObject({
      showRequest: true,
      fullScreen: true,
      expanded: true,
      customDisplay: true,
    })
    for (const event of [falseString, explicitFalse]) {
      expect(event).toMatchObject({
        showRequest: false,
        fullScreen: false,
        expanded: false,
        customDisplay: false,
      })
    }
  })

  it("decodes entities, including quoted values containing >", () => {
    const content = result(
      'request-id="r1" value="a&#10;b" icon="&lt;svg&gt;&lt;path d=&quot;M0&gt;L1&quot;/&gt;&lt;/svg&gt;"',
    )
    const [event] = parseToolEvents(content, "markdown")

    expect(event).toMatchObject({
      requestId: "r1",
      value: "a\nb",
      icon: '<svg><path d="M0>L1"/></svg>',
    })
  })

  it("leaves incomplete and fenced elements out of the event stream", () => {
    const incomplete =
      result('request-id="r1"') + '<shiny-tool-request request-id="r2" tool-'
    const fenced = `\`\`\`html\n${result('request-id="r3"')}\n\`\`\``
    const openFence = `Example:\n\n\`\`\`html\n${result('request-id="r4"')}`

    expect(parseToolEvents(incomplete, "markdown")).toHaveLength(1)
    expect(parseToolEvents(fenced, "markdown")).toEqual([])
    expect(parseToolEvents(openFence, "markdown", true)).toEqual([])
  })

  it("only opts markdown and html into tool routing", () => {
    expect(isRoutableContentType("markdown")).toBe(true)
    expect(isRoutableContentType("html")).toBe(true)
    expect(isRoutableContentType("text")).toBe(false)
  })
})
