import { toHtml } from "hast-util-to-html"
import type { Element, ElementContent, Root, RootContent } from "hast"
import type { Plugin } from "unified"
import { SKIP, visit } from "unist-util-visit"
import { rewriteTagsHtml } from "./rewriteEndTags"

// Spoof guard: any island tag reaching the markdown processor is forged
// (trusted HTML arrives as structured html_block envelopes, not in markdown).
// The disguise→template round-trip is required because rehypeRaw's parse5 pass
// hoists block-level children out of unknown custom elements before the
// component map sees them. Disguising as <template> captures children as inert
// template content; after parse5, the template is restored as literal text.
const islandTags = ["shiny-chat-raw-html", "shinychat-raw-html"]
const islandTagSet = new Set(islandTags)
const disguiseAttr = "data-reserved-island"
const disguiseProp = "dataReservedIsland"

interface RawNode {
  type: "raw"
  value: string
}

function isRaw(node: unknown): node is RawNode {
  return (node as { type?: string })?.type === "raw"
}

function isElementContent(node: RootContent): node is ElementContent {
  return node.type !== "doctype"
}

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
