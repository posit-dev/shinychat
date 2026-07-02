/** Thin wrapper so tests can mock navigation (jsdom can't implement it). */
export function navigateTo(url: string | null, reload = false): void {
  const target = url ?? window.location.pathname
  if (reload) {
    window.location.assign(target)
    return
  }
  history.replaceState(null, "", target)
}
