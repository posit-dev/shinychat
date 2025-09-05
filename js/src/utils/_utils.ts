import DOMPurify from "dompurify"
import { LitElement } from "lit"

import type { HtmlDep } from "rstudio-shiny/srcts/types/src/shiny/render"

////////////////////////////////////////////////
// Lit helpers
////////////////////////////////////////////////

function createElement(
  tag_name: string,
  attrs: { [key: string]: string | null },
): HTMLElement {
  const el = document.createElement(tag_name)
  for (const [key, value] of Object.entries(attrs)) {
    // Replace _ with - in attribute names
    const attrName = key.replace(/_/g, "-")
    if (value !== null) el.setAttribute(attrName, value)
  }
  return el
}

function createSVGIcon(icon: string): HTMLElement {
  const parser = new DOMParser()
  const svgDoc = parser.parseFromString(icon, "image/svg+xml")
  return svgDoc.documentElement
}

// https://lit.dev/docs/components/shadow-dom/#implementing-createrenderroot
class LightElement extends LitElement {
  createRenderRoot() {
    return this
  }
}
////////////////////////////////////////////////
// Shiny helpers
////////////////////////////////////////////////

export type ShinyClientMessage = {
  message: string
  headline?: string
  status?: "error" | "info" | "warning"
}

function showShinyClientMessage({
  headline = "",
  message,
  status = "warning",
}: ShinyClientMessage): void {
  document.dispatchEvent(
    new CustomEvent("shiny:client-message", {
      detail: { headline: headline, message: message, status: status },
    }),
  )
}

async function renderDependencies(deps: HtmlDep[]): Promise<void> {
  if (!window.Shiny) return
  if (!deps) return

  try {
    await window.Shiny.renderDependenciesAsync(deps)
  } catch (renderError) {
    showShinyClientMessage({
      status: "error",
      message: `Failed to render HTML dependencies: ${renderError}`,
    })
  }
}

////////////////////////////////////////////////
// General helpers
////////////////////////////////////////////////

function sanitizeHTML(html: string): string {
  return sanitizer.sanitize(html, {
    // Sanitize scripts manually (see below)
    ADD_TAGS: ["script"],
    // Allow any (defined) custom element
    CUSTOM_ELEMENT_HANDLING: {
      tagNameCheck: (tagName) => {
        return window.customElements.get(tagName) !== undefined
      },
      attributeNameCheck: (attr) => true,
      allowCustomizedBuiltInElements: true,
    },
  })
}

// Allow htmlwidgets' script tags through the sanitizer
// by allowing `<script type="application/json" data-for="*"`,
// which every widget should follow, and seems generally safe.
const sanitizer = DOMPurify()
sanitizer.addHook("uponSanitizeElement", (node, data) => {
  if (node.nodeName && node.nodeName === "SCRIPT") {
    // Need to ensure node is an Element before calling getAttribute
    const element = node as Element
    const isOK =
      element.getAttribute("type") === "application/json" &&
      element.getAttribute("data-for") !== null

    data.allowedTags["script"] = isOK
  }
})

// This next section is a big workaround to prevent DOMPurify from removing
// attributes from our custom elements when they contain suspicious HTML values.
// In particular, using HTML comments in the value attribute of
// <shiny-tool-request> is something we want to allow but DOMPurify will remove
// the entire attribute. The workaround is to restore the original attributes
// after sanitization.
const originalAttributes = new WeakMap<Node, Record<string, string>>()

sanitizer.addHook("beforeSanitizeAttributes", function (node, data) {
  if (!node.tagName) return

  const isShinyToolCard = ["shiny-tool-request", "shiny-tool-result"].includes(
    node.tagName.toLowerCase(),
  )

  if (isShinyToolCard) {
    const attrs: Record<string, string> = {}
    if (node.hasAttribute("value")) attrs.value = node.getAttribute("value")!
    // We could also preserve `icon` here, but it shouldn't have the same issue
    if (Object.keys(attrs).length > 0) {
      originalAttributes.set(node, attrs)
    }
  }
})

sanitizer.addHook("afterSanitizeAttributes", function (node, data) {
  if (originalAttributes.has(node)) {
    const attrs = originalAttributes.get(node)!
    Object.entries(attrs).forEach(([name, value]) => {
      node.setAttribute(name, value)
    })
    originalAttributes.delete(node)
  }
})

/**
 * Creates a throttle decorator that ensures the decorated method isn't called more
 * frequently than the specified delay
 * @param delay The minimum time (in ms) that must pass between calls
 */
export function throttle(delay: number) {
  /* eslint-disable @typescript-eslint/no-explicit-any */
  return function (
    _target: any,
    _propertyKey: string,
    descriptor: PropertyDescriptor,
  ) {
    const originalMethod = descriptor.value
    let timeout: number | undefined

    descriptor.value = function (...args: any[]) {
      if (timeout) {
        window.clearTimeout(timeout)
      }

      timeout = window.setTimeout(() => {
        originalMethod.apply(this, args)
        timeout = undefined
      }, delay)
    }

    return descriptor
  }
}

export {
  LightElement,
  createElement,
  createSVGIcon,
  renderDependencies,
  sanitizeHTML,
  showShinyClientMessage,
}

export type { HtmlDep }
