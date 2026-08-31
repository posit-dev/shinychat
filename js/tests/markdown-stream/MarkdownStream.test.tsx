import { render, screen, act, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import { ShinyLifecycleContext } from "../../src/chat/context"

const containerRef = vi.fn()
const scrollToBottom = vi.fn()
const engageStickToBottom = vi.fn()
const repinIfAtBottom = vi.fn()
const findScrollableParent = vi.fn()

vi.mock("../../src/markdown/useAutoScroll", () => ({
  useAutoScroll: vi.fn(() => ({
    containerRef,
    stickToBottom: true,
    scrollToBottom,
    engageStickToBottom,
    repinIfAtBottom,
  })),
  findScrollableParent: (...args: Parameters<typeof findScrollableParent>) =>
    findScrollableParent(...args),
}))

import {
  MarkdownStream,
  type MarkdownStreamApi,
} from "../../src/markdown-stream/MarkdownStream"
import { useAutoScroll } from "../../src/markdown/useAutoScroll"
import type { HtmlBlock } from "../../src/chat/html-block-model"
import type { WebActivityBlock } from "../../src/chat/web-activity-model"
import type {
  HtmlDep,
  WebFetchBlock,
  WebSearchBlock,
  WebSearchResultsBlock,
} from "../../src/transport/types"

const useAutoScrollMock = vi.mocked(useAutoScroll)

function lastContentDependency(): unknown {
  const calls = useAutoScrollMock.mock.calls
  return calls[calls.length - 1]?.[0]?.contentDependency
}

const htmlBlock = (content: string, htmlDeps: HtmlDep[] = []): HtmlBlock => ({
  type: "html_block",
  content,
  contentType: "html",
  htmlDeps,
})

const webSearchBlock = (
  overrides: Partial<WebSearchBlock> = {},
): WebSearchBlock => ({
  type: "web_search",
  version: 1,
  query: "weather in Duluth",
  ...overrides,
})

const webSearchResultsBlock = (
  overrides: Partial<WebSearchResultsBlock> = {},
): WebSearchResultsBlock => ({
  type: "web_search_results",
  version: 1,
  sources: [
    { url: "https://example.com/weather", title: "Duluth weather" },
    { url: "https://example.org/forecast" },
  ],
  ...overrides,
})

const webFetchBlock = (
  overrides: Partial<WebFetchBlock> = {},
): WebFetchBlock => ({
  type: "web_fetch",
  version: 1,
  url: "https://example.net/article",
  status: "success",
  ...overrides,
})

/** Render a MarkdownStream and capture its API. */
function renderStream(autoScroll = false) {
  let api: MarkdownStreamApi | undefined
  const rendered = render(
    <MarkdownStream
      autoScroll={autoScroll}
      onApiReady={(value) => {
        api = value
      }}
    />,
  )
  return { ...rendered, getApi: () => api }
}

describe("MarkdownStream", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("re-scans for a scroll parent as content grows", () => {
    let api: MarkdownStreamApi | undefined
    const scrollParent = document.createElement("div")

    findScrollableParent.mockReturnValueOnce(null)

    render(
      <ShinyLifecycleContext.Provider
        value={{
          bindAll: vi.fn(async () => {}),
          unbindAll: vi.fn(),
          renderDependencies: vi.fn(async () => {}),
          showClientMessage: vi.fn(),
        }}
      >
        <MarkdownStream
          autoScroll={true}
          onApiReady={(value) => {
            api = value
          }}
        />
      </ShinyLifecycleContext.Provider>,
    )

    expect(findScrollableParent).toHaveBeenCalled()
    expect(containerRef).not.toHaveBeenCalledWith(scrollParent)

    findScrollableParent.mockReturnValue(scrollParent)

    act(() => {
      api?.appendContent("streamed content")
    })

    expect(containerRef).toHaveBeenCalledWith(scrollParent)
  })

  it("settles pinnedness before an appended chunk reaches the DOM", () => {
    // posit-dev/py-shiny#2378: pinnedness has to be decided while the DOM still
    // holds the pre-growth scrollHeight, otherwise the grown content makes the
    // user's at-bottom position read as "scrolled away".
    let api: MarkdownStreamApi | undefined
    let domAtRepinTime: string | undefined

    repinIfAtBottom.mockImplementation(() => {
      domAtRepinTime = container.textContent ?? ""
    })

    const { container } = render(
      <ShinyLifecycleContext.Provider
        value={{
          bindAll: vi.fn(async () => {}),
          unbindAll: vi.fn(),
          renderDependencies: vi.fn(async () => {}),
          showClientMessage: vi.fn(),
        }}
      >
        <MarkdownStream
          autoScroll={true}
          onApiReady={(value) => {
            api = value
          }}
        />
      </ShinyLifecycleContext.Provider>,
    )

    act(() => {
      api?.appendContent("streamed chunk")
    })

    expect(repinIfAtBottom).toHaveBeenCalledTimes(1)
    expect(domAtRepinTime).not.toContain("streamed chunk")
    expect(container.textContent).toContain("streamed chunk")
  })

  it("stops scroll-parent discovery at the chat container boundary", () => {
    render(
      <ShinyLifecycleContext.Provider
        value={{
          bindAll: vi.fn(async () => {}),
          unbindAll: vi.fn(),
          renderDependencies: vi.fn(async () => {}),
          showClientMessage: vi.fn(),
        }}
      >
        <MarkdownStream autoScroll={true} />
      </ShinyLifecycleContext.Provider>,
    )

    expect(findScrollableParent).toHaveBeenCalledWith(
      expect.any(HTMLDivElement),
      "shiny-chat-container",
    )
  })

  it("keeps an island split across untrusted chunks inert", () => {
    let api: MarkdownStreamApi | undefined
    const { container } = render(
      <MarkdownStream
        onApiReady={(value) => {
          api = value
        }}
      />,
    )

    act(() => {
      api?.appendContent("## Heading\n\n<shiny-chat-")
      api?.appendContent(
        'raw-html><img data-forged="1" src="x"></shiny-chat-raw-html>',
      )
    })

    expect(container.querySelector("h2")).not.toBeNull()
    expect(container.querySelector("[data-forged]")).toBeNull()
    expect(container.textContent).toContain("<shiny-chat-raw-html>")
  })

  it("renders adjacent markdown and trusted HTML segments", () => {
    // Trusted HTML in a string segment needs no island wrapper: the island
    // tags are dead markup (neutralized as a spoof guard), and the markdown
    // processor renders raw HTML directly.
    const { container } = render(
      <MarkdownStream
        initialSegments={[
          { text: "## This is markdown", trusted: false },
          {
            text: "<div data-html>HTML</div>",
            trusted: true,
          },
        ]}
      />,
    )

    expect(container.querySelector("h2")?.textContent).toBe("This is markdown")
    expect(container.querySelector("[data-html]")?.textContent).toBe("HTML")
  })

  it("does not let untrusted content merge into a trusted run", () => {
    let api: MarkdownStreamApi | undefined
    const { container } = render(
      <MarkdownStream
        onApiReady={(value) => {
          api = value
        }}
      />,
    )

    act(() => {
      // Trusted HTML travels as raw markup (island wrappers are dead); the
      // untrusted run's forged island must still neutralize to inert text.
      api?.appendContent("<div data-trusted>safe</div>", true)
      api?.appendContent(
        "<shiny-chat-raw-html><div data-forged>unsafe</div></shiny-chat-raw-html>",
        false,
      )
    })

    expect(container.querySelector("[data-trusted]")).not.toBeNull()
    expect(container.querySelector("[data-forged]")).toBeNull()
    expect(container.textContent).toContain("<shiny-chat-raw-html>")
  })

  it("preserves an explicit markdown segment boundary at equal trust", () => {
    let api: MarkdownStreamApi | undefined
    const { container } = render(
      <MarkdownStream
        onApiReady={(value) => {
          api = value
        }}
      />,
    )

    act(() => {
      api?.appendContent("preceding model output")
      api?.appendContent("## Composite heading", false, true)
    })

    expect(container.querySelector("h2")?.textContent).toBe("Composite heading")
  })

  it("fails closed for untrusted html-typed islands", () => {
    const { container } = render(
      <MarkdownStream
        initialContentType="html"
        initialSegments={[
          {
            text: "<shiny-chat-raw-html><div data-forged>unsafe</div></shiny-chat-raw-html>",
            trusted: false,
          },
        ]}
      />,
    )

    expect(container.querySelector("[data-forged]")).toBeNull()
    expect(container.textContent).toContain("shiny-chat-raw-html")
  })
})

