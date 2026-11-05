import { describe, expect, it } from "vitest"
import { highlightHtmlCode } from "../../src/markdown/highlightHtmlCode"

describe("highlightHtmlCode", () => {
  it("adds hljs classes to code blocks with a known language class", () => {
    const out = highlightHtmlCode(
      '<pre><code class="language-r">x &lt;- 1</code></pre>',
    )
    expect(out).toMatch(/<code class="hljs language-r">/)
    expect(out).toMatch(/<span class="hljs-/)
  })

  it("highlights python and sql too (lowlight common grammars)", () => {
    for (const lang of ["python", "sql"]) {
      const out = highlightHtmlCode(
        `<pre><code class="language-${lang}">select 1</code></pre>`,
      )
      expect(out).toContain("hljs")
    }
  })

  it("returns html without language classes byte-identical (no parse round-trip)", () => {
    const html = '<div class="plain"><b>hi</b></div>'
    expect(highlightHtmlCode(html)).toBe(html)
  })

  it("leaves code with an unknown language unhighlighted (ignoreMissing)", () => {
    const out = highlightHtmlCode(
      '<pre><code class="language-nope">???</code></pre>',
    )
    expect(out).not.toMatch(/<span class="hljs-/)
  })

  it('stays byte-identical when "language-" appears only in prose', () => {
    const html = "<p>Classes like language-r are conventional.</p>"
    expect(highlightHtmlCode(html)).toBe(html)
  })

  it("round-trips malformed HTML without throwing", () => {
    const out = highlightHtmlCode('<pre><code class="language-r">x <- 1</code>')
    expect(out).toContain("hljs")
  })
})
