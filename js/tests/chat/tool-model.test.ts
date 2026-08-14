import { describe, expect, it } from "vitest"
import {
  deriveToolGroupIdentity,
  pairToolEvents,
} from "../../src/chat/tool-model"
import { parseToolEvents } from "../../src/chat/tool-protocol"

const request = (id: string, title: string) =>
  `<shiny-tool-request request-id="${id}" tool-name="search" tool-title="${title}"></shiny-tool-request>`
const result = (id: string, title: string) =>
  `<shiny-tool-result request-id="${id}" tool-name="search" status="success" tool-title="${title}"></shiny-tool-result>`

describe("tool lifecycle model", () => {
  it("pairs request and result elements into one settled call", () => {
    const events = parseToolEvents(
      request("r1", "Searching") + result("r1", "Searched"),
      "markdown",
    )
    const calls = pairToolEvents(events, "0:0", 0)

    expect(calls).toHaveLength(1)
    expect(calls[0]).toMatchObject({
      requestId: "r1",
      localId: "r1",
      status: "success",
      definitionTitle: "Searching",
      title: "Searched",
    })
  })

  it("gives missing request ids stable loop-local identities", () => {
    const events = parseToolEvents(
      '<shiny-tool-result tool-name="search" status="success"></shiny-tool-result>'.repeat(
        2,
      ),
      "markdown",
    )
    const calls = pairToolEvents(events, "2:10", 2)

    expect(calls.map((call) => call.requestId)).toEqual(["", ""])
    expect(calls.map((call) => call.localId)).toEqual([
      "__anon-2:10-0",
      "__anon-2:10-1",
    ])
  })

  it("resolves dynamic identity for a lone call and static identity for groups", () => {
    const events = parseToolEvents(
      request("r1", "Searching") +
        result("r1", "Searched") +
        request("r2", "Searching") +
        result("r2", "Searched again"),
      "markdown",
    )
    const calls = pairToolEvents(events, "0:0", 0)

    expect(deriveToolGroupIdentity([calls[0]!])).toMatchObject({
      title: "Searched",
      titleSettled: true,
      count: 1,
    })
    expect(deriveToolGroupIdentity(calls)).toMatchObject({
      title: "Searching",
      titleSettled: true,
      count: 2,
    })
  })
})
