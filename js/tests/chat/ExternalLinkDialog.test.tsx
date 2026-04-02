import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { ExternalLinkDialogComponent } from "../../src/chat/ExternalLinkDialog"

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function (
    this: HTMLDialogElement,
  ) {
    this.setAttribute("open", "")
  })
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.removeAttribute("open")
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("ExternalLinkDialogComponent", () => {
  it("displays the URL", () => {
    render(
      <ExternalLinkDialogComponent
        url="https://example.com"
        onProceed={vi.fn()}
        onAlways={vi.fn()}
        onCancel={vi.fn()}
      />,
    )

    expect(screen.getByText("https://example.com")).toBeTruthy()
  })

  it("calls onProceed when 'Open Link' is clicked", () => {
    const onProceed = vi.fn()

    render(
      <ExternalLinkDialogComponent
        url="https://example.com"
        onProceed={onProceed}
        onAlways={vi.fn()}
        onCancel={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByText("Open Link"))
    expect(onProceed).toHaveBeenCalledOnce()
  })

  it("calls onCancel when 'Cancel' is clicked", () => {
    const onCancel = vi.fn()

    render(
      <ExternalLinkDialogComponent
        url="https://example.com"
        onProceed={vi.fn()}
        onAlways={vi.fn()}
        onCancel={onCancel}
      />,
    )

    fireEvent.click(screen.getByText("Cancel"))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it("calls onCancel when the close button (X) is clicked", () => {
    const onCancel = vi.fn()

    render(
      <ExternalLinkDialogComponent
        url="https://example.com"
        onProceed={vi.fn()}
        onAlways={vi.fn()}
        onCancel={onCancel}
      />,
    )

    fireEvent.click(screen.getByLabelText("Close"))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it("calls onAlways when 'Always open external links' is clicked", () => {
    const onAlways = vi.fn()

    render(
      <ExternalLinkDialogComponent
        url="https://example.com"
        onProceed={vi.fn()}
        onAlways={onAlways}
        onCancel={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByText("Always open external links"))
    expect(onAlways).toHaveBeenCalledOnce()
  })

  it("calls onCancel when the backdrop (dialog element itself) is clicked", () => {
    const onCancel = vi.fn()

    const { container } = render(
      <ExternalLinkDialogComponent
        url="https://example.com"
        onProceed={vi.fn()}
        onAlways={vi.fn()}
        onCancel={onCancel}
      />,
    )

    const dialog = container.querySelector("dialog")!
    expect(dialog).toBeTruthy()

    // Clicking the <dialog> element directly simulates a backdrop click:
    // the native listener checks e.target === dialog, which is true here.
    fireEvent.click(dialog)
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it("calls showModal on mount", () => {
    render(
      <ExternalLinkDialogComponent
        url="https://example.com"
        onProceed={vi.fn()}
        onAlways={vi.fn()}
        onCancel={vi.fn()}
      />,
    )

    expect(HTMLDialogElement.prototype.showModal).toHaveBeenCalledOnce()
  })

  it("calls onProceed as fallback when showModal throws", () => {
    HTMLDialogElement.prototype.showModal = vi.fn(() => {
      throw new Error("showModal not supported")
    })

    const onProceed = vi.fn()

    render(
      <ExternalLinkDialogComponent
        url="https://example.com"
        onProceed={onProceed}
        onAlways={vi.fn()}
        onCancel={vi.fn()}
      />,
    )

    expect(onProceed).toHaveBeenCalledOnce()
  })
})
