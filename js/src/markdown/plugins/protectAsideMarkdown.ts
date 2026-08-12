import { unified } from "unified"
import { visit } from "unist-util-visit"
import remarkParse from "remark-parse"
import remarkGfm from "remark-gfm"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import type { Element, Root as HastRoot } from "hast"
import type { Html, Root as MdastRoot } from "mdast"
import type { Node, Parent } from "unist"
import type { Plugin } from "unified"
import {
  rehypeRewriteAsideFromTemplate,
  rehypeRewriteAsideToTemplate,
} from "./rewriteAsideTemplate"

declare module "vfile" {
  interface DataMap {
    protectedListItemAsides: string[]
  }
}

export const remarkProtectListItemAsides: Plugin<[], MdastRoot> = function () {
  return (tree, file) => {
    const source = file.toString()
    const sourceEnd = tree.position?.end.offset
    // `runSync(parse(markdown))` omits the source file; leave those callers on
    // the existing parser path instead of applying offsets to an empty string.
    if (sourceEnd !== undefined && sourceEnd > source.length) return

    const protectedMarkdown = protectListItemAsides(source, tree)
    if (!protectedMarkdown) return

    file.data.protectedListItemAsides = protectedMarkdown.fragments
    file.value = protectedMarkdown.value
    return this.parse(file) as MdastRoot
  }
}

export const rehypeRestoreListItemAsides: Plugin<[], HastRoot> =
  () => (tree, file) => {
    const fragments = file.data.protectedListItemAsides
    if (!fragments) return

    visit(tree, "element", (node: Element, index, parent) => {
      if (!parent || index === undefined) return
      if (node.tagName !== "shiny-aside-placeholder") return

      const fragmentIndex = Number(node.properties?.dataShinyAsidePlaceholder)
      const fragment = fragments[fragmentIndex]
      if (!fragment) return

      parent.children.splice(index, 1, parseAsideFragment(fragment))
    })
  }

interface AsideRegion {
  start: number
  end: number
}

interface AsideTag {
  start: number
  end: number
  closing: boolean
  selfClosing: boolean
  inListItem: boolean
  protect: boolean
}

interface ProtectedMarkdown {
  value: string
  fragments: string[]
}

const asideFragmentProcessor = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(remarkRehype, { allowDangerousHtml: true })
  .use(rehypeRewriteAsideToTemplate)
  .use(rehypeRaw)
  .use(rehypeRewriteAsideFromTemplate)
  .freeze()

function protectListItemAsides(
  source: string,
  tree: MdastRoot,
): ProtectedMarkdown | null {
  const regions = findProtectedRegions(tree)
  if (regions.length === 0) return null

  const fragments: string[] = []
  let value = ""
  let cursor = 0

  for (const region of regions) {
    const fragmentIndex = fragments.length
    fragments.push(source.slice(region.start, region.end))
    value += source.slice(cursor, region.start)
    value +=
      `<shiny-aside-placeholder ` +
      `data-shiny-aside-placeholder="${fragmentIndex}">` +
      `</shiny-aside-placeholder>`
    cursor = region.end
  }

  value += source.slice(cursor)
  return { value, fragments }
}

function findProtectedRegions(tree: MdastRoot): AsideRegion[] {
  const tags = collectAsideTags(tree)
  const stack: AsideTag[] = []
  const regions: AsideRegion[] = []

  for (const tag of tags) {
    if (tag.closing) {
      const opening = stack.pop()
      if (opening?.protect) {
        regions.push({ start: opening.start, end: tag.end })
      }
      continue
    }

    if (tag.selfClosing) continue
    tag.protect = tag.inListItem && !stack.some((entry) => entry.protect)
    stack.push(tag)
  }

  return regions.sort((a, b) => a.start - b.start)
}

function collectAsideTags(tree: MdastRoot): AsideTag[] {
  const tags: AsideTag[] = []
  collectNodeAsideTags(tree, false, tags)
  return tags.sort((a, b) => a.start - b.start)
}

function collectNodeAsideTags(
  node: Node,
  inListItem: boolean,
  tags: AsideTag[],
): void {
  const insideListItem = inListItem || node.type === "listItem"

  if (node.type === "html") {
    collectHtmlAsideTags(node as Html, insideListItem, tags)
  }

  if ("children" in node) {
    for (const child of (node as Parent).children) {
      collectNodeAsideTags(child, insideListItem, tags)
    }
  }
}

function collectHtmlAsideTags(
  node: Html,
  inListItem: boolean,
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
      inListItem,
      protect: false,
    })
  }
}

function parseAsideFragment(fragment: string): Element {
  const tree = asideFragmentProcessor.runSync(
    asideFragmentProcessor.parse(fragment),
  ) as HastRoot
  const aside = findAside(tree)
  if (!aside) {
    throw new Error("Protected <shiny-aside> could not be restored")
  }
  return aside
}

function findAside(node: HastRoot | Element): Element | null {
  for (const child of node.children) {
    if (child.type !== "element") continue
    if (child.tagName === "shiny-aside") return child
    const nested = findAside(child)
    if (nested) return nested
  }
  return null
}
