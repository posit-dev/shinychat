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
}: {
  content: string
  htmlDeps: HtmlDep[]
}) {
  const shiny = useContext(ShinyLifecycleContext)
  const [depsReady, setDepsReady] = useState(htmlDeps.length === 0)

  useEffect(() => {
    if (htmlDeps.length === 0) return
    let cancelled = false
    void (async () => {
      await shiny?.renderDependencies(htmlDeps)
      if (!cancelled) setDepsReady(true)
    })()
    return () => {
      cancelled = true
    }
  }, [htmlDeps, shiny])

  if (!depsReady) return null
  return <RawHTML html={content} />
}