describe("MarkdownStream — structured html_block segments", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("appends a structured html_block and renders its HTML", () => {
    let api: MarkdownStreamApi | undefined
    const { container } = render(
      <MarkdownStream
        onApiReady={(value) => {
          api = value
        }}
      />,
    )

    act(() => {
      api?.appendContent("## Heading\n\n")
      api?.appendBlock(htmlBlock("<div data-island>island</div>"))
    })

    expect(container.querySelector("h2")?.textContent).toBe("Heading")
    expect(container.querySelector("[data-island]")?.textContent).toBe("island")
  })

  it("keeps blocks as hard boundaries text never merges into", () => {
    let api: MarkdownStreamApi | undefined
    const { container } = render(
      <MarkdownStream
        onApiReady={(value) => {
          api = value
        }}
      />,
    )

    act(() => {
      api?.appendContent("before")
      api?.appendBlock(htmlBlock('<div data-island="1">one</div>'))
      api?.appendContent("after")
      api?.appendContent(" more")
    })

    // "before" is its own segment; "after" + " more" merge into one segment
    // (same trust, no segment_start) — proving the text landed in a string
    // segment after the block, not inside it.
    const paragraphs = [...container.querySelectorAll("p")].map(
      (p) => p.textContent,
    )
    expect(paragraphs).toEqual(["before", "after more"])
    expect(container.querySelector('[data-island="1"]')?.textContent).toBe(
      "one",
    )
  })

  it("replaceWithBlock wipes all prior segments and blocks", () => {
    let api: MarkdownStreamApi | undefined
    const { container } = render(
      <MarkdownStream
        onApiReady={(value) => {
          api = value
        }}
      />,
    )

    act(() => {
      api?.appendContent("before text")
      api?.appendBlock(htmlBlock('<div data-island="old">old</div>'))
    })
    act(() => {
      api?.replaceWithBlock(htmlBlock('<div data-island="new">new</div>'))
    })

    expect(container.textContent).not.toContain("before text")
    expect(container.querySelector('[data-island="old"]')).toBeNull()
    expect(container.querySelector('[data-island="new"]')?.textContent).toBe(
      "new",
    )
  })

  it("a string replace wipes prior blocks too", () => {
    let api: MarkdownStreamApi | undefined
    const { container } = render(
      <MarkdownStream
        onApiReady={(value) => {
          api = value
        }}
      />,
    )

    act(() => {
      api?.appendBlock(htmlBlock('<div data-island="old">old</div>'))
    })
    act(() => {
      api?.replaceContent("fresh text")
    })

    expect(container.querySelector('[data-island="old"]')).toBeNull()
    expect(container.textContent).toContain("fresh text")
  })

  it("renders initial segments carrying structured blocks", () => {
    const { container } = render(
      <MarkdownStream
        initialSegments={[
          { text: "## Markdown", trusted: false },
          htmlBlock("<div data-island>HTML</div>"),
        ]}
      />,
    )

    expect(container.querySelector("h2")?.textContent).toBe("Markdown")
    expect(container.querySelector("[data-island]")?.textContent).toBe("HTML")
  })

  it("settles pinnedness before an appended block reaches the DOM", () => {
    // Same race as appended chunks (posit-dev/py-shiny#2378): a block grows
    // the DOM just like a text chunk, so pinnedness must be settled first.
    let api: MarkdownStreamApi | undefined
    let domAtRepinTime: string | undefined

    repinIfAtBottom.mockImplementation(() => {
      domAtRepinTime = container.textContent ?? ""
    })

    const { container } = render(
      <MarkdownStream
        autoScroll={true}
        onApiReady={(value) => {
          api = value
        }}
      />,
    )

    act(() => {
      api?.appendBlock(htmlBlock("<div data-island>block html</div>"))
    })

    expect(repinIfAtBottom).toHaveBeenCalledTimes(1)
    expect(domAtRepinTime).not.toContain("block html")
    expect(container.textContent).toContain("block html")
  })

  it("renders block dependencies before mounting the island HTML", async () => {
    let resolveDeps: (() => void) | undefined
    const renderDependencies = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveDeps = resolve
        }),
    )
    const dep = { name: "testlib", version: "1.0" } as unknown as HtmlDep

    let api: MarkdownStreamApi | undefined
    const { container } = render(
      <ShinyLifecycleContext.Provider
        value={{
          bindAll: vi.fn(async () => {}),
          unbindAll: vi.fn(),
          renderDependencies,
          showClientMessage: vi.fn(),
        }}
      >
        <MarkdownStream
          onApiReady={(value) => {
            api = value
          }}
        />
      </ShinyLifecycleContext.Provider>,
    )

    act(() => {
      api?.appendBlock(htmlBlock("<div data-island>deferred</div>", [dep]))
    })

    expect(renderDependencies).toHaveBeenCalledWith([dep])
    expect(container.querySelector("[data-island]")).toBeNull()

    await act(async () => {
      resolveDeps?.()
    })

    expect(container.querySelector("[data-island]")?.textContent).toBe(
      "deferred",
    )
  })

  it("re-runs scroll discovery and auto-scroll when a deps-gated block mounts", async () => {
    // A deps-gated block renders nothing until its dependencies resolve;
    // when it finally mounts, `segments` doesn't change, so the scroll
    // logic keyed on segments alone would never re-run for the growth.
    let resolveDeps: (() => void) | undefined
    const renderDependencies = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveDeps = resolve
        }),
    )
    const dep = { name: "testlib", version: "1.0" } as unknown as HtmlDep

    let api: MarkdownStreamApi | undefined
    const { container } = render(
      <ShinyLifecycleContext.Provider
        value={{
          bindAll: vi.fn(async () => {}),
          unbindAll: vi.fn(),
          renderDependencies,
          showClientMessage: vi.fn(),
        }}
      >
        <MarkdownStream
          autoScroll={true}
          onApiReady={(value) => {
            api = value
          }}
        />
      </ShinyLifecycleContext.Provider>,
    )

    act(() => {
      api?.appendBlock(htmlBlock("<div data-island>deferred</div>", [dep]))
    })

    // Gated: the block's HTML has not mounted yet.
    expect(container.querySelector("[data-island]")).toBeNull()

    const discoveryCallsBeforeMount = findScrollableParent.mock.calls.length
    const contentDepBeforeMount = lastContentDependency()

    await act(async () => {
      resolveDeps?.()
    })

    expect(container.querySelector("[data-island]")?.textContent).toBe(
      "deferred",
    )
    // The deferred mount re-ran scroll-parent discovery and handed
    // useAutoScroll a fresh content dependency.
    expect(findScrollableParent.mock.calls.length).toBeGreaterThan(
      discoveryCallsBeforeMount,
    )
    expect(lastContentDependency()).not.toBe(contentDepBeforeMount)
  })
})

