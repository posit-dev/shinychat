import type { Html, ListItem, Root as MdastRoot } from "mdast"
import type { Node, Parent } from "unist"
import type { Plugin } from "unified"

export const remarkNormalizeListItemAsides: Plugin<[], MdastRoot> =
  function () {
    return (tree, file) => {
      const source = file.toString()
      const sourceEnd = tree.position?.end.offset
      if (sourceEnd !== undefined && sourceEnd > source.length) return

      const normalized = normalizeListItemAsides(source, tree)
      if (!normalized) return

      file.value = normalized
      return this.parse(file) as MdastRoot
    }
  }

interface AsideRegion {
  start: number
  end: number
  targetIndent: number
}

interface AsideTag {
  start: number
  end: number
  closing: boolean
  selfClosing: boolean
  targetIndent: number | null
}

function normalizeListItemAsides(
  source: string,
  tree: MdastRoot,
): string | null {
  const regions = findProtectedRegions(tree)
  if (regions.length === 0) return null

  let normalized = source
  for (const region of regions.sort(
    (left, right) => right.start - left.start,
  )) {
    normalized = normalizeRegion(normalized, region)
  }

  return normalized === source ? null : normalized
}

function findProtectedRegions(tree: MdastRoot): AsideRegion[] {
  const tags = collectAsideTags(tree)
  const stack: AsideTag[] = []
  const regions: AsideRegion[] = []

  for (const tag of tags) {
    if (tag.closing) {
      const opening = stack.pop()
      if (opening && opening.targetIndent !== null) {
        regions.push({
          start: opening.start,
          end: tag.end,
          targetIndent: opening.targetIndent,
        })
      }
      continue
    }

    if (tag.selfClosing) continue
    if (stack.some((entry) => entry.targetIndent !== null)) {
      tag.targetIndent = null
    }
    stack.push(tag)
  }

  return regions
}

function collectAsideTags(tree: MdastRoot): AsideTag[] {
  const tags: AsideTag[] = []
  collectNodeAsideTags(tree, null, tags)
  return tags.sort((a, b) => a.start - b.start)
}

function collectNodeAsideTags(
  node: Node,
  listItem: ListItem | null,
  tags: AsideTag[],
): void {
  const currentListItem =
    node.type === "listItem" ? (node as ListItem) : listItem

  if (node.type === "html") {
    collectHtmlAsideTags(node as Html, currentListItem, tags)
  }

  if ("children" in node) {
    for (const child of (node as Parent).children) {
      collectNodeAsideTags(child, currentListItem, tags)
    }
  }
}

function collectHtmlAsideTags(
  node: Html,
  listItem: ListItem | null,
  tags: AsideTag[],
): void {
  const offset = node.position?.start.offset
  if (offset === undefined) return

  const pattern =
    /<\/shiny-aside\s*>|<shiny-aside(?=[\s/>])(?:"[^"]*"|'[^']*'|[^"'>])*>/g

  for (const match of node.value.matchAll(pattern)) {
    const value = match[0]
    const start = offset + match.index
    tags.push({
      start,
      end: start + value.length,
      closing: value.startsWith("</"),
      selfClosing: /\/\s*>$/.test(value),
      targetIndent: listItem ? listItemIndent(listItem) : null,
    })
  }
}

function listItemIndent(listItem: ListItem): number | null {
  for (const child of listItem.children) {
    const column = child.position?.start.column
    if (column !== undefined) return column - 1
  }
  return null
}

function normalizeRegion(source: string, region: AsideRegion): string {
  const openingLineStart = source.lastIndexOf("\n", region.start - 1) + 1
  const openingPrefix = source.slice(openingLineStart, region.start)
  const openingIsAtLineStart = /^[\t ]*$/.test(openingPrefix)
  const openingLineEnd = source.indexOf("\n", region.start)
  const rewriteStart = openingIsAtLineStart
    ? openingLineStart
    : openingLineEnd === -1
      ? region.end
      : openingLineEnd + 1

  if (rewriteStart >= region.end) return source

  const fragment = source.slice(rewriteStart, region.end)
  const baseline = minimumIndent(fragment)
  if (baseline === null || baseline >= region.targetIndent) return source

  const indent = " ".repeat(region.targetIndent - baseline)
  const normalized = fragment.replace(/^(?=[^\r\n])/gm, indent)
  return source.slice(0, rewriteStart) + normalized + source.slice(region.end)
}

function minimumIndent(value: string): number | null {
  let minimum: number | null = null

  for (const line of value.split(/\r?\n/)) {
    if (line.trim() === "") continue
    const indent = indentationWidth(line)
    minimum = minimum === null ? indent : Math.min(minimum, indent)
  }

  return minimum
}

function indentationWidth(value: string): number {
  let width = 0

  for (const character of value) {
    if (character === " ") {
      width++
    } else if (character === "\t") {
      width += 4 - (width % 4)
    } else {
      break
    }
  }

  return width
}
