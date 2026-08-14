import type { CSSProperties } from "react"

export interface PortalTheme {
  theme?: string
  style: CSSProperties & Record<`--${string}`, string>
}

export function portalTheme(reference: globalThis.Element | null): PortalTheme {
  const style: PortalTheme["style"] = {}
  if (!(reference instanceof HTMLElement)) return { style }

  const computed = getComputedStyle(reference)
  for (let index = 0; index < computed.length; index += 1) {
    const property = computed.item(index)
    if (!property.startsWith("--bs-")) continue
    const value = computed.getPropertyValue(property).trim()
    if (value) style[property as `--${string}`] = value
  }

  const theme = reference
    .closest<HTMLElement>("[data-bs-theme]")
    ?.getAttribute("data-bs-theme")
  return { theme: theme || undefined, style }
}