describe("MarkdownStream — structured web_* blocks", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("groups a search/results/fetch burst into one rendered activity", () => {
    const { container, getApi } = renderStream()

    act(() => {
      getApi()?.appendContent("Before the burst. ")
      getApi()?.appendBlock(webSearchBlock())
      getApi()?.appendBlock(webSearchResultsBlock())
      getApi()?.appendBlock(webFetchBlock())
      getApi()?.appendContent(" After the burst.")
    })

    // One grouped activity between the two prose segments.
    expect(container.querySelectorAll(".shiny-web-activity")).toHaveLength(1)
    const text = container.textContent ?? ""
    expect(text.indexOf("Before the burst.")).toBeLessThan(
      text.indexOf("Searched the web"),
    )
    expect(text.indexOf("Searched the web")).toBeLessThan(
      text.indexOf("After the burst."),
    )

    // The results block paired with the pending search; the fetch appended
    // a standalone item (the shared appendWebActivityBlock semantics).
    fireEvent.click(container.querySelector(".shiny-web-activity__header")!)
    expect(
      container.querySelector(".shiny-web-activity__query")?.textContent,
    ).toBe("weather in Duluth")
    expect(
      container.querySelector(".shiny-web-activity__count")?.textContent,
    ).toBe("2 results")
    expect(
      container.querySelector(".shiny-web-activity__fetch")?.textContent,
    ).toContain("https://example.net/article")
  })

  it("tolerates a whitespace-only text segment between carriers", () => {
    const { container, getApi } = renderStream()

    act(() => {
      getApi()?.appendBlock(webSearchBlock())
      getApi()?.appendContent(" \n")
      getApi()?.appendBlock(webFetchBlock())
    })

    // The whitespace separator is dropped; the fetch joins the activity.
    expect(container.querySelectorAll(".shiny-web-activity")).toHaveLength(1)
    fireEvent.click(container.querySelector(".shiny-web-activity__header")!)
    expect(
      container.querySelector(".shiny-web-activity__query")?.textContent,
    ).toBe("weather in Duluth")
    expect(
      container.querySelector(".shiny-web-activity__fetch")?.textContent,
    ).toContain("https://example.net/article")
  })

  it("ends the activity run when prose intervenes", () => {
    const { container, getApi } = renderStream()

    act(() => {
      getApi()?.appendBlock(webSearchBlock())
      getApi()?.appendContent(" Some prose. ")
      getApi()?.appendBlock(webFetchBlock())
    })

    const activities = container.querySelectorAll(".shiny-web-activity")
    expect(activities).toHaveLength(2)
    // The first run holds the (still-pending) search; the second the fetch.
    expect(activities[0]!.textContent).toContain("Searched the web")
    expect(activities[1]!.textContent).toContain("Read the web")
  })

  it("keeps web blocks as hard boundaries text never merges across", () => {
    const { container, getApi } = renderStream()

    act(() => {
      getApi()?.appendContent("before")
      getApi()?.appendBlock(webSearchBlock())
      getApi()?.appendContent("after")
      getApi()?.appendContent(" more")
    })

    // "before" is its own segment; "after" + " more" merge into one segment
    // after the block — proving text landed around the block, not in it.
    const paragraphs = [...container.querySelectorAll("p")].map(
      (p) => p.textContent,
    )
    expect(paragraphs).toEqual(["before", "after more"])
    expect(container.querySelectorAll(".shiny-web-activity")).toHaveLength(1)
  })

  it("replaceWithBlock with a web block wipes all prior segments and blocks", () => {
    const { container, getApi } = renderStream()

    act(() => {
      getApi()?.appendContent("before text")
      getApi()?.appendBlock(webSearchBlock())
      getApi()?.appendBlock(htmlBlock('<div data-island="old">old</div>'))
    })
    act(() => {
      getApi()?.replaceWithBlock(webFetchBlock())
    })

    expect(container.textContent).not.toContain("before text")
    expect(container.querySelector('[data-island="old"]')).toBeNull()
    // The replaced web block starts a fresh fetch-only activity.
    const activities = container.querySelectorAll(".shiny-web-activity")
    expect(activities).toHaveLength(1)
    expect(activities[0]!.textContent).toContain("Read the web")
    expect(activities[0]!.textContent).not.toContain("Searched the web")
  })

  it("a string replace wipes prior web activity blocks too", () => {
    const { container, getApi } = renderStream()

    act(() => {
      getApi()?.appendBlock(webSearchBlock())
    })
    act(() => {
      getApi()?.replaceContent("fresh text")
    })

    expect(container.querySelector(".shiny-web-activity")).toBeNull()
    expect(container.textContent).toContain("fresh text")
  })

  it("renders initial segments carrying a web_activity block", () => {
    const activity: WebActivityBlock = {
      type: "web_activity",
      items: [
        {
          kind: "search",
          query: "weather in Duluth",
          sources: null,
          citedSources: [],
        },
      ],
    }
    const { container } = render(
      <MarkdownStream
        initialSegments={[{ text: "## Markdown", trusted: false }, activity]}
      />,
    )

    expect(container.querySelector("h2")?.textContent).toBe("Markdown")
    expect(
      container.querySelector(".shiny-web-activity")?.textContent,
    ).toContain("Searched the web")
  })

  it("settles pinnedness before an appended web block reaches the DOM", () => {
    // Same race as appended chunks (posit-dev/py-shiny#2378): a web block
    // grows the DOM just like a text chunk, so pinnedness must be settled
    // first.
    let domAtRepinTime: string | undefined
    repinIfAtBottom.mockImplementation(() => {
      domAtRepinTime = container.textContent ?? ""
    })

    const { container, getApi } = renderStream(true)

    act(() => {
      getApi()?.appendBlock(webSearchBlock())
    })

    expect(repinIfAtBottom).toHaveBeenCalledTimes(1)
    expect(domAtRepinTime).not.toContain("Searched the web")
    expect(container.textContent).toContain("Searched the web")
  })
})

