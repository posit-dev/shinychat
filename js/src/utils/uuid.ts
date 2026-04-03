/**
 * Generate a UUID v4 string. Uses `crypto.getRandomValues()` which,
 * unlike `crypto.randomUUID()`, is available in all browser contexts
 * (including non-secure HTTP).
 */
export function uuid(): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)

  // Set version to 4 and variant to RFC 4122.
  bytes[6] = (bytes[6]! & 0x0f) | 0x40
  bytes[8] = (bytes[8]! & 0x3f) | 0x80

  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"))

  return `${hex[0]}${hex[1]}${hex[2]}${hex[3]}-${hex[4]}${hex[5]}-${hex[6]}${hex[7]}-${hex[8]}${hex[9]}-${hex[10]}${hex[11]}${hex[12]}${hex[13]}${hex[14]}${hex[15]}`
}
