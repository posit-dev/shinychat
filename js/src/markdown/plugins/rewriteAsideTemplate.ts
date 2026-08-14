import { visit } from "unist-util-visit"
import type { Root, RootContent, Element, ElementContent } from "hast"
import type { Plugin } from "unified"

// `raw` nodes are hast-util-raw's string carriers that exist between
// remark-rehype and rehype-raw; they are not part of the standard hast union.
interface RawNode {
  type: "raw"
  value: string
}

function isRaw(node: unknown): node is RawNode {
  return (node as { type?: string })?.type === "raw"
}

// `Root.children` is typed as `RootContent[]`, which includes `Doctype` (only
// ever produced at a full document's root); a `<template>`'s `.content`
// fragment can't contain one, so this narrows to the `ElementContent[]` that
// `Element.children` requires.
function isElementContent(node: RootContent): node is ElementContent {
  return node.type !== "doctype"
}

export function rewriteAsideToTemplateHtml(value: string): string {
  return value
    .replace(
      /<shiny-aside(?=[\s/>])((?:"[^"]*"|'[^']*'|[^"'>])*?)\/>/g,
      "<shiny-aside$1></shiny-aside>",
    )
    .replace(/<shiny-aside(?=[\s/>])/g, "<template data-shiny-aside")
    .replace(/<\/shiny-aside\s*>/g, "</template>")
}

/**
 * BEFORE rehype-raw: rewrite `<shiny-aside …>`/`</shiny-aside>` raw
 * strings to `<template data-shiny-aside …>`/`</template>`. `<template>` is
 * the one tag parse5 gives "in template" tree construction, so its content is
 * pulled into a `.content` fragment with full block nesting instead of being
 * orphaned by the `<p>`-can't-contain-blocks auto-close rule. Operating on raw
 * nodes only means literal aside text inside code fences/spans is untouched.
 * The lookahead `[\s/>]` avoids matching `<shiny-aside-group>`.
 *
 * Self-closing `<shiny-aside .../>` is normalized to an open/close pair
 * first: a lone `<template data-shiny-aside/>` would (like any non-void
 * element) ignore the `/` and swallow everything up to the next `</template>`,
 * eating the text that follows the tag. The attribute scan skips over quoted
 * values so a `/` inside e.g. `url="https://…"` isn't mistaken for the close.
 */
export const rehypeRewriteAsideToTemplate: Plugin<[], Root> = () => (tree) => {
  visit(tree, (node) => {
    if (!isRaw(node)) return
    node.value = rewriteAsideToTemplateHtml(node.value)
  })
}

export function restoreAsideTemplates(tree: Root): void {
  visit(tree, "element", (node: Element) => {
    if (node.tagName !== "template") return
    if (!node.properties || !("dataShinyAside" in node.properties)) return
    node.tagName = "shiny-aside"
    node.children = (node.content?.children ?? []).filter(isElementContent)
    delete node.content
    delete node.properties.dataShinyAside
  })
}

/**
 * AFTER rehype-raw: undo the disguise. parse5 stores template content in the
 * `.content` fragment (which `toJsxRuntime` ignores), so hoist it into normal
 * `.children` and rename back to `<shiny-aside>`. Downstream code then sees
 * an ordinary custom element whose children may contain blocks.
 */
export const rehypeRewriteAsideFromTemplate: Plugin<[], Root> = () =>
  restoreAsideTemplates
