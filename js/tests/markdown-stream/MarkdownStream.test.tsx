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
    // posit-dev/py-shiny#2378: pinnedness must be settled before the DOM grows.
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
    // posit-dev/py-shiny#2378: pinnedness must be settled before the DOM grows.
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

    expect(container.querySelector("[data-island]")).toBeNull()

    const discoveryCallsBeforeMount = findScrollableParent.mock.calls.length
    const contentDepBeforeMount = lastContentDependency()

    await act(async () => {
      resolveDeps?.()
    })

    expect(container.querySelector("[data-island]")?.textContent).toBe(
      "deferred",
    )
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

    expect(container.querySelectorAll(".shiny-web-activity")).toHaveLength(1)
    const text = container.textContent ?? ""
    expect(text.indexOf("Before the burst.")).toBeLessThan(
      text.indexOf("Searched the web"),
    )
    expect(text.indexOf("Searched the web")).toBeLessThan(
      text.indexOf("After the burst."),
    )

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

    expect(container.querySelector(".shiny-aside-group")).not.toBeNull()
    expect(container.querySelector(".shiny-aside-pill")).not.toBeNull()
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
