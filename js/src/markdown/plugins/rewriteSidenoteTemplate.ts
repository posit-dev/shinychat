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

/**
 * BEFORE rehype-raw: rewrite `<shiny-sidenote …>`/`</shiny-sidenote>` raw
 * strings to `<template data-shiny-sidenote …>`/`</template>`. `<template>` is
 * the one tag parse5 gives "in template" tree construction, so its content is
 * pulled into a `.content` fragment with full block nesting instead of being
 * orphaned by the `<p>`-can't-contain-blocks auto-close rule. Operating on raw
 * nodes only means literal sidenote text inside code fences/spans is untouched.
 * The lookahead `[\s/>]` avoids matching `<shiny-sidenote-group>`.
 */
export const rehypeRewriteSidenoteToTemplate: Plugin<[], Root> =
  () => (tree) => {
    visit(tree, (node) => {
      if (!isRaw(node)) return
      node.value = node.value
        .replace(/<shiny-sidenote(?=[\s/>])/g, "<template data-shiny-sidenote")
        .replace(/<\/shiny-sidenote\s*>/g, "</template>")
    })
  }

/**
 * AFTER rehype-raw: undo the disguise. parse5 stores template content in the
 * `.content` fragment (which `toJsxRuntime` ignores), so hoist it into normal
 * `.children` and rename back to `<shiny-sidenote>`. Downstream code then sees
 * an ordinary custom element whose children may contain blocks.
 */
export const rehypeRewriteSidenoteFromTemplate: Plugin<[], Root> =
  () => (tree) => {
    visit(tree, "element", (node: Element) => {
      if (node.tagName !== "template") return
      if (!node.properties || !("dataShinySidenote" in node.properties)) return
      node.tagName = "shiny-sidenote"
      node.children = (node.content?.children ?? []).filter(isElementContent)
      delete node.content
      delete node.properties.dataShinySidenote
    })
  }
