import { describe, it, expect, vi } from "vitest"
import { render, fireEvent } from "@testing-library/react"
import { TextAttachmentPreview } from "../../src/chat/TextAttachmentPreview"

const url = (s: string) => `data:text/plain;base64,${btoa(s)}`

describe("TextAttachmentPreview", () => {
  it("renders the decoded preview body, filename and size", () => {
    const { container } = render(
      <TextAttachmentPreview
        dataUrl={url("# Project Notes\nbody")}
        name="notes.md"
        size={2400}
      />,
    )
    const card = container.querySelector(".shiny-chat-text-preview")
    expect(card).not.toBeNull()
    expect(card!.textContent).toContain("# Project Notes")
    expect(card!.textContent).toContain("notes.md")
    expect(card!.textContent).toContain("2.4 KB")
  })
  it("renders a remove button only when onRemove is provided", () => {
    const onRemove = vi.fn()
    const { container, rerender } = render(
      <TextAttachmentPreview dataUrl={url("x")} name="a.txt" size={1} />,
    )
    expect(container.querySelector("button")).toBeNull()
    rerender(
      <TextAttachmentPreview
        dataUrl={url("x")}
        name="a.txt"
        size={1}
        onRemove={onRemove}
      />,
    )
    expect(container.querySelector("button")).not.toBeNull()
    fireEvent.click(container.querySelector("button")!)
    expect(onRemove).toHaveBeenCalledOnce()
  })
  it("shows an (empty file) placeholder when there is no text", () => {
    const { container } = render(
      <TextAttachmentPreview
        dataUrl="data:text/plain;base64,"
        name="empty.txt"
        size={0}
      />,
    )
    expect(
      container.querySelector(".shiny-chat-text-preview-body")!.textContent,
    ).toContain("(empty file)")
  })
  it("is not activatable by default (no role=button)", () => {
    const { container } = render(
      <TextAttachmentPreview dataUrl={url("x")} name="a.txt" size={1} />,
    )
    expect(
      container.querySelector(".shiny-chat-text-preview")!.getAttribute("role"),
    ).toBeNull()
  })
  it("activates on click and Enter/Space when onActivate is provided", () => {
    const onActivate = vi.fn()
    const { container } = render(
      <TextAttachmentPreview
        dataUrl={url("x")}
        name="a.txt"
        size={1}
        onActivate={onActivate}
      />,
    )
    const card = container.querySelector(".shiny-chat-text-preview")!
    expect(card.getAttribute("role")).toBe("button")
    expect(card.getAttribute("tabindex")).toBe("0")
    fireEvent.click(card)
    fireEvent.keyDown(card, { key: "Enter" })
    fireEvent.keyDown(card, { key: " " })
    expect(onActivate).toHaveBeenCalledTimes(3)
  })
})
