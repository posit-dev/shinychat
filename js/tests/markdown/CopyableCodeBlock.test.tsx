import { describe, expect, it, vi } from "vitest"
import { render, fireEvent, waitFor } from "@testing-library/react"
import { CopyableCodeBlock } from "../../src/markdown/components/CopyableCodeBlock"

describe("CopyableCodeBlock", () => {
  it("copies the code text and flashes the checked state on click", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    })

    const { container } = render(
      <CopyableCodeBlock>
        <code>x &lt;- 1</code>
      </CopyableCodeBlock>,
    )
    const button = container.querySelector(
      "pre .code-copy-button",
    ) as HTMLButtonElement
    expect(button).toBeTruthy()

    fireEvent.click(button)

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("x <- 1"))
    await waitFor(() =>
      expect(button.classList.contains("code-copy-button-checked")).toBe(true),
    )
  })
})
