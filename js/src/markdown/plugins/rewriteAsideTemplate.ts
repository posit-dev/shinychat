import { visit } from "unist-util-visit"
import type { Root, Element } from "hast"
import type { Plugin } from "unified"
import { isElementContent, isRaw } from "./hastRaw"
import { rewriteTagsHtml } from "./rewriteEndTags"

export function rewriteAsideToTemplateHtml(value: string): string {
  return rewriteTagsHtml(value, {
    "shiny-aside": {
      start: "<template data-shiny-aside",
      end: "</template>",
      selfClosingEnd: "</template>",
    },
  })
}

/**
 * BEFORE rehype-raw: rewrite `<shiny-aside …>`/`</shiny-aside>` raw strings
 * to `<template data-shiny-aside …>`/`</template>`. `<template>` is the one
 * tag parse5 gives "in template" tree construction, so its content is pulled
 * into a `.content` fragment with full block nesting instead of being
 * orphaned by the `<p>`-can't-contain-blocks auto-close rule. Operating on
 * raw nodes only leaves literal aside text inside code fences/spans
 * untouched.
 *
 * Self-closing `<shiny-aside .../>` is normalized to an open/close pair
 * first: a lone `<template data-shiny-aside/>` would ignore the `/` and
 * swallow everything up to the next `</template>`.
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
