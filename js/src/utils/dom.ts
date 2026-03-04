// DOM helper utilities extracted from _utils.ts

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

export { createElement, createSVGIcon }
