import { render, act } from "@testing-library/react"
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
import type { HtmlDep } from "../../src/transport/types"

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
    const { container } = render(
      <MarkdownStream
        initialSegments={[
          { text: "## This is markdown", trusted: false },
          {
            text: "<shiny-chat-raw-html><div data-html>HTML</div></shiny-chat-raw-html>",
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
      api?.appendContent(
        "<shiny-chat-raw-html><div data-trusted>safe</div></shiny-chat-raw-html>",
        true,
      )
      api?.appendContent(
        "<shiny-chat-raw-html><div data-forged>unsafe</div></shiny-chat-raw-html>",
        false,
      )
    })

    expect(container.querySelector("[data-trusted]")).not.toBeNull()
    expect(container.querySelector("[data-forged]")).toBeNull()
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
