import type { CitationEntry } from "./citations"
import { isSafeUrl } from "../markdown/urlSanitize"

// Matches <shiny-citation ...> elements in both void/self-closing and paired-tag forms.
// These elements have no children so the paired form is always <shiny-citation ...></shiny-citation>.
const CITATION_ELEMENT_RE =
  /<shiny-citation\b[^>]*\/?>(?:<\/shiny-citation>)?/gi

/**
 * Returns an array of [start, end] index pairs for fenced code blocks in `text`.
 * Used to avoid inserting markers inside code fences.
 */
function fencedCodeRegions(text: string): [number, number][] {
  const regions: [number, number][] = []
  // Match ``` fenced code blocks (optionally with a language tag).
  // We do a simple scan: find the opening fence, then the closing fence.
  const fenceRe = /```/g
  let match: RegExpExecArray | null
  let openAt = -1
  while ((match = fenceRe.exec(text)) !== null) {
    if (openAt === -1) {
      openAt = match.index
    } else {
      regions.push([openAt, match.index + match[0].length])
      openAt = -1
    }
  }
  // An unclosed fence extends to end of string
  if (openAt !== -1) {
    regions.push([openAt, text.length])
  }
  return regions
}

function isInsideFence(
  index: number,
  length: number,
  regions: [number, number][],
): boolean {
  const end = index + length
  return regions.some(([rStart, rEnd]) => index < rEnd && end > rStart)
}

/**
 * Given a block's content and the message's citation entries, return content with:
 *  (a) <shiny-citation ...> carrier elements removed, and
 *  (b) a superscript marker inserted immediately after the first occurrence of
 *      each entry's cited_text found in this block (skipping already-placed entries).
 *
 * @param content   The raw markdown/HTML string for a single content block.
 * @param entries   All citation entries for the message (from parseCitations).
 * @param placed    Mutable set of entry numbers already placed in earlier blocks.
 */
export function insertCitationMarkers(
  content: string,
  entries: CitationEntry[],
  placed: Set<number>,
): string {
  // Step (a): strip <shiny-citation ...> elements so their attribute text
  // is not matched by the cited_text search below.
  const stripped = content.replace(CITATION_ELEMENT_RE, "")

  if (entries.length === 0) return stripped

  const fences = fencedCodeRegions(stripped)

  // Collect insertions: { index: number after which to insert, marker: string }
  // We process them in insertion order, then apply from right-to-left to avoid
  // offset drift.
  const insertions: { at: number; marker: string }[] = []

  for (const entry of entries) {
    if (placed.has(entry.number)) continue
    const ct = entry.cited_text
    if (!ct) continue

    const idx = stripped.indexOf(ct)
    if (idx === -1) continue

    // Skip matches inside fenced code regions
    if (isInsideFence(idx, ct.length, fences)) continue

    placed.add(entry.number)

    const markerInner = isSafeUrl(entry.url)
      ? `<a href="${entry.url}" target="_blank" rel="noopener noreferrer">${entry.number}</a>`
      : String(entry.number)

    insertions.push({
      at: idx + ct.length,
      marker: `<sup class="shiny-citation-marker">${markerInner}</sup>`,
    })
  }

  if (insertions.length === 0) return stripped

  // Apply insertions right-to-left to keep earlier offsets valid
  insertions.sort((a, b) => b.at - a.at)
  let result = stripped
  for (const { at, marker } of insertions) {
    result = result.slice(0, at) + marker + result.slice(at)
  }
  return result
}
