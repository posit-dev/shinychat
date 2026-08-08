import { describe, it, expect, afterEach } from "vitest"
import type { CSSProperties } from "react"
import {
  render,
  screen,
  cleanup,
  fireEvent,
  act,
  waitFor,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { markdownProcessor } from "../../src/markdown/processors"
import { parseMarkdown, hastToReact } from "../../src/markdown/markdownToReact"
import { chatTagToComponentMap } from "../../src/chat/chatTagToComponentMap"
import { AsideGroupView, parseAsideEntries } from "../../src/chat/AsideGroup"
import type { Element } from "hast"

afterEach(cleanup)

function renderMarkdown(md: string) {
  const hast = parseMarkdown(md, markdownProcessor)
  return render(
    <>{hastToReact(hast, { tagToComponentMap: chatTagToComponentMap })}</>,
  )
}

function renderMarkdownStreaming(md: string) {
  const hast = parseMarkdown(md, markdownProcessor)
  return render(
    <>
      {hastToReact(hast, {
        tagToComponentMap: chatTagToComponentMap,
        streaming: true,
      })}
    </>,
  )
}

describe("AsideGroup", () => {
  it("normalizes citation metadata from markup", () => {
    const node: Element = {
      type: "element",
      tagName: "shiny-aside-group",
      properties: {},
      children: [
        {
          type: "element",
          tagName: "shiny-aside",
          properties: {
            dataCitation: "",
            label: "example.com",
            url: "https://example.com",
            "grounded-span": "Supported claim",
            "cited-quote": "Source evidence",
            dataGroundingId: "citation-grounding-1",
          },
          children: [
            {
              type: "element",
              tagName: "a",
              properties: { href: "https://example.com" },
              children: [{ type: "text", value: "Example title" }],
            },
          ],
        },
      ],
    }

    expect(parseAsideEntries(node)).toEqual([
      {
        label: "example.com",
        url: "https://example.com",
        body: '<a href="https://example.com">Example title</a>',
        index: undefined,
        icon: undefined,
        citation: {
          title: "Example title",
          grounded_span: "Supported claim",
          cited_quote: "Source evidence",
          grounding_id: "citation-grounding-1",
        },
      },
    ])
  })

  it("treats a citation body containing only its URL as untitled", () => {
    const url = "https://example.com"
    const node: Element = {
      type: "element",
      tagName: "shiny-aside-group",
      properties: {},
      children: [
        {
          type: "element",
          tagName: "shiny-aside",
          properties: { dataCitation: "", label: "example.com", url },
          children: [
            {
              type: "element",
              tagName: "a",
              properties: { href: url },
              children: [{ type: "text", value: url }],
            },
          ],
        },
      ],
    }

    expect(parseAsideEntries(node)[0]?.citation?.title).toBeUndefined()
  })

  it("renders normalized entries without a HAST node", async () => {
    const user = userEvent.setup()
    render(
      <AsideGroupView
        entries={[
          {
            label: "Example",
            url: "https://example.com/source",
            body: "<p>Evidence</p>",
          },
        ]}
      />,
    )

    await user.click(screen.getByRole("button", { name: "Example" }))

    expect(screen.getByRole("dialog")).toHaveTextContent("Evidence")
  })

  it("highlights the active citation's grounded span", async () => {
    const user = userEvent.setup()
    const { container } = renderMarkdown(
      'A **supported** claim<shiny-aside data-citation label="Example" url="https://example.com" grounded-span="supported claim">Source</shiny-aside>.',
    )
    const grounded = container.querySelectorAll(".shiny-citation-grounded")

    expect(grounded).toHaveLength(2)
    expect(grounded[0]).not.toHaveAttribute("data-active")
    expect(grounded[1]).not.toHaveAttribute("data-active")
    await user.click(screen.getByRole("button", { name: "Example" }))
    expect(grounded[0]).toHaveAttribute("data-active", "")
    expect(grounded[1]).toHaveAttribute("data-active", "")
  })

  it("clears the grounded highlight when the popover closes", async () => {
    const user = userEvent.setup()
    const { container } = renderMarkdown(
      'A supported claim<shiny-aside data-citation label="Example" url="https://example.com" grounded-span="supported claim">Source</shiny-aside>.',
    )
    const grounded = container.querySelector(".shiny-citation-grounded")

    await user.click(screen.getByRole("button", { name: "Example" }))
    await user.click(screen.getByRole("button", { name: "Example" }))
    expect(grounded).not.toHaveAttribute("data-active")
  })

  it("moves the grounded highlight with the citation carousel", async () => {
    const user = userEvent.setup()
    const { container } = renderMarkdown(
      [
        'First claim<shiny-aside data-citation label="First" url="https://first.example" grounded-span="First claim">First source</shiny-aside>',
        'and second claim<shiny-aside data-citation label="Second" url="https://second.example" grounded-span="second claim">Second source</shiny-aside>.',
      ].join(" "),
    )
    const grounded = container.querySelectorAll(".shiny-citation-grounded")

    await user.click(screen.getByRole("button", { name: /First.*\+1/ }))
    expect(grounded[0]).toHaveAttribute("data-active", "")
    expect(grounded[1]).not.toHaveAttribute("data-active")

    await user.click(screen.getByRole("button", { name: "Next source" }))
    expect(grounded[0]).not.toHaveAttribute("data-active")
    expect(grounded[1]).toHaveAttribute("data-active", "")
  })

  it("renders a chip with the label for a single labeled aside", () => {
    renderMarkdown(
      'A claim<shiny-aside label="eBicycles" url="https://ebicycles.example"></shiny-aside>.',
    )
    expect(screen.getByText("eBicycles")).toBeInTheDocument()
    expect(screen.queryByText("+1")).not.toBeInTheDocument()
  })

  it("shows an overflow count for additional distinct identities in the group", () => {
    renderMarkdown(
      [
        'Claim one<shiny-aside label="eBicycles" url="https://ebicycles.example"></shiny-aside>.',
        'Claim two<shiny-aside label="WIRED" url="https://wired.example"></shiny-aside>.',
      ].join(" "),
    )
    expect(screen.getByText("eBicycles")).toBeInTheDocument()
    expect(screen.getByText("+1")).toBeInTheDocument()
  })

  it("shows no overflow count when every grouped aside shares one label", () => {
    renderMarkdown(
      [
        'First mention<shiny-aside label="eBicycles" url="https://ebicycles.example/a"></shiny-aside>.',
        'Second mention<shiny-aside label="eBicycles" url="https://ebicycles.example/b"></shiny-aside>.',
      ].join(" "),
    )
    expect(screen.getByText("eBicycles")).toBeInTheDocument()
    expect(screen.queryByText("+1")).not.toBeInTheDocument()
    // Accessible name is the bare label — no "(+1 more)" suffix.
    expect(
      screen.getByRole("button", { name: "eBicycles" }),
    ).toBeInTheDocument()
  })

  it("still pages between same-label entries in the popover", () => {
    renderMarkdown(
      [
        'First<shiny-aside label="eBicycles" url="https://ebicycles.example/a">first body</shiny-aside>.',
        'Second<shiny-aside label="eBicycles" url="https://ebicycles.example/b">second body</shiny-aside>.',
      ].join(" "),
    )
    fireEvent.click(screen.getByRole("button", { name: "eBicycles" }))
    expect(screen.getByRole("dialog")).toHaveTextContent("1 / 2")
    expect(screen.getByRole("dialog")).toHaveTextContent("first body")
    fireEvent.click(screen.getByRole("button", { name: "Next source" }))
    expect(screen.getByRole("dialog")).toHaveTextContent("second body")
  })

  it("counts every entry, not distinct labels, for the overflow badge", () => {
    renderMarkdown(
      [
        'First<shiny-aside label="eBicycles" url="https://ebicycles.example/a"></shiny-aside>.',
        'Second<shiny-aside label="eBicycles" url="https://ebicycles.example/b"></shiny-aside>.',
        'Third<shiny-aside label="WIRED" url="https://wired.example"></shiny-aside>.',
      ].join(" "),
    )
    // Three entries, mixed labels -> +2 (entries.length - 1), not +1 (distinct labels - 1).
    expect(screen.getByText("+2")).toBeInTheDocument()
  })

  it("includes the overflow count in the accessible name of a labeled pill", () => {
    renderMarkdown(
      [
        'Claim one<shiny-aside label="eBicycles" url="https://ebicycles.example"></shiny-aside>.',
        'Claim two<shiny-aside label="WIRED" url="https://wired.example"></shiny-aside>.',
      ].join(" "),
    )
    expect(
      screen.getByRole("button", { name: /eBicycles.*\+1/ }),
    ).toBeInTheDocument()
  })

  it("falls back to a count marker when no aside in the group has a label", () => {
    renderMarkdown(
      "A computed value<shiny-aside>definition text</shiny-aside>.",
    )
    const pill = screen.getByRole("button", { name: "Aside 1" })
    expect(pill).toHaveTextContent("1")
  })

  it("renders inline children as the popover body", () => {
    renderMarkdown(
      'A claim<shiny-aside label="eBicycles" url="https://ebicycles.example">See the **study**.</shiny-aside>.',
    )
    fireEvent.click(screen.getByRole("button", { name: /eBicycles/ }))
    expect(screen.getByText("study")).toBeInTheDocument()
  })

  it("renders block children (a list) in the popover body", () => {
    renderMarkdown(
      'See notes<shiny-aside label="Study" url="https://study.example">\n\n**Key**\n\n- 40 models\n- 2024 data\n\n</shiny-aside>.',
    )
    fireEvent.click(screen.getByRole("button", { name: /Study/ }))
    expect(screen.getByText("40 models")).toBeInTheDocument()
    expect(screen.getByText("2024 data")).toBeInTheDocument()
  })

  it("renders an icon for an aside with an explicit icon but no url", () => {
    const { container } = renderMarkdown(
      'A definition<shiny-aside label="Term" icon="https://example.com/icon.png"></shiny-aside>.',
    )
    const img = container.querySelector(
      ".shiny-aside-pill img",
    ) as HTMLImageElement | null
    expect(img).toBeInTheDocument()
    expect(img?.getAttribute("src")).toBe("https://example.com/icon.png")
  })

  it("renders a source URL as an external link in the popover", async () => {
    const user = userEvent.setup()
    renderMarkdown(
      'A claim<shiny-aside label="Source" url="https://example.com/source">body</shiny-aside>.',
    )

    await user.click(screen.getByRole("button", { name: "Source" }))

    const link = within(screen.getByRole("dialog")).getByRole("link", {
      name: "Source",
    })
    expect(link).toHaveAttribute("href", "https://example.com/source")
    expect(link).toHaveAttribute("target", "_blank")
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
    expect(link).toHaveAttribute("data-shinychat-link", "")
  })

  it("does not render a source link for an unsafe URL", async () => {
    const user = userEvent.setup()
    renderMarkdown(
      'A claim<shiny-aside label="Source" url="javascript:alert(1)">body</shiny-aside>.',
    )

    await user.click(screen.getByRole("button", { name: "Source" }))

    expect(
      within(screen.getByRole("dialog")).queryByRole("link", {
        name: "Source",
      }),
    ).not.toBeInTheDocument()
  })

  it("hides a broken icon without reserving its layout space", () => {
    const { container } = renderMarkdown(
      'A claim<shiny-aside label="Term" icon="https://example.com/broken.png"></shiny-aside>.',
    )
    const img = container.querySelector(
      ".shiny-aside-pill img",
    ) as HTMLImageElement
    act(() => {
      fireEvent.error(img)
    })
    // Unmounted rather than hidden: a display:none <img> still satisfies the
    // pill's `:has(img)` padding rule, so the icon must leave the DOM entirely.
    expect(container.querySelector(".shiny-aside-pill img")).toBeNull()
  })

  it("renders nothing for a block with no asides", () => {
    const { container } = renderMarkdown("Just plain prose.")
    expect(
      container.querySelector(".shiny-aside-group"),
    ).not.toBeInTheDocument()
  })
})

describe("AsideGroup streaming", () => {
  it("hides an aside pill while its paragraph is still the streaming block", () => {
    renderMarkdownStreaming(
      'A claim<shiny-aside label="eBicycles" url="https://ebicycles.example"></shiny-aside> and more text',
    )
    expect(screen.queryByText("eBicycles")).not.toBeInTheDocument()
  })

  it("shows an aside pill once a later block follows its paragraph, mid-stream", () => {
    renderMarkdownStreaming(
      [
        'A claim<shiny-aside label="eBicycles" url="https://ebicycles.example"></shiny-aside>.',
        "",
        "A later paragraph still streaming",
      ].join("\n"),
    )
    expect(screen.getByText("eBicycles")).toBeInTheDocument()
  })

  it("shows the trailing paragraph's aside pill once streaming ends", () => {
    renderMarkdown(
      'A claim<shiny-aside label="eBicycles" url="https://ebicycles.example"></shiny-aside>.',
    )
    expect(screen.getByText("eBicycles")).toBeInTheDocument()
  })
})

describe("AsideGroup popover", () => {
  it("opens the popover on hover and shows the face entry's label and body", () => {
    renderMarkdown(
      'A claim<shiny-aside label="eBicycles" url="https://ebicycles.example">Hub motors are cheaper.</shiny-aside>.',
    )
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    fireEvent.mouseEnter(screen.getByRole("button", { name: /eBicycles/ }))
    expect(screen.getByRole("dialog")).toHaveTextContent(
      "Hub motors are cheaper.",
    )
  })

  it("closes on mouse-leave when not pinned", async () => {
    const user = userEvent.setup()
    renderMarkdown(
      'A claim<shiny-aside label="eBicycles" url="https://ebicycles.example"></shiny-aside>.',
    )
    const pill = screen.getByRole("button", { name: /eBicycles/ })
    await user.hover(pill)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    await user.unhover(pill)
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    })
  })

  it("keeps the popover open briefly after mouse-leave so the pointer can reach it", async () => {
    const user = userEvent.setup()
    renderMarkdown(
      'A claim<shiny-aside label="eBicycles" url="https://ebicycles.example"></shiny-aside>.',
    )
    const pill = screen.getByRole("button", { name: /eBicycles/ })
    await user.hover(pill)
    await user.unhover(pill)
    // The popover must still be present immediately after leaving the pill,
    // otherwise the pointer has nothing left to land on while crossing the gap.
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("cancels the pending close when the pointer re-enters before the grace period elapses", async () => {
    const user = userEvent.setup()
    renderMarkdown(
      'A claim<shiny-aside label="eBicycles" url="https://ebicycles.example"></shiny-aside>.',
    )
    const pill = screen.getByRole("button", { name: /eBicycles/ })
    await user.hover(pill)
    await user.unhover(pill)
    await user.hover(screen.getByRole("dialog"))

    // This test exercises the 150ms close timer itself, so wait past that
    // known interval before checking that the re-entry canceled it.
    await act(async () => {
      await new Promise<void>((resolve) => {
        window.setTimeout(resolve, 200)
      })
    })

    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("pins the popover open on click, surviving mouse-leave", () => {
    renderMarkdown(
      'A claim<shiny-aside label="eBicycles" url="https://ebicycles.example"></shiny-aside>.',
    )
    const pill = screen.getByRole("button", { name: /eBicycles/ })
    fireEvent.click(pill)
    fireEvent.mouseLeave(pill)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("closes a pinned popover on outside click", async () => {
    const user = userEvent.setup()
    renderMarkdown(
      'A claim<shiny-aside label="eBicycles" url="https://ebicycles.example"></shiny-aside>.',
    )
    await user.click(screen.getByRole("button", { name: /eBicycles/ }))
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    await user.pointer({ keys: "[MouseLeft>]", target: document.body })
    await user.pointer({ keys: "[/MouseLeft]", target: document.body })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("shows carousel navigation and pages between entries sharing a group", () => {
    renderMarkdown(
      [
        'Claim one<shiny-aside label="eBicycles" url="https://ebicycles.example">first</shiny-aside>.',
        'Claim two<shiny-aside label="WIRED" url="https://wired.example">second</shiny-aside>.',
      ].join(" "),
    )
    fireEvent.click(screen.getByRole("button", { name: /eBicycles/ }))
    expect(screen.getByRole("dialog")).toHaveTextContent("1 / 2")
    expect(screen.getByRole("dialog")).toHaveTextContent("first")
    fireEvent.click(screen.getByRole("button", { name: "Next source" }))
    expect(screen.getByRole("dialog")).toHaveTextContent("2 / 2")
    expect(screen.getByRole("dialog")).toHaveTextContent("second")
  })

  it("announces carousel source changes without repeating the body", async () => {
    const user = userEvent.setup()
    renderMarkdown(
      [
        'Claim one<shiny-aside label="eBicycles" url="https://ebicycles.example">first body</shiny-aside>.',
        'Claim two<shiny-aside label="WIRED" url="https://wired.example">second body</shiny-aside>.',
      ].join(" "),
    )

    await user.click(screen.getByRole("button", { name: /eBicycles/ }))
    expect(screen.getByRole("status")).toHaveTextContent(
      "Source 1 of 2: eBicycles",
    )

    await user.click(screen.getByRole("button", { name: "Next source" }))

    expect(screen.getByRole("status")).toHaveTextContent("Source 2 of 2: WIRED")
    expect(screen.getByRole("status")).not.toHaveTextContent("second body")
    expect(screen.getByText("2 / 2")).toBeVisible()
  })

  it("groups the prev/next arrows together, separate from the count", () => {
    renderMarkdown(
      [
        'Claim one<shiny-aside label="eBicycles" url="https://ebicycles.example"></shiny-aside>.',
        'Claim two<shiny-aside label="WIRED" url="https://wired.example"></shiny-aside>.',
      ].join(" "),
    )
    fireEvent.click(screen.getByRole("button", { name: /eBicycles/ }))
    const nav = screen
      .getByRole("dialog")
      .querySelector(".shiny-aside-popover__nav")!
    const arrows = nav.querySelector(".shiny-aside-popover__nav-arrows")!
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
      'A claim<shiny-aside label="eBicycles" url="https://ebicycles.example"></shiny-aside>.',
    )
    fireEvent.click(screen.getByRole("button", { name: /eBicycles/ }))
    expect(
      screen.queryByRole("button", { name: "Next source" }),
    ).not.toBeInTheDocument()
  })

  it("renders the popover through a floating-ui portal under document.body, escaping any clipping ancestor", () => {
    renderMarkdown(
      'A claim<shiny-aside label="eBicycles" url="https://ebicycles.example">Hub motors are cheaper.</shiny-aside>.',
    )
    fireEvent.mouseEnter(screen.getByRole("button", { name: /eBicycles/ }))
    const dialog = screen.getByRole("dialog")
    expect(dialog.closest(".shiny-aside-group")).toBeNull()
    const portalRoot = dialog.closest("[data-floating-ui-portal]")
    expect(portalRoot?.parentElement).toBe(document.body)
    expect(dialog.style.position).toBe("fixed")
  })

  it("carries scoped Bootstrap theme context into the body portal", async () => {
    const user = userEvent.setup()
    const scopedTheme = {
      "--bs-body-bg": "rgb(18, 18, 18)",
      "--bs-body-color": "rgb(238, 238, 238)",
    } as CSSProperties

    render(
      <div data-bs-theme="dark" style={scopedTheme}>
        <AsideGroupView
          entries={[
            {
              label: "Scoped source",
              body: "<p>Scoped evidence</p>",
            },
          ]}
        />
      </div>,
    )

    const pill = screen.getByRole("button", { name: "Scoped source" })
    // JSDOM does not resolve inherited custom properties. Mirror the values
    // that a browser resolves on the reference; Playwright covers inheritance.
    for (const [property, value] of Object.entries(scopedTheme)) {
      pill.style.setProperty(property, value)
    }
    await user.click(pill)

    const dialog = screen.getByRole("dialog")
    expect(dialog.closest("[data-floating-ui-portal]")?.parentElement).toBe(
      document.body,
    )
    expect(dialog).toHaveAttribute("data-bs-theme", "dark")
    expect(dialog.style.getPropertyValue("--bs-body-bg")).toBe(
      "rgb(18, 18, 18)",
    )
    expect(dialog.style.getPropertyValue("--bs-body-color")).toBe(
      "rgb(238, 238, 238)",
    )
  })

  it("keeps a pinned popover open when clicking inside the popover itself", () => {
    renderMarkdown(
      'A claim<shiny-aside label="eBicycles" url="https://ebicycles.example">Hub motors are cheaper.</shiny-aside>.',
    )
    fireEvent.click(screen.getByRole("button", { name: /eBicycles/ }))
    fireEvent.mouseDown(screen.getByRole("dialog"))
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("does not close when focus moves from the pill to a control inside the popover", () => {
    renderMarkdown(
      [
        'Claim one<shiny-aside label="eBicycles" url="https://ebicycles.example">first</shiny-aside>.',
        'Claim two<shiny-aside label="WIRED" url="https://wired.example">second</shiny-aside>.',
      ].join(" "),
    )
    const pill = screen.getByRole("button", { name: /eBicycles/ })
    fireEvent.click(pill)
    const nextButton = screen.getByRole("button", { name: "Next source" })
    act(() => nextButton.focus())
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("gives the dialog an accessible name", () => {
    renderMarkdown(
      'A claim<shiny-aside label="eBicycles" url="https://ebicycles.example">Hub motors are cheaper.</shiny-aside>.',
    )
    fireEvent.click(screen.getByRole("button", { name: /eBicycles/ }))
    expect(screen.getByRole("dialog")).toHaveAccessibleName()
  })

  it("opens the popover when the pill receives keyboard focus", () => {
    renderMarkdown(
      'A claim<shiny-aside label="eBicycles" url="https://ebicycles.example">Hub motors are cheaper.</shiny-aside>.',
    )
    const pill = screen.getByRole("button", { name: /eBicycles/ })
    act(() => pill.focus())
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("closes on Escape and leaves focus on the pill instead of dropping it", async () => {
    const user = userEvent.setup()
    renderMarkdown(
      'A claim<shiny-aside label="eBicycles" url="https://ebicycles.example">Hub motors are cheaper.</shiny-aside>.',
    )
    const pill = screen.getByRole("button", { name: /eBicycles/ })
    await user.click(pill)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    await user.keyboard("{Escape}")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(pill).toHaveFocus()
  })

  it("reaches the popover's nav controls by tabbing forward from the pill", async () => {
    const user = userEvent.setup()
    renderMarkdown(
      [
        'Claim one<shiny-aside label="eBicycles" url="https://ebicycles.example">first</shiny-aside>.',
        'Claim two<shiny-aside label="WIRED" url="https://wired.example">second</shiny-aside>.',
      ].join(" "),
    )
    const pill = screen.getByRole("button", { name: /eBicycles/ })
    await user.click(pill)
    await user.tab()
    expect(
      screen.getByRole("button", { name: "Previous source" }),
    ).toHaveFocus()
  })

  it("gives two separate anonymous asides in different paragraphs different numbers", () => {
    renderMarkdown(
      [
        "First paragraph, one anonymous claim<shiny-aside>a</shiny-aside>.",
        "",
        "Second paragraph, another anonymous claim<shiny-aside>b</shiny-aside>.",
      ].join("\n"),
    )
    expect(screen.getByRole("button", { name: "Aside 1" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Aside 2" })).toBeInTheDocument()
  })

  it("renders three anonymous asides in one paragraph as three separate, consecutively-numbered pills", () => {
    renderMarkdown(
      "Backed by three signals<shiny-aside>a</shiny-aside><shiny-aside>b</shiny-aside><shiny-aside>c</shiny-aside>.",
    )
    expect(screen.getByRole("button", { name: "Aside 1" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Aside 2" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Aside 3" })).toBeInTheDocument()
  })

  it("renders a mixed labeled+anonymous paragraph as two separate pills, not one with overflow", () => {
    renderMarkdown(
      'A cited claim<shiny-aside label="Public Source" url="https://example.com"></shiny-aside> and an anonymous one<shiny-aside>anon claim</shiny-aside>.',
    )
    expect(
      screen.getByRole("button", { name: /Public Source/ }),
    ).toBeInTheDocument()
    expect(screen.queryByText("+1")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Aside 1" })).toBeInTheDocument()
  })
})
