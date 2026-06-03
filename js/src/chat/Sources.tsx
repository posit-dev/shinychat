import { memo, useMemo } from "react"
import { isSafeUrl } from "../markdown/urlSanitize"
import { parseCitations } from "./citations"

interface SourcesProps {
  content: string
}

export const Sources = memo(function Sources({ content }: SourcesProps) {
  const entries = useMemo(() => parseCitations(content), [content])
  if (entries.length === 0) return null
  return (
    <div className="shiny-chat-sources">
      <div className="shiny-chat-sources__label">Sources</div>
      <ol className="shiny-chat-sources__list">
        {entries.map((e) => (
          <li key={e.url} value={e.number}>
            {isSafeUrl(e.url) ? (
              <a href={e.url} target="_blank" rel="noopener noreferrer">
                {e.title || e.url}
              </a>
            ) : (
              e.title || e.url
            )}
          </li>
        ))}
      </ol>
    </div>
  )
})
