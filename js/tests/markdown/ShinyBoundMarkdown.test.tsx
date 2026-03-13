import { describe, it, expect, vi } from "vitest"
import { render, act } from "@testing-library/react"
import type { ReactNode } from "react"
import type { ShinyLifecycle } from "../../src/transport/types"
import { ShinyLifecycleContext } from "../../src/chat/context"
import { ShinyBoundMarkdown } from "../../src/markdown/ShinyBoundMarkdown"
import { createMockShinyLifecycle } from "../helpers/mocks"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function Wrapper({
  shiny,
  children,
}: {
  shiny: ShinyLifecycle
  children: ReactNode
}) {
  return (
    <ShinyLifecycleContext.Provider value={shiny}>
      {children}
    </ShinyLifecycleContext.Provider>
  )
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ShinyBoundMarkdown", () => {
  it("renders MarkdownContent inside a container div", () => {
    const shiny = createMockShinyLifecycle()
    const { container } = render(
      <Wrapper shiny={shiny}>
        <ShinyBoundMarkdown content="**bold**" contentType="markdown" />
      </Wrapper>,
    )
    // ShinyBoundMarkdown wraps in a div; the markdown should produce <strong>
    expect(container.querySelector("strong")).not.toBeNull()
  })

  it("calls bindAll after rendering content", async () => {
    const shiny = createMockShinyLifecycle()
    await act(async () => {
      render(
        <Wrapper shiny={shiny}>
          <ShinyBoundMarkdown content="hello" contentType="markdown" />
        </Wrapper>,
      )
    })
    expect(shiny.bindAll).toHaveBeenCalled()
  })

  it("calls unbindAll on unmount", async () => {
    const shiny = createMockShinyLifecycle()
    let unmount!: () => void
    await act(async () => {
      const result = render(
        <Wrapper shiny={shiny}>
          <ShinyBoundMarkdown content="hello" contentType="markdown" />
        </Wrapper>,
      )
      unmount = result.unmount
    })
    act(() => {
      unmount()
    })
    expect(shiny.unbindAll).toHaveBeenCalled()
  })

  it("calls onStreamEnd when streaming transitions true → false", () => {
    const shiny = createMockShinyLifecycle()
    const onStreamEnd = vi.fn()

    const { rerender } = render(
      <Wrapper shiny={shiny}>
        <ShinyBoundMarkdown
          content="hello"
          contentType="markdown"
          streaming={true}
          onStreamEnd={onStreamEnd}
        />
      </Wrapper>,
    )

    expect(onStreamEnd).not.toHaveBeenCalled()

    rerender(
      <Wrapper shiny={shiny}>
        <ShinyBoundMarkdown
          content="hello"
          contentType="markdown"
          streaming={false}
          onStreamEnd={onStreamEnd}
        />
      </Wrapper>,
    )

    expect(onStreamEnd).toHaveBeenCalledTimes(1)
  })

  it("calls onContentChange when content changes", () => {
    const shiny = createMockShinyLifecycle()
    const onContentChange = vi.fn()

    const { rerender } = render(
      <Wrapper shiny={shiny}>
        <ShinyBoundMarkdown
          content="hello"
          contentType="markdown"
          onContentChange={onContentChange}
        />
      </Wrapper>,
    )

    // Initial render triggers onContentChange
    const initialCalls = onContentChange.mock.calls.length

    rerender(
      <Wrapper shiny={shiny}>
        <ShinyBoundMarkdown
          content="hello world"
          contentType="markdown"
          onContentChange={onContentChange}
        />
      </Wrapper>,
    )

    expect(onContentChange.mock.calls.length).toBeGreaterThan(initialCalls)
  })
})
