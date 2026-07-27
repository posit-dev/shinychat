import { describe, it, expect } from "vitest"
import { render, fireEvent } from "@testing-library/react"
import { ToolGroup } from "../../src/chat/ToolGroup"
import type { ToolCallGroup, ToolCallItem } from "../../src/chat/state"

function call(
  partial: Partial<ToolCallItem> & { requestId: string },
): ToolCallItem {
  return {
    toolName: "search",
    status: "success",
    ...partial,
  }
}

function group(
  partial: Partial<ToolCallGroup> & { calls: ToolCallItem[] },
): ToolCallGroup {
  const calls = partial.calls
  return {
    key: partial.key ?? "tool:search",
    toolName: partial.toolName ?? calls[0]!.toolName,
    title: partial.title,
    titleSettled: partial.titleSettled ?? true,
    icon: partial.icon,
    count: partial.count ?? calls.length,
    calls,
  }
}

describe("ToolGroup", () => {
  it("rests a single-call group as a Tier-1 row and morphs into the card on expand", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Ran R code",
          calls: [
            call({
              requestId: "a",
              value: "42",
              valueType: "text",
            }),
          ],
        })}
      />,
    )
    const row = container.querySelector(".shinychat-tool-group__row")
    expect(row).toBeTruthy()
    // At rest it's a quiet row, not a card, and carries no ×N badge.
    expect(container.querySelector(".shiny-tool-card")).toBeNull()
    expect(container.textContent).not.toContain("×")
    expect(row?.getAttribute("aria-expanded")).toBe("false")

    fireEvent.click(row as Element)
    expect(row?.getAttribute("aria-expanded")).toBe("true")
    expect(container.querySelector(".shiny-tool-card")).toBeTruthy()
  })

  it("shows a title: label colon form for a single call with a label", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Ran R code",
          calls: [
            call({
              requestId: "a",
              label: "fib.R",
              value: "ok",
              valueType: "text",
            }),
          ],
        })}
      />,
    )
    expect(
      container.querySelector(".shinychat-tool-group__title")?.textContent,
    ).toContain("Ran R code")
    expect(
      container.querySelector(".shinychat-tool-group__label")?.textContent,
    ).toContain("fib.R")
  })

  it("renders a multi-call group as a Tier-1 row with an ×N badge that expands to a Tier-2 list", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Searched",
          calls: [
            call({ requestId: "a", label: "glucose" }),
            call({ requestId: "b", label: "mannose" }),
          ],
        })}
      />,
    )
    const row = container.querySelector(".shinychat-tool-group__row")
    expect(row).toBeTruthy()
    expect(
      container.querySelector(".shinychat-tool-group__count")?.textContent,
    ).toBe("×2")
    expect(row?.getAttribute("aria-expanded")).toBe("false")

    // The call list is present but hidden until expanded.
    const list = container.querySelector(".shinychat-tool-group__calls")
    expect(list?.getAttribute("role")).toBe("list")
    expect((list as HTMLElement).hidden).toBe(true)

    fireEvent.click(row as Element)
    expect(row?.getAttribute("aria-expanded")).toBe("true")
    expect((list as HTMLElement).hidden).toBe(false)
    expect(container.querySelectorAll(".shinychat-tool-call-row").length).toBe(
      2,
    )
    expect(container.textContent).toContain("glucose")
    expect(container.textContent).toContain("mannose")
  })

  it("falls back to the tool name in code font when the group has no title", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          toolName: "run_sql",
          title: undefined,
          calls: [
            call({ requestId: "a", toolName: "run_sql" }),
            call({ requestId: "b", toolName: "run_sql" }),
          ],
        })}
      />,
    )
    const code = container.querySelector(".shinychat-tool-group__toolname")
    expect(code?.tagName).toBe("CODE")
    expect(code?.textContent).toBe("run_sql")
  })

  it("uses an argument preview as the per-call label fallback", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Searched",
          calls: [
            call({
              requestId: "a",
              arguments: '{"query":"insulin resistance"}',
            }),
            call({ requestId: "b", arguments: '{"query":"glucose"}' }),
          ],
        })}
      />,
    )
    fireEvent.click(
      container.querySelector(".shinychat-tool-group__row") as Element,
    )
    const labels = Array.from(
      container.querySelectorAll(".shinychat-tool-call-row__label code"),
    ).map((el) => el.textContent)
    expect(labels).toContain("insulin resistance")
  })

  it("shows a subtle 'N failed' note but no red on the resting group row", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Searched",
          calls: [
            call({ requestId: "a", label: "ok", status: "success" }),
            call({ requestId: "b", label: "bad", status: "error" }),
          ],
        })}
      />,
    )
    expect(
      container.querySelector(".shinychat-tool-group__failed")?.textContent,
    ).toBe("1 failed")
    // The resting glyph is not styled as an error.
    expect(
      container.querySelector(".shinychat-tool-group__glyph.text-danger"),
    ).toBeNull()
  })

  it("shows a spinner glyph while any call in the group is running", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Searching",
          titleSettled: false,
          calls: [
            call({ requestId: "a", status: "success", label: "one" }),
            call({ requestId: "b", status: "running", label: "two" }),
          ],
        })}
      />,
    )
    expect(
      container.querySelector(".shinychat-tool-group__glyph .spinner-border"),
    ).toBeTruthy()
  })

  it("shows a subtle text 'failed' note (not just color/icon) on a resting single-call error row", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Ran R code",
          calls: [
            call({
              requestId: "a",
              status: "error",
              value: "boom",
              valueType: "text",
            }),
          ],
        })}
      />,
    )
    expect(
      container.querySelector(".shinychat-tool-group__failed")?.textContent,
    ).toBe("failed")
    // The resting glyph stays the muted identity glyph, not a red error icon.
    expect(
      container.querySelector(".shinychat-tool-group__glyph.text-danger"),
    ).toBeNull()
  })

  it("gives the single-call running spinner a visually-hidden 'Running…' label", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Running R code",
          titleSettled: false,
          calls: [
            call({
              requestId: "a",
              status: "running",
              title: "Running R code",
            }),
          ],
        })}
      />,
    )
    const hidden = container.querySelector(
      ".shinychat-tool-group__glyph .visually-hidden",
    )
    expect(hidden?.textContent).toBe("Running…")
    // The visible title text has no "Running " prefix wrapper baked in by us;
    // it's whatever the server-provided title says.
    expect(
      container.querySelector(".shinychat-tool-group__title")?.textContent,
    ).toBe("Running R code")
  })

  it("does not render a label for a call with neither an explicit label nor a scalar argument", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Searched",
          calls: [
            call({ requestId: "a", arguments: '{"nested":{"a":1}}' }),
            call({ requestId: "b", arguments: "{}" }),
          ],
        })}
      />,
    )
    fireEvent.click(
      container.querySelector(".shinychat-tool-group__row") as Element,
    )
    expect(
      container.querySelector(".shinychat-tool-call-row__label"),
    ).toBeNull()
  })
})
