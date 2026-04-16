# Opaque HTML Islands Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore pre-React stable behavior for `shinychat-raw-html` content by preserving raw island payloads, rendering islands from that preserved payload, and moving stable-era island enhancements to the `RawHTML` DOM boundary.

**Architecture:** Add a post-`rehypeRaw` snapshot plugin that stores each island's original inner HTML on its HAST node. `MarkdownContent` will read that preserved payload instead of serializing `node.children`, and `RawHTML` will call a small DOM helper that applies only stable-style island behaviors (external links, suggestion accessibility, and code highlighting) inside the island root.

**Tech Stack:** React 19, TypeScript, unified/remark/rehype, highlight.js, Vitest, Testing Library

---

## File Structure

### Existing files to modify

- `js/src/markdown/processors.ts`
  - Register a new rehype plugin immediately after `rehypeRaw`.
- `js/src/markdown/MarkdownContent.tsx`
  - Read preserved island HTML from the HAST node instead of `toHtml(node.children)`.
- `js/src/chat/RawHTML.tsx`
  - Call the island enhancement helper after `innerHTML` assignment and before Shiny binding.
- `js/tests/markdown/MarkdownContent.test.tsx`
  - Cover preserved island payload rendering and raw HTML highlighting behavior.
- `js/tests/chat/RawHTML.test.tsx`
  - Cover island enhancement behavior at the DOM boundary.
- `js/tests/chat/ChatApp.test.tsx`
  - Cover end-to-end stable behavior for external links and suggestion attributes inside island HTML.

### New files to create

- `js/src/markdown/plugins/rehypeSnapshotHtmlIslands.ts`
  - Capture each `shinychat-raw-html` node's original inner HTML in `node.data`.
- `js/src/chat/enhanceRawHtmlContent.ts`
  - Apply stable-style DOM enhancements inside a `RawHTML` container.
- `js/tests/markdown/plugins/rehypeSnapshotHtmlIslands.test.ts`
  - Verify payload preservation survives later rehype mutations.
- `js/tests/chat/enhanceRawHtmlContent.test.ts`
  - Verify external links, suggestions, and code highlighting inside raw HTML islands.

## Task 1: Snapshot Island Payloads In The Markdown Pipeline

**Files:**
- Create: `js/src/markdown/plugins/rehypeSnapshotHtmlIslands.ts`
- Modify: `js/src/markdown/processors.ts`
- Test: `js/tests/markdown/plugins/rehypeSnapshotHtmlIslands.test.ts`

- [ ] **Step 1: Write the failing plugin test**

```ts
import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import { visit } from "unist-util-visit"
import type { Element } from "hast"

import { rehypeSnapshotHtmlIslands } from "../../../src/markdown/plugins/rehypeSnapshotHtmlIslands"
import { rehypeAccessibleSuggestions } from "../../../src/markdown/plugins/rehypeAccessibleSuggestions"
import { rehypeExternalLinks } from "../../../src/markdown/plugins/rehypeExternalLinks"

function getIsland(md: string): Element | undefined {
  const tree = unified()
    .use(remarkParse)
    .use(remarkRehype, { allowDangerousHtml: true })
    .use(rehypeRaw)
    .use(rehypeSnapshotHtmlIslands)
    .use(rehypeAccessibleSuggestions)
    .use(rehypeExternalLinks)
    .runSync(
      unified()
        .use(remarkParse)
        .use(remarkRehype, { allowDangerousHtml: true })
        .use(rehypeRaw)
        .parse(md),
    )

  let found: Element | undefined
  visit(tree, "element", (node: Element) => {
    if (node.tagName === "shinychat-raw-html") found = node
  })
  return found
}

describe("rehypeSnapshotHtmlIslands", () => {
  it("stores the original inner HTML before later plugins mutate island children", () => {
    const island = getIsland(
      "<shinychat-raw-html><a href='https://example.com'>link</a><span class='suggestion'>Try this</span></shinychat-raw-html>",
    )

    expect(island?.data?.rawHtml).toBe(
      '<a href="https://example.com">link</a><span class="suggestion">Try this</span>',
    )
    expect(JSON.stringify(island?.properties ?? {})).not.toContain("dataExternalLink")
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd js && npx vitest run tests/markdown/plugins/rehypeSnapshotHtmlIslands.test.ts`

