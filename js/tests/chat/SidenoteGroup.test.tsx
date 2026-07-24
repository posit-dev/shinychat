import { describe, it, expect, afterEach, vi } from "vitest"
import { render, screen, cleanup, fireEvent, act } from "@testing-library/react"
import { markdownProcessor } from "../../src/markdown/processors"
import { parseMarkdown, hastToReact } from "../../src/markdown/markdownToReact"
import { chatTagToComponentMap } from "../../src/chat/chatTagToComponentMap"

afterEach(cleanup)

function renderMarkdown(md: string) {
  const hast = parseMarkdown(md, markdownProcessor)
  return render(
    <>{hastToReact(hast, { tagToComponentMap: chatTagToComponentMap })}</>,
  )
}

describe("SidenoteGroup", () => {
  it("renders a chip with the label for a single labeled sidenote", () => {
    renderMarkdown(
      'A claim<shiny-sidenote label="eBicycles" url="https://ebicycles.example"></shiny-sidenote>.',
    )
    expect(screen.getByText("eBicycles")).toBeInTheDocument()
    expect(screen.queryByText("+1")).not.toBeInTheDocument()
  })

  it("shows an overflow count for additional distinct identities in the group", () => {
    renderMarkdown(
      [
        'Claim one<shiny-sidenote label="eBicycles" url="https://ebicycles.example"></shiny-sidenote>.',
        'Claim two<shiny-sidenote label="WIRED" url="https://wired.example"></shiny-sidenote>.',
      ].join(" "),
    )
    expect(screen.getByText("eBicycles")).toBeInTheDocument()
    expect(screen.getByText("+1")).toBeInTheDocument()
  })

  it("includes the overflow count in the accessible name of a labeled pill", () => {
    renderMarkdown(
      [
        'Claim one<shiny-sidenote label="eBicycles" url="https://ebicycles.example"></shiny-sidenote>.',
        'Claim two<shiny-sidenote label="WIRED" url="https://wired.example"></shiny-sidenote>.',
      ].join(" "),
    )
    expect(
      screen.getByRole("button", { name: /eBicycles.*\+1/ }),
    ).toBeInTheDocument()
  })

  it("falls back to a count marker when no sidenote in the group has a label", () => {
    renderMarkdown(
      "A computed value<shiny-sidenote>definition text</shiny-sidenote>.",
    )
    const pill = screen.getByRole("button", { name: "Sidenote 1" })
    expect(pill).toHaveTextContent("1")
  })

  it("renders inline children as the popover body", () => {
    renderMarkdown(
      'A claim<shiny-sidenote label="eBicycles" url="https://ebicycles.example">See the **study**.</shiny-sidenote>.',
    )
    fireEvent.click(screen.getByRole("button", { name: /eBicycles/ }))
    expect(screen.getByText("study")).toBeInTheDocument()
  })

  it("renders block children (a list) in the popover body", () => {
    renderMarkdown(
      'See notes<shiny-sidenote label="Study" url="https://study.example">\n\n**Key**\n\n- 40 models\n- 2024 data\n\n</shiny-sidenote>.',
    )
    fireEvent.click(screen.getByRole("button", { name: /Study/ }))
    expect(screen.getByText("40 models")).toBeInTheDocument()
    expect(screen.getByText("2024 data")).toBeInTheDocument()
  })

  it("renders an icon for a sidenote with an explicit icon but no url", () => {
    const { container } = renderMarkdown(
      'A definition<shiny-sidenote label="Term" icon="https://example.com/icon.png"></shiny-sidenote>.',
    )
    const img = container.querySelector(
      ".shiny-sidenote-pill img",
    ) as HTMLImageElement | null
    expect(img).toBeInTheDocument()
    expect(img?.getAttribute("src")).toBe("https://example.com/icon.png")
  })

  it("hides a broken icon without reserving its layout space", () => {
    const { container } = renderMarkdown(
      'A claim<shiny-sidenote label="Term" icon="https://example.com/broken.png"></shiny-sidenote>.',
    )
    const img = container.querySelector(
      ".shiny-sidenote-pill img",
    ) as HTMLImageElement
    fireEvent.error(img)
    expect(img.style.display).toBe("none")
  })

  it("renders nothing for a block with no sidenotes", () => {
    const { container } = renderMarkdown("Just plain prose.")
    expect(
      container.querySelector(".shiny-sidenote-group"),
    ).not.toBeInTheDocument()
  })
})

