export function domainFromUrl(url: string): string {
  try {
    return new URL(url).hostname || url
  } catch {
    return url
  }
}
