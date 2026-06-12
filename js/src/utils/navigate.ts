/** Thin wrapper so tests can mock navigation (jsdom can't implement it). */
export function navigateTo(url: string): void {
  window.location.assign(url)
}
