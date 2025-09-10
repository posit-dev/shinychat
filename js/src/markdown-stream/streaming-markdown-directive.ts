import { directive, Directive, PartInfo, PartType } from "lit-html/directive.js"
import { noChange } from "lit-html"
import { parse, Renderer } from "marked"
import morphdom from "morphdom"
import { sanitizeHTML } from "../utils/_utils"

interface StreamingState {
  lastContent: string
  lastHTML: string
  container: HTMLElement | null
}

class StreamingMarkdownDirective extends Directive {
  private state: StreamingState = {
    lastContent: "",
    lastHTML: "",
    container: null,
  }

  constructor(partInfo: PartInfo) {
    super(partInfo)
    if (partInfo.type !== PartType.CHILD) {
      throw new Error(
        "streamingMarkdown directive must be used in a child position",
      )
    }
  }

  render(content: string, renderer: Renderer) {
    // If content hasn't changed, don't update
    if (content === this.state.lastContent) {
      return noChange
    }

    // If this is the first render or content was replaced (shorter than before)
    if (
      !this.state.container ||
      content.length < this.state.lastContent.length
    ) {
      const html = parse(content, { renderer })
      const sanitizedHTML = sanitizeHTML(html as string)
      this.state.lastContent = content
      this.state.lastHTML = sanitizedHTML

      // Create a container div that we'll morph
      const container = document.createElement("div")
      container.innerHTML = sanitizedHTML
      this.state.container = container

      return container
    }

    // For incremental updates, parse the new content and use morphdom
    const newHTML = parse(content, { renderer })
    const sanitizedNewHTML = sanitizeHTML(newHTML as string)

    if (sanitizedNewHTML !== this.state.lastHTML) {
      const newContainer = document.createElement("div")
      newContainer.innerHTML = sanitizedNewHTML

      // Use morphdom to efficiently update only the changed parts
      morphdom(this.state.container, newContainer, {
        // Preserve input focus and selection
        onBeforeElUpdated: (fromEl: Element, toEl: Element) => {
          // Preserve focus on input elements
          if (fromEl.tagName === "INPUT" && fromEl === document.activeElement) {
            const caretPos = (fromEl as HTMLInputElement).selectionStart
            requestAnimationFrame(() => {
              ;(fromEl as HTMLInputElement).focus()
              if (caretPos !== null) {
                ;(fromEl as HTMLInputElement).setSelectionRange(
                  caretPos,
                  caretPos,
                )
              }
            })
          }
          return true
        },
        // Don't morph script tags or other sensitive elements
        onBeforeNodeDiscarded: (node: Node) => {
          if (node.nodeType === Node.ELEMENT_NODE) {
            const el = node as Element
            return !["script", "style", "link"].includes(
              el.tagName.toLowerCase(),
            )
          }
          return true
        },
      })

      this.state.lastHTML = sanitizedNewHTML
    }

    this.state.lastContent = content
    return noChange // Container is already updated via morphdom
  }

  // Reset state when directive is disconnected
  disconnected() {
    this.state = {
      lastContent: "",
      lastHTML: "",
      container: null,
    }
  }
}

export const streamingMarkdown = directive(StreamingMarkdownDirective)
