import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkGfm from "remark-gfm"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeSanitize from "rehype-sanitize"
import rehypeHighlight from "rehype-highlight"

import { remarkRawHtml } from "./plugins/remarkRawHtml"
import { remarkEscapeHtml } from "./plugins/remarkEscapeHtml"
import { rehypeExternalLinks } from "./plugins/rehypeExternalLinks"
import { customSchema } from "./plugins/sanitizeSchema"

/**
 * Frozen processor for assistant messages.
 * Includes: GFM, {=html} passthrough, raw HTML parsing, sanitization,
 * external links, syntax highlighting.
 *
 * SECURITY: remarkRawHtml is ONLY used here, never for user messages.
 */
export const assistantProcessor = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(remarkRawHtml)
  .use(remarkRehype, { allowDangerousHtml: true })
  .use(rehypeRaw)
  .use(rehypeSanitize, customSchema)
  .use(rehypeExternalLinks)
  .use(rehypeHighlight, { detect: false, ignoreMissing: true })
  .freeze()

/**
 * Frozen processor for user messages (semi-markdown).
 * HTML tags are escaped and displayed literally.
 * No syntax highlighting, no raw HTML passthrough.
 */
export const userProcessor = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(remarkEscapeHtml)
  .use(remarkRehype, { allowDangerousHtml: true })
  .use(rehypeRaw)
  .use(rehypeSanitize, customSchema)
  .freeze()
