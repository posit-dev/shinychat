import { useContext, useEffect, useState } from "react"
import { ShinyLifecycleContext } from "./context"
import { RawHTML } from "./RawHTML"
import type { HtmlDep } from "../transport/types"

/**
 * A structured `html_block` island: server-authored trusted HTML mounted
 * through the shared RawHTML sink. Block-level dependencies render BEFORE
 * the HTML mounts (ChatDrawer's ordering), so a dynamically-sent island's
 * styles/scripts are in place before its markup — and its Shiny bindings —
 * attach.
 *
 * Shared by Chat (message blocks) and MarkdownStream (stream segments).
 */
export function HtmlBlockContent({
  content,
  htmlDeps,
  onMounted,
}: {
  content: string
  htmlDeps: HtmlDep[]
  /**
   * Called after the island's HTML actually mounts (i.e. once the deps
   * gate resolves and RawHTML's innerHTML effect has run). A deps-gated
   * island grows the DOM well after it first rendered (null), so parents
   * whose layout logic keyed on the initial render — e.g. MarkdownStream's
   * scroll-parent discovery — use this to re-run it.
   */
  onMounted?: () => void
}) {
  const shiny = useContext(ShinyLifecycleContext)
  // Readiness is tracked against the CURRENT htmlDeps identity, not the
  // props the instance mounted with: React reuses this component when a
  // block is replaced at the same position (e.g. a MarkdownStream replace
  // swapping one block for another, or a Chat message update). `readyDeps`
  // records which deps array finished loading; a replacement with different
  // deps re-gates (its HTML never mounts before the new deps load), and a
  // dependency-free replacement ungates immediately instead of stranding
  // behind a stale pending gate.
  const [readyDeps, setReadyDeps] = useState<HtmlDep[] | null>(null)

  useEffect(() => {
    if (htmlDeps.length === 0) return
    let cancelled = false
    void (async () => {
      await shiny?.renderDependencies(htmlDeps)
      if (!cancelled) setReadyDeps(htmlDeps)
    })()
    return () => {
      cancelled = true
    }
  }, [htmlDeps, shiny])

  const depsReady = htmlDeps.length === 0 || readyDeps === htmlDeps

  // Child effects run before this one, so when depsReady flips true the
  // island's HTML is already in the DOM.
  useEffect(() => {
    if (depsReady) onMounted?.()
  }, [depsReady, onMounted])

  if (!depsReady) return null
  return <RawHTML html={content} />
}
