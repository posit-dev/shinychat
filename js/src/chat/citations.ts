import type { AsideEntry } from "./AsideGroup"

export interface CitationEntry {
  url: string
  domain?: string
  title?: string
}

/**
 * Project normalized citation asides into the message's Sources summary model.
 * Hand-authored asides have no citation metadata and are ignored.
 */
export function citationEntriesFromAsides(
  entries: AsideEntry[],
): CitationEntry[] {
  return entries
    .filter((entry) => entry.citation != null)
    .map((entry) => ({
      url: entry.url ?? "",
      domain: entry.label,
      title: entry.citation?.title,
    }))
    .filter((e) => e.url !== "")
}

/**
 * Collapse citation entries to one per URL, in first-seen order, keeping the
 * first non-empty title encountered for each URL.
 */
export function mergeCitations(entries: CitationEntry[]): CitationEntry[] {
  const byUrl = new Map<string, CitationEntry>()
  for (const e of entries) {
    const existing = byUrl.get(e.url)
    if (!existing) byUrl.set(e.url, { ...e })
    else if (!existing.title && e.title) existing.title = e.title
  }
  return [...byUrl.values()]
}
