import {
  DirectiveParameters,
  PartInfo,
  PartType,
  ChildPart,
} from "lit-html/directive.js"
import { AsyncDirective, directive } from "lit/async-directive.js"
import { noChange, html } from "lit-html"
import { LitElement } from "lit"
import { unsafeHTML } from "lit-html/directives/unsafe-html.js"
import morphdom from "morphdom"

import { renderToHTML } from "./markdown-renderer.js"
import type { ContentType } from "./markdown-renderer.js"
import { createSVGIcon, throttle } from "../utils/_utils"
import { findInnermostStreamingElement } from "./utils.js"

// SVG dot to indicate content is currently streaming
const SVG_DOT_CLASS = "markdown-stream-dot"
const SVG_DOT = createSVGIcon(
  `<svg width="12" height="12" xmlns="http://www.w3.org/2000/svg" class="${SVG_DOT_CLASS}" style="margin-left:.25em;margin-top:-.25em"><circle cx="6" cy="6" r="6"/></svg>`,
)

function removeStreamingDot(htmlContainer: HTMLElement): void {
  htmlContainer.querySelector(`svg.${SVG_DOT_CLASS}`)?.remove()
}

function appendStreamingDot(htmlContainer: HTMLElement): void {
  // When message starts, we may still be waiting for the first meaningful
  // chunk, and in that case, the message icon should indicate progress
  if (htmlContainer.children.length === 0) {
    return
  }
  // Tool requests already indicate progress
  // TODO: could also be done via CSS?
  if (
    htmlContainer?.lastElementChild?.tagName.toLowerCase() ===
    "shiny-tool-request"
  ) {
    return
  }
  const innerEl = findInnermostStreamingElement(htmlContainer)
  innerEl.appendChild(SVG_DOT)
}

// Wrap content in a <div> so that we can morph that div instead
// of the lit container itself
const CONTENT_CONTAINER_CLASS = "content-container"
function renderToHTMLContainer(content: string, contentType: ContentType) {
  return `<div class="${CONTENT_CONTAINER_CLASS}">
      ${renderToHTML(content, contentType)}
    </div>`
}
// Given the (host) lit Element, get the actual HTML container
function getHTMLContainer(container: LitElement): HTMLElement {
  return container.querySelector(`.${CONTENT_CONTAINER_CLASS}`) as HTMLElement
}

class IncrementalHTMLStream extends AsyncDirective {
  // The content string from the previous render
  private lastContent: string = ""
  // The content type of the previous render
  private lastContentType: ContentType | null = null

  constructor(partInfo: PartInfo) {
    super(partInfo)
    if (partInfo.type !== PartType.CHILD) {
      throw new Error(
        "IncrementalHTMLStream directive must be used in a child position",
      )
    }
  }

  // Defines the input parameters to incrementalHTMLStream() (and
  // therefore what update() receives as its 2nd argument)
  render(content: string, contentType: ContentType, streaming: boolean) {
    return ""
  }

  // Imperatively update the DOM so that it can be incrementally morphed
  // https://lit.dev/docs/templates/custom-directives/#imperative-dom-access:-update()
  update(
    part: ChildPart,
    [content, contentType, streaming]: DirectiveParameters<this>,
  ) {
    const container = part.parentNode
    if (!(container instanceof LitElement)) {
      throw new Error(
        `IncrementalHTMLStream.update() expects a LitElement, not a ${typeof container}`,
      )
    }

    // Do a full (re)-render if the content type has changed or if the
    // new content doesn't start with the previous content
    if (
      contentType !== this.lastContentType ||
      !content.startsWith(this.lastContent)
    ) {
      const html = renderToHTMLContainer(content, contentType)
      this.lastContent = content
      this.lastContentType = contentType
      // TODO: This is technically a problem for MarkdownStream() since there
      // will be no progress indication when the stream first starts
      return unsafeHTML(html)
    }

    if (content !== this.lastContent) {
      // TODO: prevent a scenario of a re-render occurring in-between throttled updates
      this._doIncrementalUpdate(container, content, contentType)
      this.lastContent = content
      this.lastContentType = contentType
    }

    // After morphing add/remove the streaming dot
    const htmlContainer = getHTMLContainer(container)
    if (streaming) {
      appendStreamingDot(htmlContainer)
    } else {
      removeStreamingDot(htmlContainer)
    }

    return noChange
  }

  // Reset state when directive is disconnected
  disconnected() {
    this.lastContent = ""
    this.lastContentType = null
  }

  // TODO: throttle the update?
  private _doIncrementalUpdate(
    container: LitElement,
    content: string,
    contentType: ContentType,
  ) {
    // Morph the HTML container div (not the lit container itself)
    const from = getHTMLContainer(container)
    const toString = renderToHTMLContainer(content, contentType)
    morphdom(from, toString, {
      onBeforeElUpdated: (fromEl: Element, toEl: Element) => {
        const fromTag = fromEl.tagName.toLowerCase()
        // Don't ever update tool displays
        if (["shiny-tool-request", "shiny-tool-result"].includes(fromTag)) {
          return false
        }
        // Allow for an opt-into preventing an update
        // TODO: better name? How to document?
        if (fromEl.hasAttribute("data-shinychat-cache-render")) {
          return false
        }
        return true
      },
    })
  }
}

export const incrementalHTMLStream = directive(IncrementalHTMLStream)
