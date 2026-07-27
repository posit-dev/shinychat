import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import {
  rehypeRewriteAsideToTemplate,
  rehypeRewriteAsideFromTemplate,
} from "../../../src/markdown/plugins/rewriteAsideTemplate"
import { rehypeGroupAsides } from "../../../src/markdown/plugins/rehypeGroupAsides"
import { rehypeDedupeCitations } from "../../../src/markdown/plugins/rehypeDedupeCitations"

function process(md: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRewriteAsideToTemplate)
      .use(rehypeRaw)
      .use(rehypeRewriteAsideFromTemplate)
      .use(rehypeGroupAsides)
      .use(rehypeDedupeCitations)
      .use(rehypeStringify)
      .processSync(md),
  )
}

const cite = (url: string, title: string) =>
  `<shiny-aside data-citation label="${new URL(url).hostname}" url="${url}"><a href="${url}">${title}</a></shiny-aside>`

describe("rehypeDedupeCitations", () => {
  it("collapses two identical (url, title) citations in a paragraph to one", () => {
    const u = "https://ebicycles.example/hub"
    const md = `Claim${cite(u, "Hub vs Mid")} and again${cite(u, "Hub vs Mid")}.`
    const html = process(md)
    expect(html.match(/<shiny-aside\b(?!-group)/g)).toHaveLength(1)
  })

  it("keeps two citations that share a url but differ in title", () => {
    const u = "https://ebicycles.example/hub"
    const md = `A${cite(u, "Title One")} B${cite(u, "Title Two")}.`
    const html = process(md)
    expect(html.match(/<shiny-aside\b(?!-group)/g)).toHaveLength(2)
  })

  it("keeps two citations to different urls", () => {
    const md = `A${cite("https://a.example/x", "A")} B${cite("https://b.example/y", "B")}.`
    const html = process(md)
    expect(html.match(/<shiny-aside\b(?!-group)/g)).toHaveLength(2)
  })

  it("leaves hand-authored (non-citation) duplicate asides untouched", () => {
    const a = `<shiny-aside label="Src" url="https://x.example">note</shiny-aside>`
    const md = `A${a} B${a}.`
    const html = process(md)
    expect(html.match(/<shiny-aside\b(?!-group)/g)).toHaveLength(2)
  })

  it("dedupes per container, not across the whole message", () => {
    const u = "https://ebicycles.example/hub"
    const md = [
      `Para one${cite(u, "T")}.`,
      "",
      `Para two${cite(u, "T")}.`,
    ].join("\n")
    const html = process(md)
    expect(html.match(/<shiny-aside\b(?!-group)/g)).toHaveLength(2)
  })
})
