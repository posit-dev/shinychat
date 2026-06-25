/** Thin wrapper so tests can mock navigation (jsdom can't implement it). */
export function navigateTo(url: string | null, reload = false): void {
  if (reload && url !== null) {
    window.location.assign(url)
    return
  }
  history.replaceState(null, "", url ?? window.location.pathname)
}
