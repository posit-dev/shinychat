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
import { rehypeCEBooleans } from "./plugins/rehypeCEBooleans"
import { rehypeUnwrapBlockCEs } from "./plugins/rehypeUnwrapBlockCEs"

/**
 * Frozen processor for assistant messages.
 * Includes: GFM, raw HTML parsing, external links, syntax highlighting.
 *
 * No rehypeSanitize step: the output is converted to React elements via
 * toJsxRuntime (not innerHTML), so script tags and event-handler attributes
 * are inert. Sanitization is applied only to user messages as defense-in-depth.
 */
export const assistantProcessor = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(remarkRehype, { allowDangerousHtml: true })
  .use(rehypeRaw)
  .use(rehypeUnwrapBlockCEs)
  .use(rehypeCEBooleans)
  .use(rehypeUncontrolledInputs)
  .use(rehypeExternalLinks)
  .use(rehypeHighlight, { detect: false, ignoreMissing: true })
  .freeze()

/**
 * Frozen processor for user messages (semi-markdown).
 * HTML tags are escaped and displayed literally.
 * No syntax highlighting, no raw HTML passthrough.
 * Sanitization provides defense-in-depth (remarkEscapeHtml already escapes HTML).
 */
export const userProcessor = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(remarkEscapeHtml)
  .use(remarkRehype, { allowDangerousHtml: true })
  .use(rehypeRaw)
  .use(rehypeSanitize)
  .freeze()
