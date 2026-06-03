import { memo } from "react"
import { isSafeUrl } from "../markdown/urlSanitize"

interface WebFetchProps {
  url?: string
  status?: string
  node?: unknown
  children?: React.ReactNode
}

export const WebFetch = memo(function WebFetch({ url, status }: WebFetchProps) {
  if (!url) return null
  const ok = status !== "error"
  const safe = isSafeUrl(url)
  return (
    <div className="shiny-web-fetch">
      <span className="shiny-web-fetch__icon" aria-hidden="true">
        📄
      </span>
      <span className="shiny-web-fetch__label">Read</span>
      {safe ? (
        <a
          className="shiny-web-fetch__url"
          href={url}
          target="_blank"
          rel="noopener noreferrer"
        >
          {url}
        </a>
      ) : (
        <span className="shiny-web-fetch__url">{url}</span>
      )}
      <span
        className={`shiny-web-fetch__status shiny-web-fetch__status--${ok ? "ok" : "error"}`}
      >
        {ok ? "✓" : "✗"}
      </span>
    </div>
  )
})