describe("SidenoteGroup popover", () => {
  it("opens the popover on hover and shows the face entry's label and body", () => {
    renderMarkdown(
      'A claim<shiny-sidenote label="eBicycles" url="https://ebicycles.example">Hub motors are cheaper.</shiny-sidenote>.',
    )
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    fireEvent.mouseEnter(screen.getByRole("button", { name: /eBicycles/ }))
    expect(screen.getByRole("dialog")).toHaveTextContent(
      "Hub motors are cheaper.",
    )
  })

  it("closes on mouse-leave when not pinned", () => {
    vi.useFakeTimers()
    try {
      renderMarkdown(
        'A claim<shiny-sidenote label="eBicycles" url="https://ebicycles.example"></shiny-sidenote>.',
      )
      const pill = screen.getByRole("button", { name: /eBicycles/ })
      fireEvent.mouseEnter(pill)
      expect(screen.getByRole("dialog")).toBeInTheDocument()
      fireEvent.mouseLeave(pill.closest(".shiny-sidenote-group")!)
      act(() => {
        vi.runAllTimers()
      })
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("keeps the popover open briefly after mouse-leave so the pointer can reach it", () => {
    vi.useFakeTimers()
    try {
      renderMarkdown(
        'A claim<shiny-sidenote label="eBicycles" url="https://ebicycles.example"></shiny-sidenote>.',
      )
      const pill = screen.getByRole("button", { name: /eBicycles/ })
      fireEvent.mouseEnter(pill)
      fireEvent.mouseLeave(pill.closest(".shiny-sidenote-group")!)
      // The popover must still be present immediately after leaving the pill,
      // otherwise the pointer has nothing left to land on while crossing the gap.
      expect(screen.getByRole("dialog")).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("cancels the pending close when the pointer re-enters before the grace period elapses", () => {
    vi.useFakeTimers()
    try {
      renderMarkdown(
        'A claim<shiny-sidenote label="eBicycles" url="https://ebicycles.example"></shiny-sidenote>.',
      )
      const pill = screen.getByRole("button", { name: /eBicycles/ })
      const container = pill.closest(".shiny-sidenote-group")!
      fireEvent.mouseEnter(pill)
      fireEvent.mouseLeave(container)
      fireEvent.mouseEnter(screen.getByRole("dialog"))
      act(() => {
        vi.runAllTimers()
      })
      expect(screen.getByRole("dialog")).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("pins the popover open on click, surviving mouse-leave", () => {
    renderMarkdown(
      'A claim<shiny-sidenote label="eBicycles" url="https://ebicycles.example"></shiny-sidenote>.',
    )
    const pill = screen.getByRole("button", { name: /eBicycles/ })
    fireEvent.click(pill)
    fireEvent.mouseLeave(pill.closest(".shiny-sidenote-group")!)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("closes a pinned popover on outside click", () => {
    renderMarkdown(
      'A claim<shiny-sidenote label="eBicycles" url="https://ebicycles.example"></shiny-sidenote>.',
    )
    fireEvent.click(screen.getByRole("button", { name: /eBicycles/ }))
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    fireEvent.mouseDown(document.body)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("shows carousel navigation and pages between entries sharing a group", () => {
    renderMarkdown(
      [
        'Claim one<shiny-sidenote label="eBicycles" url="https://ebicycles.example">first</shiny-sidenote>.',
        'Claim two<shiny-sidenote label="WIRED" url="https://wired.example">second</shiny-sidenote>.',
      ].join(" "),
    )
    fireEvent.click(screen.getByRole("button", { name: /eBicycles/ }))
    expect(screen.getByRole("dialog")).toHaveTextContent("1 / 2")
    expect(screen.getByRole("dialog")).toHaveTextContent("first")
    fireEvent.click(screen.getByRole("button", { name: "Next source" }))
    expect(screen.getByRole("dialog")).toHaveTextContent("2 / 2")
    expect(screen.getByRole("dialog")).toHaveTextContent("second")
  })

  it("groups the prev/next arrows together, separate from the count", () => {
    renderMarkdown(
      [
        'Claim one<shiny-sidenote label="eBicycles" url="https://ebicycles.example"></shiny-sidenote>.',
        'Claim two<shiny-sidenote label="WIRED" url="https://wired.example"></shiny-sidenote>.',
      ].join(" "),
    )
    fireEvent.click(screen.getByRole("button", { name: /eBicycles/ }))
    const nav = screen
      .getByRole("dialog")
      .querySelector(".shiny-sidenote-popover__nav")!
    const arrows = nav.querySelector(".shiny-sidenote-popover__nav-arrows")!
    expect(arrows).toContainElement(
      screen.getByRole("button", { name: "Previous source" }),
    )
    expect(arrows).toContainElement(
      screen.getByRole("button", { name: "Next source" }),
    )
    expect(arrows).not.toContainElement(screen.getByText("1 / 2"))
  })

  it("does not show carousel navigation for a single-entry group", () => {
    renderMarkdown(
      'A claim<shiny-sidenote label="eBicycles" url="https://ebicycles.example"></shiny-sidenote>.',
    )
    fireEvent.click(screen.getByRole("button", { name: /eBicycles/ }))
    expect(
      screen.queryByRole("button", { name: "Next source" }),
    ).not.toBeInTheDocument()
  })

  it("renders the popover through a floating-ui portal under document.body, escaping any clipping ancestor", () => {
    renderMarkdown(
      'A claim<shiny-sidenote label="eBicycles" url="https://ebicycles.example">Hub motors are cheaper.</shiny-sidenote>.',
    )
    fireEvent.mouseEnter(screen.getByRole("button", { name: /eBicycles/ }))
    const dialog = screen.getByRole("dialog")
    expect(dialog.closest(".shiny-sidenote-group")).toBeNull()
    const portalRoot = dialog.closest("[data-floating-ui-portal]")
    expect(portalRoot?.parentElement).toBe(document.body)
    expect(dialog.style.position).toBe("fixed")
  })

  it("keeps a pinned popover open when clicking inside the popover itself", () => {
    renderMarkdown(
      'A claim<shiny-sidenote label="eBicycles" url="https://ebicycles.example">Hub motors are cheaper.</shiny-sidenote>.',
    )
    fireEvent.click(screen.getByRole("button", { name: /eBicycles/ }))
    fireEvent.mouseDown(screen.getByRole("dialog"))
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("does not close when focus moves from the pill to a control inside the popover", () => {
    renderMarkdown(
      [
        'Claim one<shiny-sidenote label="eBicycles" url="https://ebicycles.example">first</shiny-sidenote>.',
        'Claim two<shiny-sidenote label="WIRED" url="https://wired.example">second</shiny-sidenote>.',
      ].join(" "),
    )
    const pill = screen.getByRole("button", { name: /eBicycles/ })
    fireEvent.click(pill)
    const nextButton = screen.getByRole("button", { name: "Next source" })
    fireEvent.blur(pill, { relatedTarget: nextButton })
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("gives two separate anonymous sidenotes in different paragraphs different numbers", () => {
    renderMarkdown(
      [
        "First paragraph, one anonymous claim<shiny-sidenote>a</shiny-sidenote>.",
        "",
        "Second paragraph, another anonymous claim<shiny-sidenote>b</shiny-sidenote>.",
      ].join("\n"),
    )
    expect(
      screen.getByRole("button", { name: "Sidenote 1" }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Sidenote 2" }),
    ).toBeInTheDocument()
  })

  it("renders three anonymous sidenotes in one paragraph as three separate, consecutively-numbered pills", () => {
    renderMarkdown(
      "Backed by three signals<shiny-sidenote>a</shiny-sidenote><shiny-sidenote>b</shiny-sidenote><shiny-sidenote>c</shiny-sidenote>.",
    )
    expect(
      screen.getByRole("button", { name: "Sidenote 1" }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Sidenote 2" }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Sidenote 3" }),
    ).toBeInTheDocument()
  })

  it("renders a mixed labeled+anonymous paragraph as two separate pills, not one with overflow", () => {
    renderMarkdown(
      'A cited claim<shiny-sidenote label="Public Source" url="https://example.com"></shiny-sidenote> and an anonymous one<shiny-sidenote>anon claim</shiny-sidenote>.',
    )
    expect(
      screen.getByRole("button", { name: /Public Source/ }),
    ).toBeInTheDocument()
    expect(screen.queryByText("+1")).not.toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Sidenote 1" }),
    ).toBeInTheDocument()
  })
})
