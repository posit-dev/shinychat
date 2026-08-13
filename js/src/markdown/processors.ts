import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkGfm from "remark-gfm"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeSanitize from "rehype-sanitize"
import rehypeHighlight from "rehype-highlight"

import { rehypeAccessibleSuggestions } from "./plugins/rehypeAccessibleSuggestions"
import { rehypeSuggestionCards } from "./plugins/rehypeSuggestionCards"
import { remarkEscapeHtml } from "./plugins/remarkEscapeHtml"
import { rehypeExternalLinks } from "./plugins/rehypeExternalLinks"
import { rehypeUncontrolledInputs } from "./plugins/rehypeUncontrolledInputs"
import { rehypeUnwrapBlockCEs } from "./plugins/rehypeUnwrapBlockCEs"
import { rehypeGroupWebActivity } from "./plugins/rehypeGroupWebActivity"
import { rehypeGroupAsides } from "./plugins/rehypeGroupAsides"
import { rehypeGroundedAsides } from "./plugins/rehypeGroundedAsides"
import { rehypeMarkTrailingAsides } from "./plugins/markTrailingAsides"
import { rehypeLazyContinuation } from "./plugins/rehypeLazyContinuation"
import {
  rehypeRewriteAsideToTemplate,
  rehypeRewriteAsideFromTemplate,
} from "./plugins/rewriteAsideTemplate"
import { remarkNormalizeListItemAsides } from "./plugins/normalizeAsideMarkdown"

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
  .use(remarkNormalizeListItemAsides)
  .use(remarkRehype, { allowDangerousHtml: true })
  .use(rehypeRewriteAsideToTemplate)
  .use(rehypeRaw)
  .use(rehypeRewriteAsideFromTemplate)
  .use(rehypeLazyContinuation)
  .use(rehypeUnwrapBlockCEs)
  .use(rehypeGroupWebActivity)
  .use(rehypeGroundedAsides)
  .use(rehypeGroupAsides)
  .use(rehypeMarkTrailingAsides)
  .use(rehypeUncontrolledInputs)
  .use(rehypeAccessibleSuggestions)
  .use(rehypeSuggestionCards)
  .use(rehypeExternalLinks)
  .use(rehypeHighlight, { detect: false, ignoreMissing: true })
  .freeze()

/**
 * Frozen processor for raw HTML content.
 * Preserves HTML fragment structure while still normalizing uncontrolled form
 * inputs, external link attributes, and <shiny-aside> grouping.
 *
 * No rehypeLazyContinuation/rehypeUnwrapBlockCEs: those work around quirks of
 * markdown parsers wrapping inline HTML in <p> tags, which doesn't apply to a
 * parse5-parsed HTML fragment.
 */
export const htmlProcessor = unified()
  .use(rehypeGroupWebActivity)
  .use(rehypeGroundedAsides)
  .use(rehypeGroupAsides)
  .use(rehypeMarkTrailingAsides)
  .use(rehypeUncontrolledInputs)
  .use(rehypeAccessibleSuggestions)
  .use(rehypeSuggestionCards)
  .use(rehypeExternalLinks)
  .freeze()

/**
 * Frozen processor for user message markdown content.
 * HTML tags are escaped and displayed literally.
 * No syntax highlighting, no raw HTML passthrough.
 * Sanitization provides defense-in-depth (remarkEscapeHtml already escapes HTML).
 */
export const userMarkdownProcessor = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(remarkEscapeHtml)
  .use(remarkRehype, { allowDangerousHtml: true })
  .use(rehypeRaw)
  .use(rehypeSanitize)
  .freeze()
