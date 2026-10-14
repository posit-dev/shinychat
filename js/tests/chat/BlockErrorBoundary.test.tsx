import { describe, it, expect, vi, beforeEach } from "vitest"
import { render } from "@testing-library/react"
import { BlockErrorBoundary } from "../../src/chat/BlockErrorBoundary"

function ThrowingChild(): never {
  throw new Error("render failure")
}

beforeEach(() => {
  vi.spyOn(console, "warn").mockImplementation(() => {})
  vi.spyOn(console, "error").mockImplementation(() => {})
})

describe("BlockErrorBoundary", () => {
  it("renders children when no error occurs", () => {
    const { getByText } = render(
      <BlockErrorBoundary>
        <div>OK content</div>
      </BlockErrorBoundary>,
    )
    expect(getByText("OK content")).toBeTruthy()
  })

  it("renders the default fallback when a child throws", () => {
    const { getByRole } = render(
      <BlockErrorBoundary>
        <ThrowingChild />
      </BlockErrorBoundary>,
    )
    expect(getByRole("alert").textContent).toContain("couldn’t be displayed")
  })

  it("contains the error without affecting siblings", () => {
    const { getByText, getByRole } = render(
      <>
        <BlockErrorBoundary>
          <ThrowingChild />
        </BlockErrorBoundary>
        <BlockErrorBoundary>
          <div>surviving sibling</div>
        </BlockErrorBoundary>
      </>,
    )
    expect(getByRole("alert")).toBeTruthy()
    expect(getByText("surviving sibling")).toBeTruthy()
  })

  it("renders a custom fallback when provided", () => {
    const { getByText } = render(
      <BlockErrorBoundary fallback={<pre>raw content</pre>}>
        <ThrowingChild />
      </BlockErrorBoundary>,
    )
    expect(getByText("raw content")).toBeTruthy()
  })

  it("logs the context label with the error", () => {
    render(
      <BlockErrorBoundary context="tool_result block">
        <ThrowingChild />
      </BlockErrorBoundary>,
    )
    expect(console.warn).toHaveBeenCalledWith(
      "[shinychat] Error rendering tool_result block:",
      expect.any(Error),
      expect.anything(),
    )
  })

  it("resets and retries when resetKey changes after an error", () => {
    function MaybeThrows({ shouldThrow }: { shouldThrow: boolean }) {
      if (shouldThrow) throw new Error("render failure")
      return <div>recovered</div>
    }

    const { rerender, getByRole, getByText, queryByRole } = render(
      <BlockErrorBoundary resetKey="bad">
        <MaybeThrows shouldThrow={true} />
      </BlockErrorBoundary>,
    )
    expect(getByRole("alert")).toBeTruthy()

    // Same resetKey: stays in the error state even after a re-render.
    rerender(
      <BlockErrorBoundary resetKey="bad">
        <MaybeThrows shouldThrow={false} />
      </BlockErrorBoundary>,
    )
    expect(getByRole("alert")).toBeTruthy()

    // New resetKey: resets and retries the children.
    rerender(
      <BlockErrorBoundary resetKey="good">
        <MaybeThrows shouldThrow={false} />
      </BlockErrorBoundary>,
    )
    expect(queryByRole("alert")).toBeNull()
    expect(getByText("recovered")).toBeTruthy()
  })
})
