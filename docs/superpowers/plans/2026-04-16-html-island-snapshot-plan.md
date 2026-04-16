# Snapshot HTML Island Payloads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Treat `shinychat-raw-html` islands as opaque payloads by recording their raw HTML immediately after `rehypeRaw` so downstream renders can read a stable string.

**Architecture:** Insert a rehype plugin (`rehypeSnapshotHtmlIslands`) into the Markdown processor right after `rehypeRaw`; the plugin serializes island children via `toHtml` and stores that string in `node.data.rawHtml` before later plugins mutate the tree.

**Tech Stack:** unified/rehype, Vitest, TypeScript.

---

### Task 1: Add the failing snapshot plugin test

**Files:**
- Create: `/Users/cpsievert/github/shinychat/js/tests/markdown/plugins/rehypeSnapshotHtmlIslands.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from "vitest"
import { unified } from "unified"
import { visit } from "unist-util-visit"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import { rehypeAccessibleSuggestions } from "../../../src/markdown/plugins/rehypeAccessibleSuggestions"
import {
  rehypeSnapshotHtmlIslands,
  HTML_ISLAND_RAW_HTML,
} from "../../../src/markdown/plugins/rehypeSnapshotHtmlIslands"

function snapshotFromMarkdown(md: string): string | undefined {
  let snapshot: string | undefined

  unified()
    .use(remarkParse)
    .use(remarkRehype, { allowDangerousHtml: true })
    .use(rehypeRaw)
    .use(rehypeSnapshotHtmlIslands)
    .use(rehypeAccessibleSuggestions)
    .use(() => (tree) => {
      visit(tree, "element", (node) => {
        if (node.tagName === "shinychat-raw-html") {
          snapshot = node.data?.[HTML_ISLAND_RAW_HTML] as string | undefined
        }
      })
    })
    .processSync(md)

  return snapshot
}

describe("rehypeSnapshotHtmlIslands", () => {
  it("captures the original inner HTML before other rehype plugins mutate it", () => {
    const inner = "<button class='suggestion'>Use hint</button>"
    const md = `<shinychat-raw-html>${inner}</shinychat-raw-html>`
    expect(snapshotFromMarkdown(md)).toBe(inner)
  })
})
```

- [ ] **Step 2: Run the test to confirm it fails**

```
cd js && npx vitest run tests/markdown/plugins/rehypeSnapshotHtmlIslands.test.ts
```

Expected: FAIL because `rehypeSnapshotHtmlIslands` is missing and the snapshot is `undefined`.

### Task 2: Implement `rehypeSnapshotHtmlIslands`

**Files:**
- Create: `/Users/cpsievert/github/shinychat/js/src/markdown/plugins/rehypeSnapshotHtmlIslands.ts`

- [ ] **Step 1: Write the plugin implementation**

```ts
import { visit } from "unist-util-visit"
import { toHtml } from "hast-util-to-html"
import type { Plugin } from "unified"
import type { Root, Element } from "hast"

export const HTML_ISLAND_RAW_HTML = "rawHtml"

export const rehypeSnapshotHtmlIslands: Plugin<[], Root> = () => (tree) => {
  visit(tree, "element", (node: Element) => {
    if (node.tagName !== "shinychat-raw-html") return

    const serialized = toHtml(node.children ?? [])
    if (!serialized) return

    node.data = {
      ...node.data,
      [HTML_ISLAND_RAW_HTML]: serialized,
    }
  })
}
```

- [ ] **Step 2: Run the snapshot test to confirm it passes**

```
cd js && npx vitest run tests/markdown/plugins/rehypeSnapshotHtmlIslands.test.ts
```

Expected: PASS (the snapshot equals the `inner` string even though `rehypeAccessibleSuggestions` mutates the tree afterward).

### Task 3: Wire the plugin into the Markdown processor

**Files:**
- Modify: `/Users/cpsievert/github/shinychat/js/src/markdown/processors.ts`

- [ ] **Step 1: Add the new plugin import and registration**

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

- [ ] **Step 2: Run the plugin test suite to ensure no regressions**

```
cd js && npx vitest run tests/markdown/plugins/rehypeSnapshotHtmlIslands.test.ts tests/markdown/plugins/rehypeAccessibleSuggestions.test.ts tests/markdown/plugins/rehypeExternalLinks.test.ts
```

Expected: PASS (the new snapshot step does not break the other plugin suites).

### Task 4: Commit the work

**Files to stage:** spec, plan, new plugin, processor change, test file.

- [ ] **Step 1: Stage files**

```
git add docs/superpowers/specs/2026-04-16-html-island-snapshot-design.md \
  docs/superpowers/plans/2026-04-16-html-island-snapshot-plan.md \
  js/src/markdown/plugins/rehypeSnapshotHtmlIslands.ts \
  js/src/markdown/processors.ts \
  js/tests/markdown/plugins/rehypeSnapshotHtmlIslands.test.ts
```

- [ ] **Step 2: Commit**

```
git commit -m "feat: snapshot html island payloads"
```
