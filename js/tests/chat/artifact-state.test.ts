import { describe, expect, it } from "vitest"
import {
  chatReducer,
  initialState,
  type ChatArtifactState,
} from "../../src/chat/state"
import type { ChatAction, HtmlDep } from "../../src/transport/types"

const firstDep: HtmlDep = { name: "first", version: "1.0.0" }
const secondDep: HtmlDep = { name: "second", version: "2.0.0" }

function artifact(
  overrides: Partial<ChatArtifactState> = {},
): ChatArtifactState {
  return { ...initialState.artifact, enabled: true, ...overrides }
}

function stateWithArtifact(overrides: Partial<ChatArtifactState> = {}) {
  return { ...initialState, artifact: artifact(overrides) }
}

describe("artifact state", () => {
  it("defaults to a disabled, hidden, resizable 400px artifact", () => {
    expect(initialState.artifact).toEqual({
      enabled: false,
      visible: false,
      title: null,
      content: "",
      htmlDeps: [],
      width: "400px",
      resizable: true,
    })
  })

  it.each<ChatAction>([
    { type: "artifact_show", content: "<p>Ignored</p>", title: "Ignored" },
    { type: "artifact_hide" },
    { type: "artifact_toggle" },
    { type: "artifact_update", content: "<p>Ignored</p>", title: "Ignored" },
  ])("ignores $type while artifact support is disabled", (action) => {
    expect(chatReducer(initialState, action)).toBe(initialState)
  })

  it("show atomically replaces supplied content, title, and dependencies before revealing", () => {
    const next = chatReducer(stateWithArtifact(), {
      type: "artifact_show",
      content: "<article>Preview</article>",
      title: "Preview",
      html_deps: [firstDep],
    })

    expect(next.artifact).toEqual(
      artifact({
        visible: true,
        title: "Preview",
        content: "<article>Preview</article>",
        htmlDeps: [firstDep],
      }),
    )
  })

  it("show preserves omitted content, title, and dependencies", () => {
    const before = stateWithArtifact({
      title: "Existing",
      content: "<p>Existing</p>",
      htmlDeps: [firstDep],
    })
    const next = chatReducer(before, { type: "artifact_show" })

    expect(next.artifact).toEqual({ ...before.artifact, visible: true })
  })

  it("update works before show and leaves visibility unchanged", () => {
    const next = chatReducer(stateWithArtifact(), {
      type: "artifact_update",
      content: "<p>Prepared</p>",
      title: "Prepared",
      html_deps: [firstDep],
    })

    expect(next.artifact).toEqual(
      artifact({
        title: "Prepared",
        content: "<p>Prepared</p>",
        htmlDeps: [firstDep],
      }),
    )
    expect(next.artifact.visible).toBe(false)
  })

  it("updates only supplied fields and preserves visibility", () => {
    const before = stateWithArtifact({
      visible: true,
      title: "Before",
      content: "<p>Before</p>",
      htmlDeps: [firstDep],
    })
    const next = chatReducer(before, {
      type: "artifact_update",
      title: "After",
    })

    expect(next.artifact).toEqual(
      artifact({
        visible: true,
        title: "After",
        content: "<p>Before</p>",
        htmlDeps: [firstDep],
      }),
    )
  })

  it("replaces dependencies whenever supplied content is replaced", () => {
    const before = stateWithArtifact({
      content: "<p>Before</p>",
      htmlDeps: [firstDep],
    })
    const next = chatReducer(before, {
      type: "artifact_update",
      content: "<p>After</p>",
      html_deps: [secondDep],
    })

    expect(next.artifact.content).toBe("<p>After</p>")
    expect(next.artifact.htmlDeps).toEqual([secondDep])
  })

  it("clears content and dependencies with content='', and normalizes title='' to null", () => {
    const before = stateWithArtifact({
      title: "Before",
      content: "<p>Before</p>",
      htmlDeps: [firstDep],
    })
    const next = chatReducer(before, {
      type: "artifact_update",
      content: "",
      title: "",
    })

    expect(next.artifact.content).toBe("")
    expect(next.artifact.htmlDeps).toEqual([])
    expect(next.artifact.title).toBeNull()
  })

  it("hide and toggle change only visibility", () => {
    const before = stateWithArtifact({
      visible: true,
      title: "Preview",
      content: "<p>Preview</p>",
      htmlDeps: [firstDep],
    })
    const hidden = chatReducer(before, { type: "artifact_hide" })
    const toggled = chatReducer(hidden, { type: "artifact_toggle" })

    expect(hidden.artifact).toEqual({ ...before.artifact, visible: false })
    expect(toggled.artifact).toEqual(before.artifact)
  })
})