Expected: FAIL with module-not-found for `rehypeSnapshotHtmlIslands` or missing `data.rawHtml`.

- [ ] **Step 3: Write the snapshot plugin**

```ts
import { visit } from "unist-util-visit"
import { toHtml } from "hast-util-to-html"
import type { Root, Element } from "hast"
import type { Plugin } from "unified"

export const HTML_ISLAND_RAW_HTML = "rawHtml"

export const rehypeSnapshotHtmlIslands: Plugin<[], Root> = () => (tree) => {
  visit(tree, "element", (node: Element) => {
    if (node.tagName !== "shinychat-raw-html") return

    node.data = {
      ...node.data,
      [HTML_ISLAND_RAW_HTML]: toHtml(node.children),
    }
  })
}
```

- [ ] **Step 4: Register the plugin immediately after `rehypeRaw`**

```ts
import { rehypeSnapshotHtmlIslands } from "./plugins/rehypeSnapshotHtmlIslands"

export const markdownProcessor = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(remarkRehype, { allowDangerousHtml: true })
  .use(rehypeRaw)
  .use(rehypeSnapshotHtmlIslands)
  .use(rehypeLazyContinuation)
  .use(rehypeUnwrapBlockCEs)
  .use(rehypeUncontrolledInputs)
  .use(rehypeAccessibleSuggestions)
  .use(rehypeExternalLinks)
  .use(rehypeHighlight, { detect: false, ignoreMissing: true })
  .freeze()
```

- [ ] **Step 5: Run the plugin test and the current markdown pipeline tests**

Run: `cd js && npx vitest run tests/markdown/plugins/rehypeSnapshotHtmlIslands.test.ts tests/markdown/plugins/rehypeAccessibleSuggestions.test.ts tests/markdown/plugins/rehypeExternalLinks.test.ts`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add js/src/markdown/plugins/rehypeSnapshotHtmlIslands.ts js/src/markdown/processors.ts js/tests/markdown/plugins/rehypeSnapshotHtmlIslands.test.ts
git commit -m "feat: snapshot html island payloads"
```

## Task 2: Render Islands From Preserved Payloads

**Files:**
- Modify: `js/src/markdown/MarkdownContent.tsx`
- Modify: `js/tests/markdown/MarkdownContent.test.tsx`
- Test: `js/tests/markdown/markdownToReact.test.tsx`

- [ ] **Step 1: Add failing MarkdownContent tests**

```ts
it("renders shinychat-raw-html from preserved payload instead of mutated children", () => {
  const content =
    "<shinychat-raw-html><a href='https://example.com'>link</a></shinychat-raw-html>"

  const { container } = render(
    <MarkdownContent content={content} contentType="markdown" />,
  )

  const anchor = container.querySelector("a") as HTMLAnchorElement
  expect(anchor.outerHTML).toBe('<a href="https://example.com">link</a>')
})

