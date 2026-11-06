import type { Root } from "hast"
import rehypeHighlight from "rehype-highlight"
import rehypeParse from "rehype-parse"
import rehypeStringify from "rehype-stringify"
import { unified } from "unified"
import { visit } from "unist-util-visit"

// rehype-highlight replaces the children of every matching <code> with
// tokenized text, so markup the author put inside the code (links, <mark>,
// Prism token spans) would be lost. Mark any pre > code whose children
// aren't all text with the `no-highlight` class that rehype-highlight
// already honors, leaving structured code exactly as authored.
function rehypePreserveStructuredCode() {
  return (tree: Root) => {
    visit(tree, "element", (node, _index, parent) => {
      if (
        node.tagName !== "code" ||
        !parent ||
        parent.type !== "element" ||
        parent.tagName !== "pre"
      ) {
        return
      }
      if (node.children.some((child) => child.type !== "text")) {
        if (!Array.isArray(node.properties.className)) {
          node.properties.className = []
        }
        ;(node.properties.className as Array<string | number>).push(
          "no-highlight",
        )
      }
    })
  }
}

// Frozen processor for tool-display HTML (display.html / valueType "html").
// Same highlight options as markdownProcessor: explicit language classes
// only, unknown languages degrade silently.
const processor = unified()
  .use(rehypeParse, { fragment: true })
  .use(rehypePreserveStructuredCode)
  .use(rehypeHighlight, { detect: false, ignoreMissing: true })
  .use(rehypeStringify)
  .freeze()

// rehype-highlight recognizes language- and lang- classes anywhere in the
// class list, and rehype-parse accepts unquoted attribute values. Gate on
// the same forms so the processor never sees HTML it could only re-serialize.
const LANGUAGE_CLASS = /\bclass\s*=\s*["']?[^"'>]*\b(?:language|lang)-/i

/**
 * Syntax-highlight `<pre><code class="language-*">` blocks in an HTML string.
 * Returns the input untouched when no language class is present, so plain
 * HTML pays no parse round-trip and is byte-identical. Code blocks that
 * contain markup (or carry a `no-highlight`/`nohighlight` class) are left
 * as authored.
 */
export function highlightHtmlCode(html: string): string {
  // Gate on the class attribute, not the bare word: prose mentioning
  // "language-" must stay byte-identical rather than take the round-trip.
  if (!LANGUAGE_CLASS.test(html)) {
    return html
  }
  return String(processor.processSync(html))
}
