import { memo, useMemo } from "react"
import { isSafeUrl } from "../markdown/urlSanitize"

interface SourcesProps {
  content: string
}

interface SourceEntry {
  url: string
  title?: string
}

function parseCitations(content: string): SourceEntry[] {
  if (typeof document === "undefined" || !content.includes("shiny-citation")) {
    return []
  }
  const tpl = document.createElement("template")
  tpl.innerHTML = content
  const els = tpl.content.querySelectorAll("shiny-citation")
  const seen = new Set<string>()
  const out: SourceEntry[] = []
  els.forEach((el) => {
    const url = el.getAttribute("url")
    if (!url || seen.has(url)) return
    seen.add(url)
    out.push({ url, title: el.getAttribute("title") || undefined })
  })
  return out
}

export const Sources = memo(function Sources({ content }: SourcesProps) {
  const sources = useMemo(() => parseCitations(content), [content])
  if (sources.length === 0) return null
  return (
    <div className="shiny-chat-sources">
      <div className="shiny-chat-sources__label">Sources</div>
      <ol className="shiny-chat-sources__list">
        {sources.map((s) => (
          <li key={s.url}>
            {isSafeUrl(s.url) ? (
              <a href={s.url} target="_blank" rel="noopener noreferrer">
                {s.title || s.url}
              </a>
            ) : (
              s.title || s.url
            )}
          </li>
        ))}
      </ol>
    </div>
  )
})
