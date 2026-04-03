/**
 * Generate a UUID v4 string. Uses `crypto.getRandomValues()` which,
 * unlike `crypto.randomUUID()`, is available in all browser contexts
 * (including non-secure HTTP).
 */
export function uuid(): string {
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
    (
      +c ^
      (crypto.getRandomValues(new Uint8Array(1))[0]! & (15 >> (+c / 4)))
    ).toString(16),
  )
}
