/**
 * Parse a JSON-encoded attribute value, requiring a top-level array. Returns
 * null (after warning) when the JSON is malformed or not an array, so the
 * caller can fall back to its default rendering.
 */
export function parseJsonArray(
  raw: string,
  description: string,
): unknown[] | null {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    console.warn(`Ignoring malformed ${description}: not valid JSON`)
    return null
  }
  if (!Array.isArray(parsed)) {
    console.warn(`Ignoring malformed ${description}: expected a JSON array`)
    return null
  }
  return parsed
}