describe("MarkdownStream — inline asides", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const asideMarkdown = [
    "A claim.",
    "",
    "<shiny-aside>Details</shiny-aside>",
  ].join("\n")

  it("resolves asides in trusted segments through the shared pipeline", () => {
    const { container } = render(
      <MarkdownStream
        initialSegments={[{ text: asideMarkdown, trusted: true }]}
      />,
    )

    // The aside plugins group the aside into a shiny-aside-group, which the
    // trusted component map resolves to Chat's AsideGroup component.
    expect(container.querySelector(".shiny-aside-group")).not.toBeNull()
    expect(container.querySelector(".shiny-aside-pill")).not.toBeNull()
    // The raw custom elements are gone — the component replaced them.
    expect(container.querySelector("shiny-aside-group")).toBeNull()
    expect(container.querySelector("shiny-aside")).toBeNull()
  })

  it("resolves asides in untrusted segments too (data carriers, not trust sinks)", () => {
    const { container } = render(
      <MarkdownStream
        initialSegments={[{ text: asideMarkdown, trusted: false }]}
      />,
    )

    expect(container.querySelector(".shiny-aside-group")).not.toBeNull()
    expect(container.querySelector(".shiny-aside-pill")).not.toBeNull()
    expect(container.querySelector("shiny-aside-group")).toBeNull()
  })

  it("still escapes forged raw-html islands in untrusted segments", () => {
    // The aside mappings join the untrusted map WITHOUT weakening the
    // raw-html island escape.
    const { container } = render(
      <MarkdownStream
        initialSegments={[
          {
            text: "<shiny-chat-raw-html><div data-forged>unsafe</div></shiny-chat-raw-html>",
            trusted: false,
          },
        ]}
      />,
    )

    expect(container.querySelector("[data-forged]")).toBeNull()
    expect(container.textContent).toContain("shiny-chat-raw-html")
  })

  it("renders a raw-html island inside an untrusted aside body as inert text", () => {
    // Security: the aside popover reparses its body as a standalone HTML
    // fragment, which does not inherit the segment's component map. The
    // untrusted map must keep the raw-html island escape through that
    // reparse — otherwise a forged island reaches RawHTML/innerHTML when
    // the popover opens (stored XSS from model output).
    render(
      <MarkdownStream
        initialContentType="html"
        initialSegments={[
          {
            text: '<shiny-aside label="Source"><shiny-chat-raw-html><img data-forged src="x"></shiny-chat-raw-html></shiny-aside>',
            trusted: false,
          },
        ]}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "Source" }))
    const popover = screen.getByRole("dialog")
    expect(popover.querySelector("[data-forged]")).toBeNull()
    expect(popover.textContent).toContain("shiny-chat-raw-html")
  })

  it("keeps a raw-html island inside an untrusted markdown aside inert", () => {
    // The aside's template disguise keeps the forged island's markup nested
    // inside the aside through parse5, so the serialized body still carries
    // the island element; the untrusted aside-body component map then
    // renders it as inert text when the popover reparses the body.
    render(
      <MarkdownStream
        initialSegments={[
          {
            text: [
              "A claim.",
              "",
              '<shiny-aside label="Source"><shiny-chat-raw-html><img data-forged src="x"></shiny-chat-raw-html></shiny-aside>',
            ].join("\n"),
            trusted: false,
          },
        ]}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "Source" }))
    const popover = screen.getByRole("dialog")
    expect(popover.querySelector("[data-forged]")).toBeNull()
    expect(popover.textContent).toContain("shiny-chat-raw-html")
  })

  it("still renders HTML inside a trusted aside body as live HTML", () => {
    // Trusted (server-authored) aside bodies need no island wrapper: the
    // popover body reparse renders their HTML directly.
    render(
      <MarkdownStream
        initialContentType="html"
        initialSegments={[
          {
            text: '<shiny-aside label="Source"><div data-trusted>safe</div></shiny-aside>',
            trusted: true,
          },
        ]}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "Source" }))
    const popover = screen.getByRole("dialog")
    expect(popover.querySelector("[data-trusted]")?.textContent).toBe("safe")
  })
})
