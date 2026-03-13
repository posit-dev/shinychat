import { toJsxRuntime } from "hast-util-to-jsx-runtime"
import { Fragment, jsx as reactJsx, jsxs as reactJsxs } from "react/jsx-runtime"
import { VFile } from "vfile"
import type { Root } from "hast"
import type { ReactElement, ComponentType } from "react"
import type { Processor } from "unified"

import { sanitizeUrls } from "./urlSanitize"
import { withStreamingDot } from "./streamingDot"

/**
 * Map of React property names → HTML attribute names for properties where
 * they differ. Only the subset likely to appear on custom elements is
 * included; obscure legacy attributes (aLink, vSpace, etc.) are omitted.
 */
const reactToHtmlAttr: Record<string, string> = {
  className: "class",
  htmlFor: "for",
  tabIndex: "tabindex",
  readOnly: "readonly",
  contentEditable: "contenteditable",
  colSpan: "colspan",
  rowSpan: "rowspan",
  autoComplete: "autocomplete",
  autoFocus: "autofocus",
  autoPlay: "autoplay",
  crossOrigin: "crossorigin",
  encType: "enctype",
  formAction: "formaction",
  formNoValidate: "formnovalidate",
  inputMode: "inputmode",
  maxLength: "maxlength",
  minLength: "minlength",
  noValidate: "novalidate",
  spellCheck: "spellcheck",
  srcDoc: "srcdoc",
  srcLang: "srclang",
  srcSet: "srcset",
}

/**
 * For custom elements (tag name contains "-"), convert React-ified property
 * names back to their HTML attribute equivalents. React 19 sets properties
 * (not attributes) on custom elements, and properties like `htmlFor` or
 * `readOnly` don't map to any attribute on a generic HTMLElement — only
 * `className` and `tabIndex` happen to work via property setting.
 *
 * Standard HTML elements are left untouched (React expects React names).
 */
function fixCustomElementProps(
  type: string,
  props: Record<string, unknown>,
): Record<string, unknown> {
  if (!type.includes("-")) return props
  let patched: Record<string, unknown> | undefined
  for (const [reactName, htmlName] of Object.entries(reactToHtmlAttr)) {
    if (reactName in props) {
      if (!patched) patched = { ...props }
      patched[htmlName] = patched[reactName]
      delete patched[reactName]
    }
  }
  return patched ?? props
}

// Wrappers that fix up props for custom elements before calling React's jsx/jsxs.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const jsx: typeof reactJsx = (type: any, props: any, key: any) =>
  reactJsx(
    type,
    typeof type === "string" ? fixCustomElementProps(type, props) : props,
    key,
  )
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const jsxs: typeof reactJsxs = (type: any, props: any, key: any) =>
  reactJsxs(
    type,
    typeof type === "string" ? fixCustomElementProps(type, props) : props,
    key,
  )

/**
 * Stage 1 (expensive): Parse a markdown string to a HAST Root.
 *
 * Runs the full unified pipeline and sanitizes URLs. The returned tree is
 * clean — no streaming dot — and is safe to cache by content string.
 */
export function parseMarkdown(
  content: string,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  processor: Processor<any, any, any, any, any>,
): Root {
  const file = new VFile(content)
  const hast = processor.runSync(processor.parse(file), file) as Root
  sanitizeUrls(hast)
  return hast
}

/**
 * Stage 2 (cheap): Convert a HAST Root to React elements.
 *
 * When streaming=true a new tree is produced with the streaming dot appended,
 * using an immutable path-copy (O(depth)) rather than a full structuredClone
 * (O(tree-size)). The original cached HAST is never mutated.
 */
export function hastToReact(
  hast: Root,
  options: {
    tagToComponentMap?: Record<string, ComponentType<unknown>>
    streaming?: boolean
  },
): ReactElement {
  const { tagToComponentMap, streaming } = options
  const tree = streaming ? withStreamingDot(hast) : hast

  return toJsxRuntime(tree, {
    Fragment,
    jsx,
    jsxs,
    components: tagToComponentMap as Record<string, ComponentType>,
    passKeys: true,
    passNode: true,
    ignoreInvalidStyle: true,
  }) as ReactElement
}
