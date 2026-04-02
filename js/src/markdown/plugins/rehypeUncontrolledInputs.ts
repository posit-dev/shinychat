import { visit } from "unist-util-visit"
import type { Root, Element } from "hast"
import type { Plugin } from "unified"

/**
 * Rehype plugin that converts `value` → `defaultValue` and
 * `checked` → `defaultChecked` on form input elements.
 *
 * Without this, React treats `<input value="0">` as a controlled input
 * (React owns the value), which prevents external code — like Shiny's
 * input bindings — from reading or updating the value.
 *
 * Using `defaultValue`/`defaultChecked` makes the inputs uncontrolled,
 * so the browser (and Shiny) can manage them normally.
 */
export const rehypeUncontrolledInputs: Plugin<[], Root> = () => (tree) => {
  visit(tree, "element", (node: Element) => {
    const props = node.properties
    if (!props) return

    if (node.tagName === "input" || node.tagName === "textarea") {
      if ("value" in props) {
        props.defaultValue = props.value
        delete props.value
      }
      if ("checked" in props) {
        props.defaultChecked = props.checked
        delete props.checked
      }
    }
  })
}
