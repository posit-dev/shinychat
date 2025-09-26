import {
  directive,
  Directive,
  DirectiveParameters,
  PartInfo,
  PartType,
  ChildPart,
} from "lit-html/directive.js"
import { noChange, html } from "lit-html"
import { LitElement } from "lit"
import { unsafeHTML } from "lit-html/directives/unsafe-html.js"
import morphdom from "morphdom"

import { renderToHTML } from "./markdown-renderer.js"
import type { ContentType } from "./markdown-renderer.js"
import { createSVGIcon, throttle } from "../utils/_utils"
import { findInnermostStreamingElement } from "./utils.js"

class IncrementalHTMLStream extends Directive {
  private hasRendered = false
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

    if (!this.hasRendered) {
      this.hasRendered = true
      if (streaming && !content) {
        return html`${unsafeHTML(renderToHTMLContainer(SVG_DOT, "html"))}`
      } else {
        return html`${unsafeHTML(renderToHTMLContainer(content, contentType))}`
      }
    }

    // TODO: this is a workaround for a stream going from true -> false,
    // but the content hasn't changed (because the content updated callbacks don't fire)
    // We might want to rethink this logic so we don't have to track lastContent/lastContentType,
    // possibly by only using this directive when streaming is relevant
    if (content === this.lastContent && contentType === this.lastContentType) {
      removeStreamingDot(getHTMLContainer(container))
      return noChange
    }

    this._doIncrementalUpdate(container, content, contentType)
    this.lastContent = content
    this.lastContentType = contentType

    // After morphing add/remove the streaming dot
    const htmlContainer = getHTMLContainer(container)
    if (streaming) {
      appendStreamingDot(htmlContainer)
    } else {
      removeStreamingDot(htmlContainer)
    }

    return noChange
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

// SVG dot to indicate content is currently streaming
const SVG_DOT_CLASS = "markdown-stream-dot"
const SVG_DOT = `<svg width="12" height="12" xmlns="http://www.w3.org/2000/svg" class="${SVG_DOT_CLASS}" style="margin-left:.25em;margin-top:-.25em"><circle cx="6" cy="6" r="6"/></svg>`
const SVG_DOT_EL = createSVGIcon(SVG_DOT)

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
  innerEl.appendChild(SVG_DOT_EL)
}

export const incrementalHTMLStream = directive(IncrementalHTMLStream)
