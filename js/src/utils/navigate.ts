/** Thin wrapper so tests can mock navigation (jsdom can't implement it). */
export function navigateTo(url: string | null): void {
  history.replaceState(null, "", url ?? window.location.pathname)
}
