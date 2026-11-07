import { describe, it, expect, vi } from "vitest"
import { render, fireEvent } from "@testing-library/react"
import { ToolResult } from "../../src/chat/ToolResult"
import { ChatScrollContext } from "../../src/chat/context"

describe("ToolResult", () => {
  it("disengages the outer chat's stick-to-bottom before toggling the long tool-call preview", () => {
    // The "Tool call" argument preview collapses into a native <details> when
    // long. Opening it resizes the chat message list exactly like the card
    // itself, so it needs the same guard against the outer auto-scroll.
    const stopScroll = vi.fn()
    const requestCall = "line 1\nline 2\nline 3"
    const { container } = render(
      <ChatScrollContext.Provider value={stopScroll}>
        <ToolResult
          toolName="my_tool"
          status="success"
          value="result"
          valueType="text"
          requestCall={requestCall}
          showRequest={true}
        />
      </ChatScrollContext.Provider>,
    )
    const details = container.querySelector("details") as HTMLDetailsElement
    expect(details).toBeTruthy()
    fireEvent(details, new Event("toggle", { bubbles: false }))
    expect(stopScroll).toHaveBeenCalled()
  })

  it("renders the request call in the expanded card", () => {
    const { container } = render(
      <ToolResult
        toolName="my_tool"
        status="success"
        value="done"
        valueType="text"
        requestCall={"my_tool(x = 1)"}
        showRequest={true}
        initialExpanded={true}
      />,
    )
    expect(container.textContent).toContain("my_tool(x = 1)")
  })

  // Regression: a server once sent request_call as an array of wrapped lines;
  // requestCall.split() threw and the per-message boundary wiped the whole
  // chat message. The card body boundary must contain it instead.
  it("a malformed requestCall degrades the card body, not the card", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {})
    vi.spyOn(console, "error").mockImplementation(() => {})

    const { container, getByRole } = render(
      <ToolResult
        toolName="my_tool"
        status="success"
        value="done"
        valueType="text"
        requestCall={["my_tool(", "  x = 1)"] as unknown as string}
        showRequest={true}
        initialExpanded={true}
      />,
    )

    const header = container.querySelector(".card-header")
    expect(header).toBeTruthy()
    expect(header!.textContent).toContain("my_tool")
    expect(getByRole("alert").textContent).toContain("couldn’t be displayed")
  })

  it("recovers when a malformed requestCall is corrected with an unchanged value", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {})
    vi.spyOn(console, "error").mockImplementation(() => {})

    const props = {
      toolName: "my_tool",
      status: "success",
      value: "done",
      valueType: "text",
      showRequest: true,
      initialExpanded: true,
    }
    const { rerender, getByRole, queryByRole, container } = render(
      <ToolResult
        {...props}
        requestCall={["my_tool(", "  x = 1)"] as unknown as string}
      />,
    )
    expect(getByRole("alert")).toBeTruthy()

    // Same result value, corrected request call: the body must retry.
    rerender(<ToolResult {...props} requestCall={"my_tool(x = 1)"} />)
    expect(queryByRole("alert")).toBeNull()
    expect(container.textContent).toContain("my_tool(x = 1)")
  })

  it("renders the details slot as a collapsible disclosure above the result body", () => {
    const { container } = render(
      <ToolResult
        toolName="send"
        status="success"
        value="42"
        valueType="text"
        requestCall="my_tool(x = 1)"
        showRequest={true}
        initialExpanded={true}
        details="<pre><code>1 + 1</code></pre>"
        detailsSummary="Code"
        detailsOpen={false}
      />,
    )
    const wrapper = container.querySelector(".shiny-tool-result__details")
    expect(wrapper).toBeTruthy()
    const details = wrapper!.querySelector("details") as HTMLDetailsElement
    expect(details).toBeTruthy()
    expect(details.open).toBe(false)
    expect(details.querySelector("summary")?.textContent).toBe("Code")
    expect(details.textContent).toContain("1 + 1")

    // The slot sits above the result body (below the request section).
    const request = container.querySelector(".shiny-tool-result__request")
    const result = container.querySelector(".shiny-tool-result__result")
    expect(request).toBeTruthy()
    expect(result).toBeTruthy()
    expect(
      request!.compareDocumentPosition(wrapper!) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(
      wrapper!.compareDocumentPosition(result!) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it("honors detailsOpen and defaults the summary label to 'Details'", () => {
    const { container } = render(
      <ToolResult
        toolName="send"
        status="success"
        value="42"
        valueType="text"
        details="<pre><code>1 + 1</code></pre>"
        detailsOpen={true}
      />,
    )
    const details = container.querySelector(
      ".shiny-tool-result__details details",
    ) as HTMLDetailsElement
    expect(details.open).toBe(true)
    expect(details.querySelector("summary")?.textContent).toBe("Details")
  })

  it("highlights language-tagged code blocks in the details slot", () => {
    const { container } = render(
      <ToolResult
        toolName="send"
        status="success"
        value="42"
        valueType="text"
        details='<pre><code class="language-r">plot(1:3)</code></pre>'
      />,
    )
    const code = container.querySelector(".shiny-tool-result__details code")
    expect(code?.className).toContain("hljs")
  })

  it("injects a copy button into html-flavor details <pre> blocks", () => {
    const html = "<pre><code>1 + 1</code></pre>"
    const { container, rerender } = render(
      <ToolResult
        toolName="send"
        status="success"
        value="42"
        valueType="text"
        details={html}
      />,
    )
    const pre = container.querySelector(".shiny-tool-result__details pre")
    const button = pre?.querySelector(".code-copy-button")
    expect(button).toBeTruthy()
    expect(button?.getAttribute("aria-label")).toBe("Copy to clipboard")

    // Re-rendering with unchanged html must not stack a second button
    // (RawHTML re-sets innerHTML; the hook re-runs and the per-pre guard
    // covers any residual).
    rerender(
      <ToolResult
        toolName="send"
        status="success"
        value="42"
        valueType="text"
        details={html}
      />,
    )
    expect(
      container.querySelectorAll(
        ".shiny-tool-result__details pre .code-copy-button",
      ),
    ).toHaveLength(1)
  })

  describe("details row copy button", () => {
    const ROW_COPY = ".shiny-tool-result__details > .code-copy-button"

    function renderDetails(
      details: string,
      opts: { detailsType?: "html" | "markdown"; detailsOpen?: boolean } = {},
    ) {
      return render(
        <ToolResult
          toolName="send"
          status="success"
          value="42"
          valueType="text"
          details={details}
          detailsSummary="Code"
          detailsType={opts.detailsType}
          detailsOpen={opts.detailsOpen ?? true}
        />,
      )
    }

    function toggle(details: HTMLDetailsElement, open: boolean) {
      details.open = open
      fireEvent(details, new Event("toggle", { bubbles: false }))
    }

    it("moves copy into the summary row for a single open code block", async () => {
      const writeText = vi.fn().mockResolvedValue(undefined)
      Object.defineProperty(navigator, "clipboard", {
        value: { writeText },
        configurable: true,
      })
      const { container } = renderDetails("<pre><code>1 + 1</code></pre>")

      const wrapper = container.querySelector(".shiny-tool-result__details")!
      // Keys the CSS that hides the in-block button.
      expect(wrapper.hasAttribute("data-single-code-block")).toBe(true)

      const button = container.querySelector(ROW_COPY) as HTMLButtonElement
      expect(button).toBeTruthy()
      expect(button.getAttribute("aria-label")).toBe("Copy to clipboard")
      // A sibling of <details>, never nested inside the <summary> toggle.
      expect(button.closest("summary")).toBeNull()

      const details = wrapper.querySelector("details") as HTMLDetailsElement
      fireEvent.click(button)
      await vi.waitFor(() => expect(writeText).toHaveBeenCalledWith("1 + 1"))
      expect(details.open).toBe(true)
    })

    it("shows the row button only while the disclosure is open", () => {
      const { container } = renderDetails("<pre><code>1 + 1</code></pre>", {
        detailsOpen: false,
      })
      expect(container.querySelector(ROW_COPY)).toBeNull()

      const details = container.querySelector(
        ".shiny-tool-result__details details",
      ) as HTMLDetailsElement
      toggle(details, true)
      expect(container.querySelector(ROW_COPY)).toBeTruthy()
      toggle(details, false)
      expect(container.querySelector(ROW_COPY)).toBeNull()
    })

    it("applies to a single markdown code block too", () => {
      const { container } = renderDetails("```r\nplot(1:3)\n```", {
        detailsType: "markdown",
      })
      expect(container.querySelector(ROW_COPY)).toBeTruthy()
    })

    it.each([
      [
        "several code blocks",
        "<pre><code>a</code></pre><pre><code>b</code></pre>",
      ],
      ["prose around a code block", "<p>Ran:</p><pre><code>a</code></pre>"],
      ["no code block", "<p>Just prose</p>"],
    ])("keeps per-block copy buttons for %s", (_label, html) => {
      const { container } = renderDetails(html)
      const wrapper = container.querySelector(".shiny-tool-result__details")!
      expect(wrapper.hasAttribute("data-single-code-block")).toBe(false)
      expect(container.querySelector(ROW_COPY)).toBeNull()
    })
  })

  it("renders markdown-type details through the markdown pipeline", () => {
    const { container } = render(
      <ToolResult
        toolName="send"
        status="success"
        value="42"
        valueType="text"
        details="Some **bold** text"
        detailsType="markdown"
      />,
    )
    const slot = container.querySelector(".shiny-tool-result__details")
    expect(slot?.querySelector("strong")?.textContent).toBe("bold")
  })

  it("highlights language-tagged code blocks in html values", () => {
    const { container } = render(
      <ToolResult
        toolName="send"
        status="success"
        value='<pre><code class="language-r">plot(1:3)</code></pre>'
        valueType="html"
        showRequest={false}
        initialExpanded={true}
      />,
    )
    const code = container.querySelector("code")
    expect(code?.className).toContain("hljs")
    expect(code?.innerHTML).toMatch(/<span class="hljs-/)
  })

  it("does not re-parse html values without language classes", () => {
    // A re-serialization round-trip drops one leading newline inside <pre>,
    // and the DOM parser drops another on mount. If the value were re-parsed,
    // the rendered text would be "keep", not "\nkeep".
    const html =
      '<div class="author-widget"><b>custom</b></div><pre>\n\nkeep</pre>'
    const { container } = render(
      <ToolResult
        toolName="send"
        status="success"
        value={html}
        valueType="html"
        showRequest={false}
        initialExpanded={true}
      />,
    )
    expect(container.querySelector(".author-widget")?.innerHTML).toBe(
      "<b>custom</b>",
    )
    expect(container.querySelector("pre")?.textContent).toBe("\nkeep")
  })
})
