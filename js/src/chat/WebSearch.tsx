import { memo } from "react"

interface WebSearchProps {
  query?: string
  node?: unknown
  children?: React.ReactNode
}

export const WebSearch = memo(function WebSearch({ query }: WebSearchProps) {
  return (
    <div className="shiny-web-search">
      <span className="shiny-web-search__icon" aria-hidden="true">
        🔍
      </span>
      <span className="shiny-web-search__label">Searched the web</span>
      {query ? <span className="shiny-web-search__query">{query}</span> : null}
    </div>
  )
})
