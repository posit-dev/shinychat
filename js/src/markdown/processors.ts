import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkGfm from "remark-gfm"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeSanitize from "rehype-sanitize"
import rehypeHighlight from "rehype-highlight"

import { remarkEscapeHtml } from "./plugins/remarkEscapeHtml"
import { rehypeExternalLinks } from "./plugins/rehypeExternalLinks"
import { rehypeUncontrolledInputs } from "./plugins/rehypeUncontrolledInputs"
import { rehypeUnwrapBlockCEs } from "./plugins/rehypeUnwrapBlockCEs"

/**
 * Frozen processor for markdown content.
 * Includes: GFM, raw HTML parsing, external links, syntax highlighting.
 *
 * No rehypeSanitize step: the output is converted to React elements via
 * toJsxRuntime (not innerHTML), so script tags and event-handler attributes
 * are inert.
 */
export const markdownProcessor = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(remarkRehype, { allowDangerousHtml: true })
  .use(rehypeRaw)
  .use(rehypeUnwrapBlockCEs)
  .use(rehypeUncontrolledInputs)
  .use(rehypeExternalLinks)
  .use(rehypeHighlight, { detect: false, ignoreMissing: true })
  .freeze()

/**
 * Frozen processor for raw HTML content.
 * Preserves HTML fragment structure while still normalizing uncontrolled form
 * inputs and external link attributes.
 */
export const htmlProcessor = unified()
  .use(rehypeUncontrolledInputs)
  .use(rehypeExternalLinks)
  .freeze()

/**
 * Frozen processor for semi-markdown content.
 * HTML tags are escaped and displayed literally.
 * No syntax highlighting, no raw HTML passthrough.
 * Sanitization provides defense-in-depth (remarkEscapeHtml already escapes HTML).
 */
export const semiMarkdownProcessor = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(remarkEscapeHtml)
  .use(remarkRehype, { allowDangerousHtml: true })
  .use(rehypeRaw)
  .use(rehypeSanitize)
  .freeze()
