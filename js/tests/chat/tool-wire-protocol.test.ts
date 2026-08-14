import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"
import { parseToolEvents, type ToolEvent } from "../../src/chat/tool-protocol"

interface WireFixture {
  request: string
  result: string
  expected: {
    request: Record<string, unknown>
    result: Record<string, unknown>
  }
}

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../..")
const fixturePaths = [
  [
    "R",
    resolve(repoRoot, "pkg-r/tests/testthat/fixtures/tool-wire-protocol.json"),
  ],
  [
    "Python",
    resolve(repoRoot, "pkg-py/tests/fixtures/tool-wire-protocol.json"),
  ],
] as const

function readFixture(path: string): WireFixture {
  return JSON.parse(readFileSync(path, "utf8")) as WireFixture
}

function withoutOffsets(event: ToolEvent): Record<string, unknown> {
  const { start: _start, end: _end, ...withoutOffsets } = event
  return withoutOffsets
}

const fixtures = fixturePaths.map(([language, path]) => ({
  language,
  fixture: readFixture(path),
}))

const resultOnlyFields = [
  "title",
  "icon",
  "status",
  "label",
  "valuePreview",
  "value",
  "valueType",
  "requestCall",
  "showRequest",
  "fullScreen",
  "expanded",
  "customDisplay",
  "footer",
]

describe("tool wire protocol fixtures", () => {
  it("gives R and Python the same semantic contract", () => {
    expect(fixtures[1]!.fixture.expected).toEqual(fixtures[0]!.fixture.expected)
  })

  for (const { language, fixture } of fixtures) {
    it(`matches the canonical ${language} request and result`, () => {
      const requestEvents = parseToolEvents(fixture.request, "html")
      const resultEvents = parseToolEvents(fixture.result, "html")
      expect(requestEvents).toHaveLength(1)
      expect(resultEvents).toHaveLength(1)
      const [request] = requestEvents
      const [result] = resultEvents

      expect(request).toBeDefined()
      expect(result).toBeDefined()
      expect(withoutOffsets(request!)).toEqual(fixture.expected.request)
      expect(withoutOffsets(result!)).toEqual(fixture.expected.result)

      for (const field of resultOnlyFields) {
        expect(request).not.toHaveProperty(field)
      }
    })
  }
})
