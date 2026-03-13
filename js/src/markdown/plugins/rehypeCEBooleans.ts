/**
 * rehype plugin: normalise empty-string HAST properties to `true` on custom
 * elements (tag names containing a hyphen).
 *
 * parse5 (used by rehype-raw) represents boolean HTML attributes like
 * `<my-el expanded>` as `{ expanded: "" }` in HAST. When `toJsxRuntime`
 * passes these to React 19+, React sets the **property** on the custom
 * element (`el.expanded = ""`). Because `""` is falsy in JS, Lit (and other
 * CE libraries) interpret it as `false`, breaking boolean attribute semantics.
 *
 * This plugin converts `""` → `true` for all properties on custom elements,
 * restoring the intended "attribute is present → truthy" behaviour.
 */

import { visit } from "unist-util-visit"
import type { Root, Element } from "hast"

function isCustomElement(node: Element): boolean {
  return node.tagName.includes("-")
}

export function rehypeCEBooleans() {
  return (tree: Root) => {
    visit(tree, "element", (node: Element) => {
      if (!isCustomElement(node) || !node.properties) return
      for (const [key, value] of Object.entries(node.properties)) {
        if (value === "") {
          node.properties[key] = true
        }
      }
    })
  }
}
