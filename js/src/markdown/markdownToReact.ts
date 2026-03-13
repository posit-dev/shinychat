import { toJsxRuntime } from "hast-util-to-jsx-runtime"
import { Fragment, jsx, jsxs } from "react/jsx-runtime"
import { VFile } from "vfile"
import type { Root } from "hast"
import type { ReactElement, ComponentType } from "react"
import type { Processor } from "unified"

import { sanitizeUrls } from "./urlSanitize"
import { withStreamingDot } from "./streamingDot"

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
    components?: Record<string, ComponentType<unknown>>
    streaming?: boolean
  },
): ReactElement {
  const { components, streaming } = options
  const tree = streaming ? withStreamingDot(hast) : hast

  return toJsxRuntime(tree, {
    Fragment,
    jsx,
    jsxs,
    components: components as Record<string, ComponentType>,
    passKeys: true,
    passNode: true,
    elementAttributeNameCase: "html",
    ignoreInvalidStyle: true,
  }) as ReactElement
}