it("restores syntax highlighting for raw html code blocks inside islands", () => {
  const content =
    "<shinychat-raw-html><pre><code class='language-r'>x <- 1</code></pre></shinychat-raw-html>"

  const { container } = render(
    <MarkdownContent content={content} contentType="markdown" />,
  )

  const code = container.querySelector("code") as HTMLElement
  expect(code.className).toContain("hljs")
  expect(code.innerHTML).toContain("hljs-operator")
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd js && npx vitest run tests/markdown/MarkdownContent.test.tsx`

Expected: FAIL because the current implementation serializes mutated `node.children` and does not restore highlighting from the raw island HTML.

- [ ] **Step 3: Add a typed reader for preserved island HTML and use it in the component map**

```ts
import type { Element } from "hast"
import { HTML_ISLAND_RAW_HTML } from "./plugins/rehypeSnapshotHtmlIslands"

function getRawHtmlIslandPayload(node?: Element): string {
  const rawHtml = node?.data?.[HTML_ISLAND_RAW_HTML]
  return typeof rawHtml === "string" ? rawHtml : ""
}

const baseAssistantComponents: Record<string, ComponentType<unknown>> = {
  pre: CopyableCodeBlock as ComponentType<unknown>,
  table: BootstrapTable as ComponentType<unknown>,
  "shinychat-raw-html": (({ node }: { node?: Element }) => (
    <RawHTML html={getRawHtmlIslandPayload(node)} displayContents />
  )) as ComponentType<unknown>,
}
```

- [ ] **Step 4: Remove the unused `toHtml` import and keep the rest of `MarkdownContent` unchanged**

```ts
- import { toHtml } from "hast-util-to-html"
  import { useMemo, type ReactElement, type ComponentType } from "react"
```

- [ ] **Step 5: Run the focused markdown tests**

Run: `cd js && npx vitest run tests/markdown/MarkdownContent.test.tsx tests/markdown/markdownToReact.test.tsx`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add js/src/markdown/MarkdownContent.tsx js/tests/markdown/MarkdownContent.test.tsx
git commit -m "feat: render html islands from preserved payloads"
```

## Task 3: Move Stable-Island Enhancements To The RawHTML Boundary

**Files:**
- Create: `js/src/chat/enhanceRawHtmlContent.ts`
- Modify: `js/src/chat/RawHTML.tsx`
- Create: `js/tests/chat/enhanceRawHtmlContent.test.ts`
- Modify: `js/tests/chat/RawHTML.test.tsx`

- [ ] **Step 1: Write failing helper tests for the stable-era behaviors**

```ts
import { describe, it, expect } from "vitest"
import { enhanceRawHtmlContent } from "../../src/chat/enhanceRawHtmlContent"

function makeContainer(html: string): HTMLDivElement {
  const el = document.createElement("div")
  el.innerHTML = html
  return el
}

describe("enhanceRawHtmlContent", () => {
  it("adds external-link attributes to absolute links", () => {
    const el = makeContainer('<a href="https://example.com">docs</a>')
    enhanceRawHtmlContent(el)
    const anchor = el.querySelector("a") as HTMLAnchorElement
    expect(anchor.getAttribute("target")).toBe("_blank")
    expect(anchor.getAttribute("rel")).toBe("noopener noreferrer")
    expect(anchor.hasAttribute("data-external-link")).toBe(true)
  })

  it("adds suggestion accessibility attributes", () => {
    const el = makeContainer("<span class='suggestion'>Try this</span>")
    enhanceRawHtmlContent(el)
    const suggestion = el.querySelector(".suggestion") as HTMLElement
    expect(suggestion.getAttribute("tabindex")).toBe("0")
    expect(suggestion.getAttribute("role")).toBe("button")
    expect(suggestion.getAttribute("aria-label")).toBe("Use chat suggestion: Try this")
  })

  it("highlights code blocks inside raw html", () => {
    const el = makeContainer("<pre><code class='language-r'>x <- 1</code></pre>")
    enhanceRawHtmlContent(el)
    const code = el.querySelector("code") as HTMLElement
    expect(code.className).toContain("hljs")
    expect(code.innerHTML).toContain("hljs-operator")
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd js && npx vitest run tests/chat/enhanceRawHtmlContent.test.ts`

Expected: FAIL with module-not-found for `enhanceRawHtmlContent`.

- [ ] **Step 3: Implement the DOM helper with narrow scope**

```ts
import hljs from "highlight.js/lib/core"
import r from "highlight.js/lib/languages/r"
import python from "highlight.js/lib/languages/python"
import javascript from "highlight.js/lib/languages/javascript"
import typescript from "highlight.js/lib/languages/typescript"
import xml from "highlight.js/lib/languages/xml"
import markdown from "highlight.js/lib/languages/markdown"
import css from "highlight.js/lib/languages/css"
import sql from "highlight.js/lib/languages/sql"
import bash from "highlight.js/lib/languages/bash"
import json from "highlight.js/lib/languages/json"

hljs.registerLanguage("r", r)
hljs.registerLanguage("python", python)
hljs.registerLanguage("javascript", javascript)
hljs.registerLanguage("typescript", typescript)
hljs.registerLanguage("html", xml)
hljs.registerLanguage("xml", xml)
hljs.registerLanguage("markdown", markdown)
hljs.registerLanguage("css", css)
hljs.registerLanguage("sql", sql)
hljs.registerLanguage("bash", bash)
hljs.registerLanguage("json", json)

function isExternalHref(href: string): boolean {
  return /^(https?:)?\/\//.test(href)
}

function textContent(el: Element): string {
  return (el.textContent ?? "").trim()
}

export function enhanceRawHtmlContent(root: HTMLElement): void {
  for (const anchor of root.querySelectorAll<HTMLAnchorElement>("a[href]")) {
    const href = anchor.getAttribute("href")
    if (!href || !isExternalHref(href)) continue
    anchor.setAttribute("data-external-link", "")
    anchor.setAttribute("target", "_blank")
    anchor.setAttribute("rel", "noopener noreferrer")
  }

  for (const el of root.querySelectorAll<HTMLElement>(".suggestion, [data-suggestion]")) {
    if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "0")
    if (!el.hasAttribute("role")) el.setAttribute("role", "button")
    if (!el.hasAttribute("aria-label")) {
      const suggestion = el.dataset.suggestion || textContent(el)
      if (suggestion) el.setAttribute("aria-label", `Use chat suggestion: ${suggestion}`)
    }
  }

  for (const code of root.querySelectorAll<HTMLElement>("pre code")) {
    if (code.classList.contains("hljs")) continue
    hljs.highlightElement(code)
  }
}
```

- [ ] **Step 4: Wire the helper into `RawHTML` before `bindAll`**

```ts
import { enhanceRawHtmlContent } from "./enhanceRawHtmlContent"

useEffect(() => {
  const el = ref.current
  if (!el) return

  el.innerHTML = html
  enhanceRawHtmlContent(el)

  const parent = el.parentElement
  if (parent?.classList.contains("html-fill-container")) {
    setIsFillCarrier(true)
  }

  if (shiny && html) {
    shiny.bindAll(el)
  }

  return () => {
    if (shiny && el) {
      shiny.unbindAll(el)
    }
  }
}, [html, shiny])
```

- [ ] **Step 5: Add one RawHTML integration test to prove the helper runs**

```ts
it("enhances island html before binding shiny content", () => {
  const shiny = mockShiny()
  const { container } = render(
    <ShinyLifecycleContext.Provider value={shiny}>
      <RawHTML html="<a href='https://example.com'>docs</a><span class='suggestion'>Try this</span>" />
    </ShinyLifecycleContext.Provider>,
  )

  const anchor = container.querySelector("a") as HTMLAnchorElement
  const suggestion = container.querySelector(".suggestion") as HTMLElement

  expect(anchor.getAttribute("data-external-link")).toBe("")
  expect(suggestion.getAttribute("tabindex")).toBe("0")
  expect(shiny.bindAll).toHaveBeenCalled()
})
```

- [ ] **Step 6: Run the helper and RawHTML tests**

Run: `cd js && npx vitest run tests/chat/enhanceRawHtmlContent.test.ts tests/chat/RawHTML.test.tsx`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add js/src/chat/enhanceRawHtmlContent.ts js/src/chat/RawHTML.tsx js/tests/chat/enhanceRawHtmlContent.test.ts js/tests/chat/RawHTML.test.tsx
git commit -m "feat: restore stable html island enhancements"
```

## Task 4: Prove End-To-End Stable Behavior And Streaming Stability

**Files:**
- Modify: `js/tests/chat/ChatApp.test.tsx`
- Modify: `js/tests/markdown/MarkdownContent.test.tsx`

- [ ] **Step 1: Add a ChatApp regression test for external links and suggestions inside island html**

```ts
it("applies stable link and suggestion behavior inside shinychat-raw-html content", () => {
  const transport = createMockTransport()
  const shinyLifecycle = createMockShinyLifecycle()

  render(
    <ChatApp
      transport={transport}
      shinyLifecycle={shinyLifecycle}
      elementId="test-chat"
      inputId="test-input"
      placeholder="Type here..."
    />,
  )

  act(() => {
    transport.fire("test-chat", {
      type: "message",
      message: {
        role: "assistant",
        content:
          "<shinychat-raw-html><a href='https://example.com'>docs</a><span class='suggestion' data-suggestion='click me'>click me</span></shinychat-raw-html>",
        content_type: "markdown",
      },
    })
  })

  const anchor = document.querySelector("a") as HTMLAnchorElement
  const suggestion = document.querySelector(".suggestion") as HTMLElement

  expect(anchor.getAttribute("data-external-link")).toBe("")
  expect(suggestion.getAttribute("aria-label")).toBe(
    "Use chat suggestion: click me",
  )
})
```

- [ ] **Step 2: Add a MarkdownContent regression test for island stability across rerenders**

```ts
it("does not change island html when surrounding markdown rerenders", () => {
  const island =
    "<shinychat-raw-html><a href='https://example.com'>docs</a></shinychat-raw-html>"

  const { container, rerender } = render(
    <MarkdownContent content={`before ${island}`} contentType="markdown" streaming={true} />,
  )

  const before = container.querySelector("a")?.outerHTML

  rerender(
    <MarkdownContent content={`before ${island}`} contentType="markdown" streaming={false} />,
  )

  const after = container.querySelector("a")?.outerHTML
  expect(after).toBe(before)
})
```

- [ ] **Step 3: Run the focused integration suite**

Run: `cd js && npx vitest run tests/markdown/MarkdownContent.test.tsx tests/chat/ChatApp.test.tsx`

Expected: PASS.

- [ ] **Step 4: Run the full targeted suite for all touched areas**

Run: `cd js && npx vitest run tests/markdown/plugins/rehypeSnapshotHtmlIslands.test.ts tests/markdown/plugins/rehypeAccessibleSuggestions.test.ts tests/markdown/plugins/rehypeExternalLinks.test.ts tests/markdown/MarkdownContent.test.tsx tests/markdown/markdownToReact.test.tsx tests/chat/enhanceRawHtmlContent.test.ts tests/chat/RawHTML.test.tsx tests/chat/ChatApp.test.tsx`

Expected: PASS.

- [ ] **Step 5: Run lint for the JS package**

Run: `cd js && npm run lint`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add js/tests/markdown/MarkdownContent.test.tsx js/tests/chat/ChatApp.test.tsx
git commit -m "test: cover stable html island behavior"
```

## Task 5: Final Review And Documentation Sync

**Files:**
- Modify: `memory-bank/content-rendering.md`
- Test: `docs/superpowers/specs/2026-04-16-html-islands-opaque-design.md`

- [ ] **Step 1: Update the memory bank to match the new boundary**

```md
- `shinychat-raw-html` islands are snapshotted after `rehypeRaw`.
- Rehype may still transform neighboring markdown content, but island rendering uses the preserved payload.
- `RawHTML` invokes a DOM helper to restore stable-era island behavior for external links, suggestions, and code highlighting.
```

- [ ] **Step 2: Read the design spec and memory-bank note side by side**

Run: `diff -u docs/superpowers/specs/2026-04-16-html-islands-opaque-design.md memory-bank/content-rendering.md`

Expected: The files differ in detail, but the architectural boundary is consistent and there are no stale claims that rehype owns island internals.

- [ ] **Step 3: Run the final verification sweep**

Run: `cd js && npm test`

Expected: PASS. If unrelated environment failures remain, capture them explicitly in the final handoff instead of claiming a green suite.

- [ ] **Step 4: Commit**

```bash
git add memory-bank/content-rendering.md
git commit -m "docs: update html island rendering notes"
```

## Self-Review

Spec coverage check:

- Preserve raw island payload after `rehypeRaw`: Task 1
- Render islands from preserved payload instead of `node.children`: Task 2
- Move stable-era island enhancements to `RawHTML` boundary: Task 3
- Restore external links, suggestion accessibility, and code highlighting inside islands: Tasks 3 and 4
- Fail-soft behavior and scoped enhancement: Task 3
- Streaming regression coverage: Task 4
- Documentation alignment: Task 5

Placeholder scan:

- No `TODO`, `TBD`, or “write tests later” placeholders remain.
- Every task names exact files, commands, and expected outcomes.

Type consistency check:

- The preserved payload key is `HTML_ISLAND_RAW_HTML` / `data.rawHtml` throughout.
- The DOM helper is named `enhanceRawHtmlContent` throughout.
- The snapshot plugin is named `rehypeSnapshotHtmlIslands` throughout.
