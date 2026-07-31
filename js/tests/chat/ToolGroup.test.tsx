import { describe, it, expect, vi } from "vitest"
import { render, fireEvent, act } from "@testing-library/react"
import { ToolGroup } from "../../src/chat/ToolGroup"
import type { ToolCallGroup, ToolCallItem } from "../../src/chat/state"

function call(
  partial: Partial<ToolCallItem> & { requestId: string },
): ToolCallItem {
  return {
    toolName: "search",
    status: "success",
    localId: partial.requestId,
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
    // A homogeneous group is one segment carrying the group's own identity,
    // which is what `groupCalls` builds for every non-"all" bucket.
    segments: partial.segments ?? [
      {
        toolName: partial.toolName ?? calls[0]!.toolName,
        title: partial.title,
        count: calls.length,
        settled: partial.titleSettled ?? true,
      },
    ],
  }
}

// The header row's visible text, minus the glyph (whose spinner carries a
// visually-hidden "Running…" label).
function headerText(container: HTMLElement): string {
  const row = container
    .querySelector(".shinychat-tool-group__row")!
    .cloneNode(true) as HTMLElement
  row.querySelector(".shinychat-tool-group__glyph")?.remove()
  return row.textContent ?? ""
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

  it("surfaces a single call's intent only on drill-in (expanded row)", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Rendered plot",
          calls: [
            call({
              requestId: "a",
              intent: "Visualize the trend",
              value: "chart",
              valueType: "text",
            }),
          ],
        })}
      />,
    )
    // Intent is hidden while the row is at rest.
    expect(container.querySelector(".shinychat-tool-row__intent")).toBeNull()
    fireEvent.click(
      container.querySelector(".shinychat-tool-group__row") as Element,
    )
    expect(
      container.querySelector(".shinychat-tool-row__intent")?.textContent,
    ).toBe("Visualize the trend")
  })

  it("peeks at a call's value on the resting row, single and grouped alike", () => {
    // The preview rides the header on a single-call row (there is no Tier-2 row
    // to carry it) and each call's own row once the group has several.
    const { container, rerender } = render(
      <ToolGroup
        group={group({
          title: "Queried",
          calls: [call({ requestId: "a", valuePreview: "1,204 rows" })],
        })}
      />,
    )
    const previews = () =>
      [...container.querySelectorAll(".shinychat-tool-call-row__preview")].map(
        (el) => el.textContent,
      )
    expect(previews()).toEqual(["1,204 rows"])

    rerender(
      <ToolGroup
        group={group({
          title: "Queried",
          calls: [
            call({ requestId: "a", valuePreview: "1,204 rows" }),
            call({ requestId: "b", valuePreview: "17 rows" }),
          ],
        })}
      />,
    )
    // The group header itself stays clean — the peeks moved down to the rows.
    expect(
      container.querySelector(
        ".shinychat-tool-group__row .shinychat-tool-call-row__preview",
      ),
    ).toBeNull()
    expect(previews()).toEqual(["1,204 rows", "17 rows"])
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

  it("names every tool with its own count in a heterogeneous group header", () => {
    // A loop-wide ("all") group can hold several tools; wearing one tool's
    // title would misrepresent what ran, so each tool shows the title it would
    // show on its own.
    const { container } = render(
      <ToolGroup
        group={group({
          key: "all",
          toolName: "search_web",
          title: "Searched the web",
          calls: [
            call({ requestId: "a", toolName: "search_web" }),
            call({ requestId: "b", toolName: "search_web" }),
            call({ requestId: "c", toolName: "read_page" }),
            call({ requestId: "d", toolName: "read_page" }),
            call({ requestId: "e", toolName: "read_page" }),
          ],
          segments: [
            {
              toolName: "search_web",
              title: "Searched the web",
              count: 2,
              settled: true,
            },
            {
              toolName: "read_page",
              title: "Read page",
              count: 3,
              settled: true,
            },
          ],
        })}
      />,
    )
    expect(
      Array.from(
        container.querySelectorAll(".shinychat-tool-group__title"),
      ).map((el) => el.textContent),
    ).toEqual(["Searched the web", "Read page"])
    expect(
      Array.from(
        container.querySelectorAll(".shinychat-tool-group__count"),
      ).map((el) => el.textContent),
    ).toEqual(["×2", "×3"])
    // Each count sits with its own tool, and the segments read as one list.
    expect(headerText(container)).toBe("Searched the web×2, Read page×3")
  })

  it("collapses the segments that don't fit into 'and N others'", () => {
    // Five single-call loops merging into one "all" group used to render every
    // segment independently ellipsized ("Net revenue, last fo…, Exported th…,
    // Emailed the s…"), which is illegible. Whole segments are shown until the
    // character budget is spent; the rest are named by count.
    const titles = [
      "Net revenue, last four quarters",
      "Exported the report",
      "Emailed the summary",
      "Scorecard for Q3",
      "Summarized the findings",
    ]
    const { container } = render(
      <ToolGroup
        group={group({
          key: "all",
          calls: titles.map((_, i) =>
            call({ requestId: `c${i}`, toolName: `t${i}` }),
          ),
          segments: titles.map((title, i) => ({
            toolName: `t${i}`,
            title,
            count: 1,
            settled: true,
          })),
        })}
      />,
    )
    expect(headerText(container)).toBe(
      "Net revenue, last four quarters, Exported the report, and 3 others",
    )
    // The folded titles are gone from the DOM, not merely clipped by CSS.
    expect(container.textContent).not.toContain("Emailed the summary")
  })

  it("says 'other', not 'others', when a single segment is folded away", () => {
    // Four short titles all fit the character budget, so this is the segment
    // cap doing the folding rather than the budget.
    const titles = ["Alpha", "Beta", "Gamma", "Delta"]
    const { container } = render(
      <ToolGroup
        group={group({
          key: "all",
          calls: titles.map((_, i) =>
            call({ requestId: `c${i}`, toolName: `t${i}` }),
          ),
          segments: titles.map((title, i) => ({
            toolName: `t${i}`,
            title,
            count: 1,
            settled: true,
          })),
        })}
      />,
    )
    expect(headerText(container)).toBe("Alpha, Beta, Gamma, and 1 other")
  })

  it("shows the first segment whole even when it alone busts the budget", () => {
    // Otherwise the header would be nothing but "and N others", naming nothing.
    // Its overflow is the joined list's problem (a CSS ellipsis on the
    // wrapper), never a truncated title.
    const long = "Reconciled the quarterly ledger against the general ledger"
    const { container } = render(
      <ToolGroup
        group={group({
          key: "all",
          calls: [
            call({ requestId: "a", toolName: "reconcile" }),
            call({ requestId: "b", toolName: "notify" }),
          ],
          segments: [
            { toolName: "reconcile", title: long, count: 1, settled: true },
            { toolName: "notify", title: "Notified", count: 1, settled: true },
          ],
        })}
      />,
    )
    expect(headerText(container)).toBe(`${long}, and 1 other`)
    expect(
      container.querySelector(".shinychat-tool-group__title")?.textContent,
    ).toBe(long)
  })

  it("leaves a homogeneous group header exactly as it was: one title, one ×N", () => {
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
    // No segment wrapper, and the badge is still the title's next sibling.
    //
    // 2026-07-30: this used to also assert the title's parent was the row
    // itself. Relaxed deliberately when the single- and multi-call shapes were
    // merged into one component — the title now sits inside
    // `__titlewrap` in *both* shapes, which is what keeps React from remounting
    // it (and dropping the crossfade) when a group grows from one call to two.
    // Don't restore that assertion; the invariant that matters is the one
    // below, that a homogeneous header still renders one title and one badge.
    expect(
      container.querySelector(".shinychat-tool-group__segments"),
    ).toBeNull()
    const title = container.querySelector(".shinychat-tool-group__title")!
    expect(title.nextElementSibling?.className).toBe(
      "shinychat-tool-group__count",
    )
    expect(
      container.querySelectorAll(".shinychat-tool-group__count").length,
    ).toBe(1)
    expect(title.nextElementSibling?.getAttribute("aria-label")).toBe("2 calls")
  })

  it("says 'Used <tool>' for an untitled tool, and 'Using' until it settles", () => {
    const settled = group({
      toolName: "run_sql",
      title: undefined,
      calls: [
        call({ requestId: "a", toolName: "run_sql" }),
        call({ requestId: "b", toolName: "run_sql" }),
      ],
    })
    vi.useFakeTimers()
    try {
      const { container, rerender } = render(<ToolGroup group={settled} />)
      expect(headerText(container)).toBe("Used run_sql×2")

      rerender(
        <ToolGroup
          group={group({
            toolName: "run_sql",
            title: undefined,
            titleSettled: false,
            calls: [
              call({ requestId: "a", toolName: "run_sql", status: "running" }),
              call({ requestId: "b", toolName: "run_sql", status: "running" }),
            ],
          })}
        />,
      )
      // The verb crossfades rather than flipping, so the new text lands once
      // the fade-out has run.
      act(() => {
        vi.advanceTimersByTime(200)
      })
      expect(headerText(container)).toBe("Using run_sql×2")
    } finally {
      vi.useRealTimers()
    }
  })

  it("crossfades a segment title when the result title replaces the definition title", () => {
    // The same transition the thinking header animates ("Thinking" → "Thought
    // for 2s"): a tool's title changes under the reader as the call settles, so
    // it fades out, swaps, and fades back in instead of flipping mid-row.
    vi.useFakeTimers()
    try {
      const running = group({
        title: "Inspecting schema",
        calls: [
          call({ requestId: "a", status: "running" }),
          call({ requestId: "b", status: "running" }),
        ],
      })
      const { container, rerender } = render(<ToolGroup group={running} />)
      const title = () =>
        container.querySelector(".shinychat-tool-group__title")!
      expect(title().hasAttribute("data-fading")).toBe(false)

      rerender(
        <ToolGroup
          group={group({
            title: "Inspected schema",
            calls: [call({ requestId: "a" }), call({ requestId: "b" })],
          })}
        />,
      )
      // Mid-fade the old title is still the one on screen, at opacity 0.
      expect(title().getAttribute("data-fading")).toBe("true")
      expect(title().textContent).toBe("Inspecting schema")

      act(() => {
        vi.advanceTimersByTime(200)
      })
      expect(title().hasAttribute("data-fading")).toBe(false)
      expect(title().textContent).toBe("Inspected schema")
    } finally {
      vi.useRealTimers()
    }
  })

  it("keeps the same header elements when a group grows from one call to two", () => {
    // The two shapes used to be separate components in the same position, so
    // React tore the subtree down at this boundary — discarding every row's
    // expand state and remounting the title, which is exactly where the
    // crossfade fires.
    const { container, rerender } = render(
      <ToolGroup
        group={group({
          title: "Weather for Portland",
          calls: [call({ requestId: "a", value: "1" })],
        })}
      />,
    )
    const row = container.querySelector(".shinychat-tool-group__row")!
    const title = container.querySelector(".shinychat-tool-group__title")!
    fireEvent.click(row)
    expect(row.getAttribute("aria-expanded")).toBe("true")

    rerender(
      <ToolGroup
        group={group({
          title: "Weather Forecast",
          calls: [
            call({ requestId: "a", value: "1" }),
            call({ requestId: "b", value: "2" }),
          ],
        })}
      />,
    )
    // The very same nodes, so nothing remounted...
    expect(container.querySelector(".shinychat-tool-group__row")).toBe(row)
    expect(container.querySelector(".shinychat-tool-group__title")).toBe(title)
    // ...and the disclosure the user opened is still open, now over the list of
    // calls rather than the lone call's card.
    expect(row.getAttribute("aria-expanded")).toBe("true")
    expect(
      (container.querySelector(".shinychat-tool-group__calls") as HTMLElement)
        .hidden,
    ).toBe(false)
  })

  it("crossfades the title when a group grows from one call to two", () => {
    // A single-call header shows that call's own dynamic result title; a
    // grouped header shows the tool's static definition title instead (see
    // `resolveTitle`). That swap is a real change of identity, and it can only
    // animate if the title element survives the growth.
    vi.useFakeTimers()
    try {
      const { container, rerender } = render(
        <ToolGroup
          group={group({
            title: "Weather for Portland",
            calls: [call({ requestId: "a" })],
          })}
        />,
      )
      const title = () =>
        container.querySelector(".shinychat-tool-group__title")!
      expect(title().hasAttribute("data-fading")).toBe(false)

      rerender(
        <ToolGroup
          group={group({
            title: "Weather Forecast",
            calls: [call({ requestId: "a" }), call({ requestId: "b" })],
          })}
        />,
      )
      // Mid-fade the old title is still the one on screen, at opacity 0 — while
      // the ×N, which lives outside the fading element, has already landed.
      expect(title().getAttribute("data-fading")).toBe("true")
      expect(title().textContent).toBe("Weather for Portland")
      expect(headerText(container)).toBe("Weather for Portland×2")

      act(() => {
        vi.advanceTimersByTime(200)
      })
      expect(title().hasAttribute("data-fading")).toBe(false)
      expect(headerText(container)).toBe("Weather Forecast×2")
    } finally {
      vi.useRealTimers()
    }
  })

  it("does not fade the title when only the call count changes", () => {
    // The ×N badge lives outside the fading element on purpose: another call
    // landing is not a change of identity, and blinking the title for it would
    // make a busy group flicker.
    vi.useFakeTimers()
    try {
      const { container, rerender } = render(
        <ToolGroup
          group={group({
            title: "Searched the web",
            calls: [call({ requestId: "a" }), call({ requestId: "b" })],
          })}
        />,
      )
      rerender(
        <ToolGroup
          group={group({
            title: "Searched the web",
            calls: [
              call({ requestId: "a" }),
              call({ requestId: "b" }),
              call({ requestId: "c" }),
            ],
          })}
        />,
      )
      const title = container.querySelector(".shinychat-tool-group__title")!
      expect(title.hasAttribute("data-fading")).toBe(false)
      expect(headerText(container)).toBe("Searched the web×3")
    } finally {
      vi.useRealTimers()
    }
  })

  it("keeps one leading verb when no tool in the group has a title", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          key: "all",
          toolName: "search_web",
          title: undefined,
          calls: [
            call({ requestId: "a", toolName: "search_web" }),
            call({ requestId: "b", toolName: "search_web" }),
            call({ requestId: "c", toolName: "read_page" }),
          ],
          segments: [
            { toolName: "search_web", count: 2, settled: true },
            { toolName: "read_page", count: 1, settled: true },
          ],
        })}
      />,
    )
    expect(headerText(container)).toBe("Used search_web×2, read_page")
  })

  it("keeps every verb when the group mixes titled and untitled tools", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          key: "all",
          toolName: "search_web",
          title: "Searched the web",
          calls: [
            call({ requestId: "a", toolName: "search_web" }),
            call({ requestId: "b", toolName: "read_page" }),
            call({ requestId: "c", toolName: "read_page", status: "running" }),
          ],
          segments: [
            {
              toolName: "search_web",
              title: "Searched the web",
              count: 1,
              settled: true,
            },
            { toolName: "read_page", count: 2, settled: false },
          ],
        })}
      />,
    )
    expect(headerText(container)).toBe("Searched the web, Using read_page×2")
  })

  it("suppresses a row title already shown by that call's own segment", () => {
    // The comparison is per tool, not against the combined header: with a
    // heterogeneous header, "Read page" is visible in its own segment even
    // though it differs from the header's first title.
    const { container } = render(
      <ToolGroup
        group={group({
          key: "all",
          toolName: "search_web",
          title: "Searched the web",
          calls: [
            call({
              requestId: "a",
              toolName: "search_web",
              title: "Searched the web",
              label: undefined,
            }),
            call({ requestId: "b", toolName: "read_page", title: "Read page" }),
            call({
              requestId: "c",
              toolName: "read_page",
              title: "Read page: docs",
            }),
          ],
          segments: [
            {
              toolName: "search_web",
              title: "Searched the web",
              count: 1,
              settled: true,
            },
            {
              toolName: "read_page",
              title: "Read page",
              count: 2,
              settled: true,
            },
          ],
        })}
      />,
    )
    fireEvent.click(
      container.querySelector(".shinychat-tool-group__row") as Element,
    )
    const labels = Array.from(
      container.querySelectorAll(".shinychat-tool-call-row__label"),
    ).map((el) => el.textContent)
    // Rows a and b repeat their segment's title, so they fall through to the
    // tool-name fallback; only row c adds something new.
    expect(labels).toEqual(["search_web", "read_page", "Read page: docs"])
  })

  // Icons in a group whose identity varies. Segment titles are irrelevant here,
  // so these reuse one fixture and vary only the icons and statuses.
  const webIcon = '<svg class="icon-web"></svg>'
  const pageIcon = '<svg class="icon-page"></svg>'
  const pinIcon = '<svg class="icon-pin"></svg>'
  // A settled call whose tool has an icon and whose result added none: the
  // servers send the definition icon on the request and echo it on the result,
  // so both fields carry it and nothing reads as result-specific.
  function iconedCall(
    partial: Partial<ToolCallItem> & { requestId: string; icon: string },
  ): ToolCallItem {
    return call({ definitionIcon: partial.icon, ...partial })
  }
  function mixedGroup(calls: ToolCallItem[]): ToolCallGroup {
    return group({
      key: "all",
      toolName: "search_web",
      title: "Searched the web",
      icon: webIcon,
      calls,
      segments: [
        {
          toolName: "search_web",
          title: "Searched the web",
          count: 1,
          settled: true,
        },
        { toolName: "read_page", title: "Read page", count: 1, settled: true },
      ],
    })
  }

  it("keeps the tool icon on a homogeneous group header and status glyphs on its rows", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Searched",
          icon: webIcon,
          calls: [
            iconedCall({ requestId: "a", label: "one", icon: webIcon }),
            iconedCall({ requestId: "b", label: "two", icon: webIcon }),
          ],
        })}
      />,
    )
    expect(
      container.querySelector(".shinychat-tool-group__glyph .icon-web"),
    ).toBeTruthy()
    fireEvent.click(
      container.querySelector(".shinychat-tool-group__row") as Element,
    )
    // The rows keep reporting status, since the identity never varies.
    expect(
      container.querySelectorAll(".shinychat-tool-call-row__status .icon-web")
        .length,
    ).toBe(0)
    expect(
      container.querySelectorAll(".shinychat-tool-call-row__status svg").length,
    ).toBe(2)
  })

  it("moves the tool icons to the rows when the group spans several tools", () => {
    const { container } = render(
      <ToolGroup
        group={mixedGroup([
          call({ requestId: "a", toolName: "search_web", icon: webIcon }),
          call({ requestId: "b", toolName: "read_page", icon: pageIcon }),
        ])}
      />,
    )
    // The header can't claim one tool's icon, so it takes the generic dot.
    const glyph = container.querySelector(".shinychat-tool-group__glyph")!
    expect(glyph.querySelector(".shinychat-tool-glyph-dot")).toBeTruthy()
    expect(glyph.querySelector(".icon-web")).toBeNull()

    fireEvent.click(
      container.querySelector(".shinychat-tool-group__row") as Element,
    )
    const rows = container.querySelectorAll(".shinychat-tool-call-row__status")
    expect(rows[0]!.querySelector(".icon-web")).toBeTruthy()
    expect(rows[1]!.querySelector(".icon-page")).toBeTruthy()
  })

  it("keeps the spinner on a running row of a mixed group, over its tool icon", () => {
    const { container } = render(
      <ToolGroup
        group={mixedGroup([
          call({ requestId: "a", toolName: "search_web", icon: webIcon }),
          call({
            requestId: "b",
            toolName: "read_page",
            icon: pageIcon,
            status: "running",
          }),
        ])}
      />,
    )
    fireEvent.click(
      container.querySelector(".shinychat-tool-group__row") as Element,
    )
    const rows = container.querySelectorAll(".shinychat-tool-call-row__status")
    expect(rows[1]!.querySelector(".spinner-border")).toBeTruthy()
    expect(rows[1]!.querySelector(".icon-page")).toBeNull()
  })

  it("falls back to the status glyph for an iconless tool in a mixed group", () => {
    const { container } = render(
      <ToolGroup
        group={mixedGroup([
          call({ requestId: "a", toolName: "search_web", icon: webIcon }),
          call({ requestId: "b", toolName: "read_page", status: "error" }),
        ])}
      />,
    )
    fireEvent.click(
      container.querySelector(".shinychat-tool-group__row") as Element,
    )
    const row = container.querySelectorAll(
      ".shinychat-tool-call-row__status",
    )[1]!
    expect(row.className).toContain("text-danger")
    expect(row.querySelector("svg")).toBeTruthy()
    expect(row.querySelector(".icon-page")).toBeNull()
  })

  it("gives a row its result's own icon over the status glyph in a homogeneous group", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Searched",
          // The header keeps the tool's definition icon: the result icon on
          // call b speaks for that call alone.
          icon: webIcon,
          calls: [
            iconedCall({ requestId: "a", label: "one", icon: webIcon }),
            call({
              requestId: "b",
              label: "two",
              definitionIcon: webIcon,
              icon: pinIcon,
            }),
          ],
        })}
      />,
    )
    expect(
      container.querySelector(".shinychat-tool-group__glyph .icon-web"),
    ).toBeTruthy()
    fireEvent.click(
      container.querySelector(".shinychat-tool-group__row") as Element,
    )
    const rows = container.querySelectorAll(".shinychat-tool-call-row__status")
    // Row a said nothing specific about itself, so it keeps reporting status.
    expect(rows[0]!.querySelector(".icon-pin")).toBeNull()
    expect(rows[0]!.querySelector("svg")).toBeTruthy()
    expect(rows[1]!.querySelector(".icon-pin")).toBeTruthy()
  })

  it("gives a row its result's own icon over its tool icon in a mixed group", () => {
    const { container } = render(
      <ToolGroup
        group={mixedGroup([
          iconedCall({ requestId: "a", toolName: "search_web", icon: webIcon }),
          call({
            requestId: "b",
            toolName: "read_page",
            definitionIcon: pageIcon,
            icon: pinIcon,
          }),
        ])}
      />,
    )
    fireEvent.click(
      container.querySelector(".shinychat-tool-group__row") as Element,
    )
    const rows = container.querySelectorAll(".shinychat-tool-call-row__status")
    expect(rows[0]!.querySelector(".icon-web")).toBeTruthy()
    expect(rows[1]!.querySelector(".icon-pin")).toBeTruthy()
    expect(rows[1]!.querySelector(".icon-page")).toBeNull()
  })

  it("keeps a failed row's result icon, with the red tint and the 'failed' note", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Searched",
          icon: webIcon,
          calls: [
            iconedCall({ requestId: "a", label: "one", icon: webIcon }),
            call({
              requestId: "b",
              label: "two",
              definitionIcon: webIcon,
              icon: pinIcon,
              status: "error",
            }),
          ],
        })}
      />,
    )
    fireEvent.click(
      container.querySelector(".shinychat-tool-group__row") as Element,
    )
    const row = container.querySelectorAll(".shinychat-tool-call-row")[1]!
    const glyph = row.querySelector(".shinychat-tool-call-row__status")!
    // The icon replaces the exclamation, so failure has to stay legible through
    // the tint on that icon plus the text note.
    expect(glyph.querySelector(".icon-pin")).toBeTruthy()
    expect(glyph.className).toContain("text-danger")
    expect(
      row.querySelector(".shinychat-tool-group__failed")?.textContent,
    ).toBe("failed")
  })

  it("keeps the spinner on a running row over a result icon", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Searched",
          icon: webIcon,
          calls: [
            iconedCall({ requestId: "a", label: "one", icon: webIcon }),
            call({
              requestId: "b",
              label: "two",
              definitionIcon: webIcon,
              icon: pinIcon,
              status: "running",
            }),
          ],
        })}
      />,
    )
    fireEvent.click(
      container.querySelector(".shinychat-tool-group__row") as Element,
    )
    const rows = container.querySelectorAll(".shinychat-tool-call-row__status")
    expect(rows[1]!.querySelector(".spinner-border")).toBeTruthy()
    expect(rows[1]!.querySelector(".icon-pin")).toBeNull()
  })

  it("uses a dictionary-style argument preview as the per-call label fallback", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Searched",
          calls: [
            call({
              requestId: "a",
              arguments: '{"query":"glucose"}',
            }),
            call({ requestId: "b", arguments: '{"query":"mannose"}' }),
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
    expect(labels).toContain("query: glucose")
  })

  it("previews up to three args as key: value, skipping keys starting with _ or .", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Weather Forecast",
          calls: [
            call({
              requestId: "a",
              arguments:
                '{"lat":45.5152,"lon":-122.6784,"loc":"PDX","extra":"x","_intent":"why",".hidden":"h"}',
            }),
            call({ requestId: "b", arguments: '{"lat":1}' }),
          ],
        })}
      />,
    )
    fireEvent.click(
      container.querySelector(".shinychat-tool-group__row") as Element,
    )
    const preview = container.querySelector(
      ".shinychat-tool-call-row__label code",
    )?.textContent
    expect(preview).toBe("lat: 45.5152, lon: -122.6784, loc: PDX")
  })

  it("shows each call's full dynamic title on the per-call rows of an aggregated group", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Weather Forecast",
          calls: [
            call({ requestId: "a", title: "Weather Forecast for Portland" }),
            call({
              requestId: "b",
              title: "Weather Forecast for San Francisco",
            }),
          ],
        })}
      />,
    )
    // Header is the static title.
    expect(
      container.querySelector(".shinychat-tool-group__title")?.textContent,
    ).toBe("Weather Forecast")
    fireEvent.click(
      container.querySelector(".shinychat-tool-group__row") as Element,
    )
    const labels = Array.from(
      container.querySelectorAll(".shinychat-tool-call-row__label"),
    ).map((el) => el.textContent)
    expect(labels).toEqual([
      "Weather Forecast for Portland",
      "Weather Forecast for San Francisco",
    ])
  })

  it("shows a single call's dynamic title alone, with no arg-preview suffix", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Weather Forecast for Portland",
          calls: [
            call({
              requestId: "a",
              title: "Weather Forecast for Portland",
              definitionTitle: "Weather Forecast",
              arguments: '{"lat":45.5152}',
              value: "sunny",
              valueType: "text",
            }),
          ],
        })}
      />,
    )
    expect(
      container.querySelector(".shinychat-tool-group__title")?.textContent,
    ).toBe("Weather Forecast for Portland")
    // No colon/label appended (the title is the header).
    expect(container.querySelector(".shinychat-tool-group__label")).toBeNull()
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

  // The note trails the spacer so it lands by the chevron, matching the
  // single-call row (user, 2026-07-30). Asserted structurally rather than by
  // text, because the position is the decision — a note that drifts back to
  // the left of the spacer would still pass a textContent check.
  it("puts the failure note after the spacer in both shapes", () => {
    const after = (container: HTMLElement) => {
      const kids = [
        ...container.querySelector(".shinychat-tool-group__row")!.children,
      ]
      const spacer = kids.findIndex((n) =>
        n.classList.contains("shinychat-tool-spacer"),
      )
      const note = kids.findIndex((n) =>
        n.classList.contains("shinychat-tool-group__failed"),
      )
      expect(note).toBeGreaterThan(-1)
      return note > spacer
    }

    const multi = render(
      <ToolGroup
        group={group({
          title: "Searched",
          calls: [
            call({ requestId: "a", status: "success" }),
            call({ requestId: "b", status: "error" }),
          ],
        })}
      />,
    )
    expect(after(multi.container)).toBe(true)

    const solo = render(
      <ToolGroup
        group={group({
          title: "Searched",
          calls: [call({ requestId: "a", status: "error" })],
        })}
      />,
    )
    expect(after(solo.container)).toBe(true)
  })

  it("marks which grouped row failed with the same subtle text note, not just the red glyph", () => {
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
    fireEvent.click(
      container.querySelector(".shinychat-tool-group__row") as Element,
    )
    const rows = container.querySelectorAll(".shinychat-tool-call-row")
    expect(rows.length).toBe(2)

    // Only the failed row carries the note, and it is real text in the
    // accessibility tree (not a CSS ::before), so a screen reader reaches it.
    expect(rows[0]!.querySelector(".shinychat-tool-group__failed")).toBeNull()
    expect(
      rows[1]!.querySelector(".shinychat-tool-group__failed")?.textContent,
    ).toBe("failed")
    expect(rows[1]!.textContent).toContain("failed")
    expect(rows[0]!.textContent).not.toContain("failed")

    // The group header's own "N failed" note is unchanged.
    expect(
      container.querySelector(
        ".shinychat-tool-group__row .shinychat-tool-group__failed",
      )?.textContent,
    ).toBe("1 failed")
  })

  it("leaves a running grouped row free of the failed note", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Searching",
          titleSettled: false,
          calls: [
            call({ requestId: "a", status: "running", label: "one" }),
            call({ requestId: "b", status: "success", label: "two" }),
          ],
        })}
      />,
    )
    fireEvent.click(
      container.querySelector(".shinychat-tool-group__row") as Element,
    )
    expect(
      container.querySelectorAll(
        ".shinychat-tool-call-row .shinychat-tool-group__failed",
      ).length,
    ).toBe(0)
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

  it("falls back to the tool name for a call with no label and no scalar argument", () => {
    // Last resort in the per-call chain: without it the row would be an
    // unnamed glyph + chevron button. Reuses the group header's own fallback.
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
    const labels = Array.from(
      container.querySelectorAll(".shinychat-tool-call-row__label code"),
    ).map((el) => el.textContent)
    expect(labels).toEqual(["search", "search"])
    // Every Tier-2 expand control has an accessible name.
    for (const btn of container.querySelectorAll(
      ".shinychat-tool-call-row__summary",
    )) {
      expect(btn.textContent!.trim()).not.toBe("")
    }
  })

  it("leaves a bare single-call row's label empty (the header is the tool name)", () => {
    // The tool-name fallback is Tier-2 only: a single-call row already shows it
    // in the header, so adding it as a label would read "search: search".
    const { container } = render(
      <ToolGroup
        group={group({
          title: undefined,
          calls: [call({ requestId: "a", arguments: "{}", value: "ok" })],
        })}
      />,
    )
    expect(
      container.querySelector(".shinychat-tool-group__toolname")?.textContent,
    ).toBe("search")
    expect(container.querySelector(".shinychat-tool-group__label")).toBeNull()
  })
  it("honors a call's `expanded` flag inside a grouped Tier-2 list", () => {
    // `expanded` (tool_result_display(open = TRUE) / ToolResultDisplay(open=True)
    // / <shiny-tool-result expanded>) must survive aggregation: grouping is the
    // default as soon as a tool is called twice.
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Searched",
          calls: [
            call({ requestId: "a", label: "glucose", value: "1" }),
            call({
              requestId: "b",
              label: "mannose",
              value: "2",
              expanded: true,
            }),
          ],
        })}
      />,
    )
    // The group opened so the expanded row isn't stranded in a hidden list.
    const groupRow = container.querySelector(".shinychat-tool-group__row")
    expect(groupRow?.getAttribute("aria-expanded")).toBe("true")
    expect(
      (container.querySelector(".shinychat-tool-group__calls") as HTMLElement)
        .hidden,
    ).toBe(false)

    const summaries = container.querySelectorAll(
      ".shinychat-tool-call-row__summary",
    )
    expect(summaries[0]!.getAttribute("aria-expanded")).toBe("false")
    expect(summaries[1]!.getAttribute("aria-expanded")).toBe("true")
    // Only the flagged call reveals its Tier-3 card.
    expect(container.querySelectorAll(".shiny-tool-card").length).toBe(1)
  })

  it("stays collapsed when no call in the group is flagged expanded", () => {
    const { container } = render(
      <ToolGroup
        group={group({
          title: "Searched",
          calls: [
            call({ requestId: "a", label: "glucose", expanded: false }),
            call({ requestId: "b", label: "mannose" }),
          ],
        })}
      />,
    )
    expect(
      container
        .querySelector(".shinychat-tool-group__row")
        ?.getAttribute("aria-expanded"),
    ).toBe("false")
  })

  it("latches open when `expanded` arrives with the result after the row mounted", () => {
    // The row mounts on the request (no `expanded` yet); the flag only appears
    // once the result element lands, so seeding state at mount isn't enough.
    const running = group({
      title: "Searching",
      titleSettled: false,
      calls: [
        call({ requestId: "a", label: "glucose", status: "running" }),
        call({ requestId: "b", label: "mannose", status: "running" }),
      ],
    })
    const { container, rerender } = render(<ToolGroup group={running} />)
    expect(
      container
        .querySelector(".shinychat-tool-group__row")
        ?.getAttribute("aria-expanded"),
    ).toBe("false")

    rerender(
      <ToolGroup
        group={group({
          title: "Searched",
          calls: [
            call({ requestId: "a", label: "glucose", value: "1" }),
            call({
              requestId: "b",
              label: "mannose",
              value: "2",
              expanded: true,
            }),
          ],
        })}
      />,
    )
    expect(
      container
        .querySelector(".shinychat-tool-group__row")
        ?.getAttribute("aria-expanded"),
    ).toBe("true")
    const summaries = container.querySelectorAll(
      ".shinychat-tool-call-row__summary",
    )
    expect(summaries[1]!.getAttribute("aria-expanded")).toBe("true")
  })

  it("does not reopen a group the user collapsed after `expanded` latched", () => {
    const expandedGroup = group({
      title: "Searched",
      calls: [
        call({ requestId: "a", label: "glucose", value: "1" }),
        call({ requestId: "b", label: "mannose", value: "2", expanded: true }),
      ],
    })
    const { container, rerender } = render(<ToolGroup group={expandedGroup} />)
    const groupRow = container.querySelector(
      ".shinychat-tool-group__row",
    ) as Element
    fireEvent.click(groupRow)
    expect(groupRow.getAttribute("aria-expanded")).toBe("false")

    // A re-render (streaming re-routes on every chunk) must not fight the user.
    rerender(<ToolGroup group={{ ...expandedGroup }} />)
    expect(groupRow.getAttribute("aria-expanded")).toBe("false")
  })

  it("gives every row and leaf card a document-unique aria-controls target", () => {
    // Neither `group.key` nor `requestId` is unique across the transcript: the
    // key is per routed loop, and `requestId` is optional (anonymous calls get a
    // loop-local synthetic id) so it can repeat. Two loops that group the same
    // tool, down to their expanded Tier-3 cards, must not collide.
    const twoGroups = (
      <>
        <ToolGroup
          group={group({
            key: "all",
            calls: [
              call({ requestId: "", localId: "__anon-0", value: "1" }),
              call({ requestId: "", localId: "__anon-1", value: "2" }),
            ],
          })}
        />
        <ToolGroup
          group={group({
            key: "all",
            calls: [
              call({ requestId: "", localId: "__anon-0", value: "3" }),
              call({ requestId: "", localId: "__anon-1", value: "4" }),
            ],
          })}
        />
      </>
    )
    const { container } = render(twoGroups)

    // Expand every tier so all ids are in the document at once.
    for (const row of container.querySelectorAll(
      ".shinychat-tool-group__row",
    )) {
      fireEvent.click(row)
    }
    for (const row of container.querySelectorAll(
      ".shinychat-tool-call-row__summary",
    )) {
      fireEvent.click(row)
    }
    expect(container.querySelectorAll(".shiny-tool-card").length).toBe(4)

    const targets = [...container.querySelectorAll("[aria-controls]")].map(
      (el) => el.getAttribute("aria-controls"),
    )
    expect(new Set(targets).size).toBe(targets.length)
    for (const id of targets) {
      expect(container.querySelectorAll(`[id="${id}"]`).length).toBe(1)
    }
  })
})
