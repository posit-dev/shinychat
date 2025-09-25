import { parse, Renderer } from "marked"
import { sanitizeHTML } from "../utils/_utils"

type ContentType = "markdown" | "semi-markdown" | "html" | "text"

// 'markdown' renderer (for assistant messages)
const markdownRenderer = new Renderer()

// Add some basic Bootstrap styling to markdown tables
markdownRenderer.table = (header: string, body: string) => {
  return `<table class="table table-striped table-bordered">
      <thead>${header}</thead>
      <tbody>${body}</tbody>
    </table>`
}

const defaultMarkdownCodeRenderer = markdownRenderer.code

markdownRenderer.code = function (
  code: string,
  infostring: string | undefined,
  escaped: boolean,
): string {
  if (infostring === "{=html}") {
    return code
  }
  return defaultMarkdownCodeRenderer.call(this, code, infostring, escaped)
}

// 'semi-markdown' renderer (for user messages)
const semiMarkdownRenderer = new Renderer()

const escapeHTML = (html: string) =>
  html
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;")

// Escape HTML, not for security reasons, but just because it's confusing if the user is
// using tag-like syntax to demarcate parts of their prompt for other reasons (like
// <User>/<Assistant> for providing examples to the model), and those tags vanish.
semiMarkdownRenderer.html = escapeHTML

// Normalize all content types to HTML
// N.B. this includes parsing + santizing of markdown
function renderToHTML(content: string, contentType: ContentType): string {
  if (contentType === "html") {
    return content
  }

  if (contentType === "text") {
    return escapeHTML(content)
  }

  if (contentType.includes("markdown")) {
    const renderer =
      contentType === "semi-markdown" ? semiMarkdownRenderer : markdownRenderer
    const html = parse(content, { renderer }) as string
    return sanitizeHTML(html)
  }

  throw new Error(`Unknown content type: ${contentType}`)
}

export { renderToHTML }
export type { ContentType }
