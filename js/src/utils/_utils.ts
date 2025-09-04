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

/**
 * Generate a nanoid-style random ID
 * @param prefix A prefix to prepend to the ID (e.g. "btn", "input", etc)
 * @param size The length of the random portion of the ID (default: 12)
 */
function generateRandomId(prefix: string, size = 12): string {
  const chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
  let id = ""
  // Prefer secure random when available
  if (crypto?.getRandomValues) {
    const bytes = new Uint8Array(size)
    crypto.getRandomValues(bytes)
    for (let i = 0; i < size; i++) {
      id += chars[bytes[i]! % chars.length]
    }
  } else {
    for (let i = 0; i < size; i++) {
      id += chars[Math.floor(Math.random() * chars.length)]
    }
  }
  return `${prefix}-${id}`
}

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
  generateRandomId,
}

export type { HtmlDep }
