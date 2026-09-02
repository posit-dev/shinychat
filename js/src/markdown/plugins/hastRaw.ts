import type { ElementContent, RootContent } from "hast"

// `raw` nodes are hast-util-raw's string carriers that exist between
// remark-rehype and rehype-raw; they are not part of the standard hast union.
export interface RawNode {
  type: "raw"
  value: string
}

export function isRaw(node: unknown): node is RawNode {
  return (node as { type?: string })?.type === "raw"
}

// `Root.children` is typed as `RootContent[]`, which includes `Doctype` (only
// ever produced at a full document's root); a `<template>`'s `.content`
// fragment can't contain one, so this narrows to the `ElementContent[]` that
// `Element.children` requires.
export function isElementContent(node: RootContent): node is ElementContent {
  return node.type !== "doctype"
}
