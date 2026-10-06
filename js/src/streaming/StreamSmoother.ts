export interface StreamSmootherOptions<TMeta> {
  /**
   * Called once per paced emission with a slice of buffered text and the
   * metadata it was pushed with. `isFirstSlice` is true only for the first
   * emission derived from a given queue entry — use it to forward once-only
   * metadata (e.g. html_deps) exactly once per entry.
   */
  onEmit: (text: string, meta: TMeta, isFirstSlice: boolean) => void
  /**
   * Whether an incoming push may be appended to the still-queued tail entry
   * rather than becoming its own entry. Return true only when the two are
   * interchangeable for rendering purposes and `incoming` carries no
   * once-only metadata (it is dropped on merge). Without merging, every
   * push boundary is also a forced cut point, so pacing would replay the
   * source's chunking. Defaults to never merging.
   */
  canMerge?: (queued: TMeta, incoming: TMeta) => boolean
  /**
   * Upper bound on how long `finish()` takes to reveal whatever is still
   * buffered when the source ends. The tail drains at whichever is faster:
   * the normal pacing rate or the rate that empties it within this window.
   */
  finishDurationMs?: number
  /**
   * When true, a paced cut never leaves an emission ending inside a `<…>`
   * tag, so partial tags can't flash on screen as literal text. A cut that
   * lands inside a tag whose `>` is already buffered extends past it (tags
   * render as nothing, so revealing one whole is invisible); a tag whose
   * `>` hasn't arrived yet is held back until it does. Default true.
   */
  tagBoundaries?: boolean
  /**
   * Stall guard for `tagBoundaries`: if an unclosed tag has blocked all
   * progress for this long, emit it anyway. Bounds the delay for input
   * with stray `<` characters and no `>`. Default 1500.
   */
  maxTagHoldMs?: number
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

// Markdown markers whose meaning depends on run length (``` vs `, ** vs *).
// A cut inside such a run would briefly render — or, for code fences, make
// the chat reducer misclassify — a shorter marker, so cuts extend past them.
const RUN_CHARS = new Set(["`", "~", "*", "_"])

/**
 * Buffers pushed text and drains it on a timer at a rate proportional to
 * buffer backlog (with a floor), so a burst catches up quickly and a small
 * buffer never trickles at an unreadably slow pace. Text is revealed at
 * character granularity, independent of how the source chunked it; a
 * fractional character budget carries across ticks so slow rates still
 * advance smoothly. Entries with different metadata (per `canMerge`) are
 * never blended, so content type, trust, and html deps stay intact. Cuts
 * never split a surrogate pair, a markdown marker run, or (by default) a
 * `<…>` tag.
 */
export class StreamSmoother<TMeta> {
  private readonly onEmit: StreamSmootherOptions<TMeta>["onEmit"]
  private readonly canMerge: StreamSmootherOptions<TMeta>["canMerge"]
  private readonly finishDurationMs: number
  private readonly tagBoundaries: boolean
  private readonly maxTagHoldMs: number
  private readonly tickIntervalMs: number
  private readonly drainRate: number
  private readonly minCharsPerSecond: number
  private readonly maxTickIntervalMs: number
  private readonly overrunBackoffMultiplier: number

  private queue: QueueEntry<TMeta>[] = []
  private timer: ReturnType<typeof setTimeout> | null = null
  private currentIntervalMs: number
  // Start of the previous tick (or loop start). Elapsed time is measured
  // from here so time spent in onEmit counts toward the next tick's budget.
  private lastTickAt = 0
  // Fractional characters earned but not yet emitted.
  private budgetCarry = 0
  // Set by finish(): called once the tail has drained (or been flushed).
  private onFinished: (() => void) | null = null
  private finishCharsPerMs = 0
  /** When an unclosed tag first blocked all progress; null if not held. */
  private tagHoldStartMs: number | null = null

  constructor(options: StreamSmootherOptions<TMeta>) {
    this.onEmit = options.onEmit
    this.canMerge = options.canMerge
    this.finishDurationMs = options.finishDurationMs ?? 400
    this.tagBoundaries = options.tagBoundaries ?? true
    this.maxTagHoldMs = options.maxTagHoldMs ?? 1500
    this.tickIntervalMs = options.tickIntervalMs ?? 50
    this.drainRate = options.drainRate ?? 0.02
    this.minCharsPerSecond = options.minCharsPerSecond ?? 30
    this.maxTickIntervalMs = options.maxTickIntervalMs ?? 250
    this.overrunBackoffMultiplier = options.overrunBackoffMultiplier ?? 2
    this.currentIntervalMs = this.tickIntervalMs
  }

  push(text: string, meta: TMeta): void {
    if (text.length === 0) return
    const tail = this.queue[this.queue.length - 1]
    if (tail && this.canMerge?.(tail.meta, meta)) {
      tail.text += text
    } else {
      this.queue.push({ text, meta, emittedAny: false })
    }
    this.ensureLoopRunning()
  }

  /** True between `finish()` and the tail fully draining (or flush/dispose). */
  get finishing(): boolean {
    return this.onFinished !== null
  }

  /**
   * Signal that the source has ended: reveal the remaining buffer quickly
   * (within `finishDurationMs`) rather than all at once, then call `onDone`.
   * Calls `onDone` synchronously if nothing is buffered. A later `flush()`
   * completes the finish immediately; `dispose()` cancels `onDone`.
   */
  finish(onDone: () => void): void {
    if (this.queue.length === 0) {
      this.stopLoop()
      onDone()
      return
    }
    this.onFinished = onDone
    this.finishCharsPerMs = this.backlog() / this.finishDurationMs
    this.ensureLoopRunning()
  }

  /** Emit everything queued immediately, bypassing pacing, then stop. */
  flush(): void {
    this.stopLoop()
    const queue = this.queue
    this.queue = []
    for (const entry of queue) {
      this.onEmit(entry.text, entry.meta, !entry.emittedAny)
    }
    this.completeFinish()
  }

  /** Discard everything queued without emitting, then stop. */
  dispose(): void {
    this.stopLoop()
    this.queue = []
    this.onFinished = null
  }

  private backlog(): number {
    return this.queue.reduce((n, e) => n + e.text.length, 0)
  }

  private completeFinish(): void {
    const onFinished = this.onFinished
    this.onFinished = null
    this.finishCharsPerMs = 0
    onFinished?.()
  }

  private ensureLoopRunning(): void {
    if (this.timer !== null) return
    this.lastTickAt = Date.now()
    this.scheduleTick(this.currentIntervalMs)
  }

  private scheduleTick(intervalMs: number): void {
    this.timer = setTimeout(() => this.tick(), intervalMs)
  }

  private stopLoop(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer)
      this.timer = null
    }
    this.currentIntervalMs = this.tickIntervalMs
    this.budgetCarry = 0
    this.tagHoldStartMs = null
  }

  private tick(): void {
    this.timer = null

    const now = Date.now()
    const elapsedMs = now - this.lastTickAt
    this.lastTickAt = now
    // Congestion signal: how much longer than scheduled this tick took to
    // arrive, including the previous tick's own emit work.
    const overrunMs = Math.max(0, elapsedMs - this.currentIntervalMs)
    this.drainFor(elapsedMs)

    if (this.queue.length === 0) {
      this.budgetCarry = 0
      this.currentIntervalMs = this.tickIntervalMs
      this.completeFinish()
      return
    }

    this.currentIntervalMs = Math.min(
      this.maxTickIntervalMs,
      this.tickIntervalMs + this.overrunBackoffMultiplier * overrunMs,
    )
    this.scheduleTick(this.currentIntervalMs)
  }

  private drainFor(elapsedMs: number): void {
    // Cut positions are computed over the whole buffer, so guards (tags,
    // marker runs) see across entry boundaries.
    const text = this.queue.map((e) => e.text).join("")
    if (text.length === 0) return

    const frames = elapsedMs / REFERENCE_FRAME_MS
    const charsPerFrame = Math.max(
      text.length * this.drainRate,
      this.minCharsPerSecond / 60,
    )
    const earned = Math.max(
      charsPerFrame * frames,
      this.finishCharsPerMs * elapsedMs,
    )
    this.budgetCarry += earned
    // Epsilon absorbs float error (e.g. 50ms / (1000/60) is not exactly 3)
    // so a whole character's worth of budget isn't floored a tick late.
    const budget = Math.floor(this.budgetCarry + 1e-9)
    if (budget < 1) return

    const paced = safeCut(text, Math.min(budget, text.length))
    const cut = this.tagBoundaries ? this.snapToTagBoundary(text, paced) : paced

    if (cut < paced) {
      // Held back by an unclosed tag. Don't bank the unspent budget, or the
      // text would lurch forward once the tag closes.
      this.budgetCarry = Math.min(this.budgetCarry, earned)
      if (cut === 0) {
        this.tagHoldStartMs ??= Date.now()
        return
      }
    }

    this.tagHoldStartMs = null
    this.emitPrefix(cut)
    // A cut extended past the budget (safeCut, a buffered tag) borrows from
    // future ticks.
    this.budgetCarry = Math.max(0, this.budgetCarry - cut)
  }

  /** Emits the first `n` buffered characters, entry by entry, in order. */
  private emitPrefix(n: number): void {
    while (n > 0 && this.queue.length > 0) {
      const entry = this.queue[0]!
      if (n >= entry.text.length) {
        this.queue.shift()
        this.onEmit(entry.text, entry.meta, !entry.emittedAny)
        n -= entry.text.length
        continue
      }
      const slice = entry.text.slice(0, n)
      const isFirst = !entry.emittedAny
      entry.emittedAny = true
      entry.text = entry.text.slice(n)
      this.onEmit(slice, entry.meta, isFirst)
      n = 0
    }
  }

  /**
   * Adjusts a cut so the emitted prefix doesn't end inside a tag: past the
   * tag's `>` if it is already buffered, otherwise back to its `<` (unless
   * the source has ended, or the hold has outlasted `maxTagHoldMs`).
   *
   * A `<` counts as a tag start when followed by a letter, `/`, `!`, or `?`
   * — or by nothing yet. A `<` followed by anything else ("x < y") is not.
   */
  private snapToTagBoundary(text: string, cut: number): number {
    const lt = text.lastIndexOf("<", cut - 1)
    if (lt === -1) return cut

    const gt = text.indexOf(">", lt)
    if (gt !== -1 && gt < cut) return cut

    const next = text.charAt(lt + 1)
    if (next !== "" && !/[A-Za-z/!?]/.test(next)) return cut

    if (gt !== -1) return gt + 1

    // The tag is still arriving.
    if (this.finishing) return cut
    if (
      this.tagHoldStartMs !== null &&
      Date.now() - this.tagHoldStartMs >= this.maxTagHoldMs
    ) {
      return cut
    }
    return lt
  }
}

/**
 * Adjusts a cut position forward (never backward, so pacing never stalls)
 * so it does not split a UTF-16 surrogate pair or a run of repeated
 * markdown marker characters.
 */
function safeCut(text: string, cut: number): number {
  if (cut >= text.length) return text.length

  const code = text.charCodeAt(cut - 1)
  if (code >= 0xd800 && code <= 0xdbff) cut++

  while (
    cut < text.length &&
    RUN_CHARS.has(text.charAt(cut)) &&
    text.charAt(cut) === text.charAt(cut - 1)
  ) {
    cut++
  }
  return cut
}
