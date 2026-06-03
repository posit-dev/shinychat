export interface CitationEntry {
  url: string
  title?: string
  cited_text?: string
  number: number
}

/**
 * Parse <shiny-citation> elements from message content; dedupe by url (first-seen),
 * assign 1-based numbers. Returns entries in first-seen order.
 */
export function parseCitations(content: string): CitationEntry[] {
  if (typeof document === "undefined" || !content.includes("shiny-citation")) {
    return []
  }
  const tpl = document.createElement("template")
  tpl.innerHTML = content
  const els = tpl.content.querySelectorAll("shiny-citation")
  const seen = new Set<string>()
  const out: CitationEntry[] = []
  els.forEach((el) => {
    const url = el.getAttribute("url")
    if (!url || seen.has(url)) return
    seen.add(url)
    out.push({
      url,
      title: el.getAttribute("title") || undefined,
      cited_text: el.getAttribute("cited-text") || undefined,
      number: out.length + 1,
    })
  })
  return out
}
