import { describe, expect, it } from "vitest"
import {
  chatReducer,
  initialState,
  type ChatDrawerState,
} from "../../src/chat/state"
import type { ChatAction, HtmlDep } from "../../src/transport/types"

const firstDep: HtmlDep = { name: "first", version: "1.0.0" }
const secondDep: HtmlDep = { name: "second", version: "2.0.0" }

function artifact(overrides: Partial<ChatDrawerState> = {}): ChatDrawerState {
  return { ...initialState.drawer, enabled: true, ...overrides }
}

function stateWithDrawer(overrides: Partial<ChatDrawerState> = {}) {
  return { ...initialState, drawer: artifact(overrides) }
}

describe("artifact state", () => {
  it("defaults to a disabled, hidden, resizable 400px artifact", () => {
    expect(initialState.drawer).toEqual({
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
    { type: "drawer_show", content: "<p>Ignored</p>", title: "Ignored" },
    { type: "drawer_hide" },
    { type: "drawer_toggle" },
    { type: "drawer_update", content: "<p>Ignored</p>", title: "Ignored" },
  ])("ignores $type while artifact support is disabled", (action) => {
    expect(chatReducer(initialState, action)).toBe(initialState)
  })

  it("show atomically replaces supplied content, title, and dependencies before revealing", () => {
    const next = chatReducer(stateWithDrawer(), {
      type: "drawer_show",
      content: "<article>Preview</article>",
      title: "Preview",
      html_deps: [firstDep],
    })

    expect(next.drawer).toEqual(
      artifact({
        visible: true,
        title: "Preview",
        content: "<article>Preview</article>",
        htmlDeps: [firstDep],
      }),
    )
  })

  it("show preserves omitted content, title, and dependencies", () => {
    const before = stateWithDrawer({
      title: "Existing",
      content: "<p>Existing</p>",
      htmlDeps: [firstDep],
    })
    const next = chatReducer(before, { type: "drawer_show" })

    expect(next.drawer).toEqual({ ...before.drawer, visible: true })
  })

  it("update works before show and leaves visibility unchanged", () => {
    const next = chatReducer(stateWithDrawer(), {
      type: "drawer_update",
      content: "<p>Prepared</p>",
      title: "Prepared",
      html_deps: [firstDep],
    })

    expect(next.drawer).toEqual(
      artifact({
        title: "Prepared",
        content: "<p>Prepared</p>",
        htmlDeps: [firstDep],
      }),
    )
    expect(next.drawer.visible).toBe(false)
  })

  it("updates only supplied fields and preserves visibility", () => {
    const before = stateWithDrawer({
      visible: true,
      title: "Before",
      content: "<p>Before</p>",
      htmlDeps: [firstDep],
    })
    const next = chatReducer(before, {
      type: "drawer_update",
      title: "After",
    })

    expect(next.drawer).toEqual(
      artifact({
        visible: true,
        title: "After",
        content: "<p>Before</p>",
        htmlDeps: [firstDep],
      }),
    )
  })

  it("replaces dependencies whenever supplied content is replaced", () => {
    const before = stateWithDrawer({
      content: "<p>Before</p>",
      htmlDeps: [firstDep],
    })
    const next = chatReducer(before, {
      type: "drawer_update",
      content: "<p>After</p>",
      html_deps: [secondDep],
    })

    expect(next.drawer.content).toBe("<p>After</p>")
    expect(next.drawer.htmlDeps).toEqual([secondDep])
  })

  it("clears content and dependencies with content='', and normalizes title='' to null", () => {
    const before = stateWithDrawer({
      title: "Before",
      content: "<p>Before</p>",
      htmlDeps: [firstDep],
    })
    const next = chatReducer(before, {
      type: "drawer_update",
      content: "",
      title: "",
    })

    expect(next.drawer.content).toBe("")
    expect(next.drawer.htmlDeps).toEqual([])
    expect(next.drawer.title).toBeNull()
  })

  it("hide and toggle change only visibility", () => {
    const before = stateWithDrawer({
      visible: true,
      title: "Preview",
      content: "<p>Preview</p>",
      htmlDeps: [firstDep],
    })
    const hidden = chatReducer(before, { type: "drawer_hide" })
    const toggled = chatReducer(hidden, { type: "drawer_toggle" })

    expect(hidden.drawer).toEqual({ ...before.drawer, visible: false })
    expect(toggled.drawer).toEqual(before.drawer)
  })
})
