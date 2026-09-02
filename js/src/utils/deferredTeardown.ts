// Moving a custom element in the DOM fires disconnectedCallback then
// connectedCallback synchronously in the same tick, so teardown is deferred:
// a reconnect cancels it and the live React root survives the move. If the
// element was genuinely removed, no reconnect arrives and teardown runs on
// the next tick.
export class DeferredTeardown {
  private pending: ReturnType<typeof setTimeout> | null = null

  cancel(): void {
    if (this.pending !== null) {
      clearTimeout(this.pending)
      this.pending = null
    }
  }

  schedule(teardown: () => void): void {
    this.pending = setTimeout(() => {
      this.pending = null
      teardown()
    }, 0)
  }
}
