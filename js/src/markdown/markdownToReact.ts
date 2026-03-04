import { toJsxRuntime } from "hast-util-to-jsx-runtime"
import { Fragment, jsx, jsxs } from "react/jsx-runtime"
import { VFile } from "vfile"
import type { Root } from "hast"
import type { ReactElement, ComponentType } from "react"
import type { Processor } from "unified"

import { sanitizeUrls } from "./urlSanitize"
import { insertStreamingDot } from "./streamingDot"

export interface MarkdownToReactOptions {
  /** Which frozen processor to use */
  processor: Processor
  /** Custom component overrides (e.g., pre → CopyableCodeBlock) */
  components?: Record<string, ComponentType<unknown>>
  /** Whether to insert a streaming dot at the innermost element */
  streaming?: boolean
}

/**
 * Convert a markdown string to React elements using the unified pipeline.
 *
 * Pipeline: parse → run plugins → sanitize URLs → [streaming dot] → toJsxRuntime
 *
 * The processor should be a frozen instance (created once, reused for every render).
 */
export function markdownToReact(
  content: string,
  options: MarkdownToReactOptions,
): ReactElement {
  const { processor, components, streaming } = options

  const file = new VFile(content)
  const hast = processor.runSync(processor.parse(file), file) as Root

  // Post-pipeline URL sanitization
  sanitizeUrls(hast)

  // Insert streaming dot at AST level
  if (streaming) {
    insertStreamingDot(hast)
  }

  return toJsxRuntime(hast, {
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
