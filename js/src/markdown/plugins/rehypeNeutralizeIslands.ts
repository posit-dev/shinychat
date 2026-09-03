import { toHtml } from "hast-util-to-html"
import type { Element, Root } from "hast"
import type { Plugin } from "unified"
import { SKIP, visit } from "unist-util-visit"
import { isElementContent, isRaw } from "./hastRaw"
import { rewriteTagsHtml } from "./rewriteEndTags"

// Spoof guard: island tags in markdown are forged (trusted HTML arrives as
// html_block envelopes). Disguise as <template> because rehypeRaw's parse5
// pass hoists block children out of unknown custom elements. Restore as
// literal text after parse5.
const islandTags = ["shiny-chat-raw-html", "shinychat-raw-html"]
const islandTagSet = new Set(islandTags)
const disguiseAttr = "data-reserved-island"
const disguiseProp = "dataReservedIsland"

export function disguiseIslandsHtml(value: string): string {
  return rewriteTagsHtml(
    value,
    Object.fromEntries(
      islandTags.map((tag) => [
        tag,
        {
          start: `<template ${disguiseAttr}="${tag}"`,
          end: "</template>",
          selfClosingEnd: "</template>",
        },
      ]),
    ),
  )
}

/** Disguise islands before parse5 can hoist their block children. */
export const rehypeDisguiseIslands: Plugin<[], Root> = () => (tree) => {
  visit(tree, (node) => {
    if (isRaw(node)) node.value = disguiseIslandsHtml(node.value)
  })
}

function neutralizeDisguisedIslands(tree: Root): void {
  visit(tree, "element", (node: Element, index, parent) => {
    if (node.tagName !== "template") return

    const marker = node.properties?.[disguiseProp]
    if (typeof marker !== "string" || !islandTagSet.has(marker)) {
      if (node.content) neutralizeDisguisedIslands(node.content)
      return
    }
    if (!parent || index === undefined) return

    const { [disguiseProp]: _marker, ...properties } = node.properties!
    const original: Element = {
      type: "element",
      tagName: marker,
      properties,
      children: (node.content?.children ?? []).filter(isElementContent),
    }
    parent.children.splice(index, 1, {
      type: "text",
      value: toHtml(original),
    })
    return [SKIP, index] as const
  })
}

/** Restore disguised islands as visible text after parse5. */
export const rehypeNeutralizeIslands: Plugin<[], Root> = () =>
  neutralizeDisguisedIslands
