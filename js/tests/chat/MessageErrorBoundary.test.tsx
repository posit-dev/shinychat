import { describe, it, expect, vi } from "vitest"
import { render } from "@testing-library/react"
import { MessageErrorBoundary } from "../../src/chat/MessageErrorBoundary"

function ThrowingChild(): never {
  throw new Error("render failure")
}

describe("MessageErrorBoundary", () => {
  it("renders children when no error occurs", () => {
    const { getByText } = render(
      <MessageErrorBoundary>
        <div>OK content</div>
      </MessageErrorBoundary>,
    )
    expect(getByText("OK content")).toBeTruthy()
  })

  it("renders fallback when child throws", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {})
    vi.spyOn(console, "error").mockImplementation(() => {})

    const { getByRole } = render(
      <MessageErrorBoundary>
        <ThrowingChild />
      </MessageErrorBoundary>,
    )
    expect(getByRole("alert")).toBeTruthy()
    expect(getByRole("alert").textContent).toContain("Error rendering message")

    vi.restoreAllMocks()
  })
})
