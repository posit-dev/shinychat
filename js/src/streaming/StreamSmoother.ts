export interface StreamSmootherOptions<TMeta> {
  /**
   * Called once per paced emission with a slice of buffered text and the
   * metadata it was pushed with. `isFirstSlice` is true only for the first
   * emission derived from a given `push()` call — use it to forward
   * once-only metadata (e.g. html_deps) exactly once per push.
   */
  onEmit: (text: string, meta: TMeta, isFirstSlice: boolean) => void
  tickIntervalMs?: number
  drainRate?: number
  minCharsPerSecond?: number
  maxTickIntervalMs?: number
  overrunBackoffMultiplier?: number
}

interface QueueEntry<TMeta> {
  text: string
  meta: TMeta
  emittedAny: boolean
}

const REFERENCE_FRAME_MS = 1000 / 60

/**
 * Buffers pushed text and drains it on a timer at a rate proportional to
 * buffer backlog (with a floor), so a burst catches up quickly and a small
 * buffer never trickles at an unreadably slow pace. Each `push()` is queued
 * as its own entry — entries are never merged, so metadata boundaries
 * (content type, trust, html deps) are never split or blended across pushes.
 */
export class StreamSmoother<TMeta> {
  private readonly onEmit: StreamSmootherOptions<TMeta>["onEmit"]
  private readonly tickIntervalMs: number
  private readonly drainRate: number
  private readonly minCharsPerSecond: number
  private readonly maxTickIntervalMs: number
  private readonly overrunBackoffMultiplier: number

  private queue: QueueEntry<TMeta>[] = []
  private timer: ReturnType<typeof setTimeout> | null = null
  private currentIntervalMs: number
  private nextTickAt = 0

  constructor(options: StreamSmootherOptions<TMeta>) {
    this.onEmit = options.onEmit
    this.tickIntervalMs = options.tickIntervalMs ?? 50
    this.drainRate = options.drainRate ?? 0.02
    this.minCharsPerSecond = options.minCharsPerSecond ?? 30
    this.maxTickIntervalMs = options.maxTickIntervalMs ?? 250
    this.overrunBackoffMultiplier = options.overrunBackoffMultiplier ?? 2
    this.currentIntervalMs = this.tickIntervalMs
  }

  push(text: string, meta: TMeta): void {
    if (text.length === 0) return
    this.queue.push({ text, meta, emittedAny: false })
    this.ensureLoopRunning()
  }

  /** Emit everything queued immediately, bypassing pacing, then stop. */
  flush(): void {
    this.stopLoop()
    for (const entry of this.queue) {
      this.onEmit(entry.text, entry.meta, !entry.emittedAny)
    }
    this.queue = []
  }

  /** Discard everything queued without emitting, then stop. */
  dispose(): void {
    this.stopLoop()
    this.queue = []
  }

  private ensureLoopRunning(): void {
    if (this.timer !== null) return
    this.scheduleTick(this.currentIntervalMs)
  }

  private scheduleTick(intervalMs: number): void {
    this.nextTickAt = Date.now() + intervalMs
    this.timer = setTimeout(() => this.tick(), intervalMs)
  }

  private stopLoop(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer)
      this.timer = null
    }
    this.currentIntervalMs = this.tickIntervalMs
  }

  private tick(): void {
    this.timer = null

    const now = Date.now()
    const overrunMs = Math.max(0, now - this.nextTickAt)
    this.drainFor(this.currentIntervalMs + overrunMs)

    if (this.queue.length === 0) return

    this.currentIntervalMs =
      overrunMs > 0
        ? Math.min(
            this.maxTickIntervalMs,
            this.currentIntervalMs * this.overrunBackoffMultiplier,
          )
        : this.tickIntervalMs
    this.scheduleTick(this.currentIntervalMs)
  }

  private drainFor(elapsedMs: number): void {
    const backlog = this.queue.reduce((n, e) => n + e.text.length, 0)
    if (backlog === 0) return

    const frames = elapsedMs / REFERENCE_FRAME_MS
    const proportional = backlog * this.drainRate * frames
    const floor = (this.minCharsPerSecond * elapsedMs) / 1000
    let budget = Math.max(1, Math.round(Math.max(proportional, floor)))

    while (budget > 0 && this.queue.length > 0) {
      const entry = this.queue[0]
      if (budget >= entry.text.length) {
        this.onEmit(entry.text, entry.meta, !entry.emittedAny)
        budget -= entry.text.length
        this.queue.shift()
        continue
      }

      const cut = this.snapToWordBoundary(entry.text, budget)
      if (cut === 0) {
        // No word boundary within budget; wait for next tick
        break
      }
      this.onEmit(entry.text.slice(0, cut), entry.meta, !entry.emittedAny)
      entry.emittedAny = true
      entry.text = entry.text.slice(cut)
      budget -= cut
    }
  }

  /**
   * Finds the last whitespace at or before `maxLen`, so a synthetic pacing
   * cut never lands mid-word. If no whitespace exists within the budget but
   * one exists beyond it, returns 0 to wait for a larger budget. If no
   * whitespace exists anywhere, returns `maxLen` to make progress.
   */
  private snapToWordBoundary(text: string, maxLen: number): number {
    if (maxLen >= text.length) return text.length

    // Try to find whitespace within the budget
    for (let i = maxLen - 1; i >= 0; i--) {
      if (/\s/.test(text[i])) return i + 1
    }

    // No whitespace within budget; check if any exists beyond it
    for (let i = maxLen; i < text.length; i++) {
      if (/\s/.test(text[i])) return 0 // Wait for larger budget
    }

    // No whitespace anywhere; cut at budget to guarantee progress
    return maxLen
  }
}
