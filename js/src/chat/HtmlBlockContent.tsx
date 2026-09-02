import { useContext, useEffect, useState } from "react"
import { ShinyLifecycleContext } from "./context"
import { RawHTML } from "./RawHTML"
import type { HtmlDep } from "../transport/types"

/**
 * A structured `html_block` island: server-authored trusted HTML mounted
 * through the shared RawHTML sink. Block-level dependencies render before
 * the HTML mounts. Shared by Chat (message blocks) and MarkdownStream
 * (stream segments).
 */
export function HtmlBlockContent({
  content,
  htmlDeps,
  onMounted,
}: {
  content: string
  htmlDeps: HtmlDep[]
  /**
   * Called after the island's HTML mounts (once the deps gate resolves and
   * RawHTML's innerHTML effect has run).
   */
  onMounted?: () => void
}) {
  const shiny = useContext(ShinyLifecycleContext)
  // Readiness tracks the CURRENT htmlDeps identity: React reuses this
  // component when a block is replaced in place, so new deps must re-gate.
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
