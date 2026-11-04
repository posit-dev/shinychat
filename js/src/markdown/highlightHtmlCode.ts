import { unified } from "unified"
import rehypeParse from "rehype-parse"
import rehypeHighlight from "rehype-highlight"
import rehypeStringify from "rehype-stringify"

// Frozen processor for tool-display HTML (display.html / valueType "html").
// Same highlight options as markdownProcessor: explicit language classes
// only, unknown languages degrade silently.
const processor = unified()
  .use(rehypeParse, { fragment: true })
  .use(rehypeHighlight, { detect: false, ignoreMissing: true })
  .use(rehypeStringify)
  .freeze()

/**
 * Syntax-highlight `<pre><code class="language-*">` blocks in an HTML string.
 * Returns the input untouched when no language class is present, so plain
 * HTML pays no parse round-trip and is byte-identical.
 */
export function highlightHtmlCode(html: string): string {
  if (!html.includes("language-")) return html
  return String(processor.processSync(html))
}
