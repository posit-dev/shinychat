import { memo, useState } from "react"
import { FloatingPortal, FloatingFocusManager } from "@floating-ui/react"
import { faviconUrl } from "./AsideGroup"
import { useCitations } from "./citationCollector"
import type { CitationEntry } from "./citations"
import { useDismissiblePopover } from "./useDismissiblePopover"

const MAX_STACK = 3

function Favicon({ url }: { url: string }) {
  const src = faviconUrl(url)
  const [failed, setFailed] = useState(false)
  if (!src || failed)
    return (
      <span
        className="shiny-sources-favicon shiny-sources-favicon--blank"
        aria-hidden="true"
      />
    )
  return (
    <img
      className="shiny-sources-favicon"
      src={src}
      alt=""
      onError={() => setFailed(true)}
    />
  )
}

export function SourcesSummaryView({ sources }: { sources: CitationEntry[] }) {
  const [open, setOpen] = useState(false)
  const { refs, floatingStyles, context, getReferenceProps, getFloatingProps } =
    useDismissiblePopover(open, setOpen)

  if (sources.length === 0) return null
  const label = `Sources, ${sources.length} ${sources.length === 1 ? "source" : "sources"}`

  return (
    <div className="shiny-sources">
      <button
        ref={refs.setReference}
        type="button"
        className="shiny-sources-pill"
        aria-label={label}
        {...getReferenceProps()}
      >
        <span className="shiny-sources-pill__stack">
          {sources.slice(0, MAX_STACK).map((s) => (
            <Favicon key={s.url} url={s.url} />
          ))}
        </span>
        <span className="shiny-sources-pill__label">Sources</span>
      </button>
      {open && (
        <FloatingPortal>
          <FloatingFocusManager
            context={context}
            modal={false}
            initialFocus={-1}
            returnFocus
          >
            <div
              ref={refs.setFloating}
              className="shiny-sources-popover"
              style={floatingStyles}
              aria-label={label}
              {...getFloatingProps()}
            >
              <div className="shiny-sources-popover__title">Sources</div>
              <ul className="shiny-sources-list">
                {sources.map((s) => (
                  <li key={s.url} className="shiny-sources-item">
                    <a
                      className="shiny-sources-item__link"
                      href={s.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <Favicon url={s.url} />
                      <span className="shiny-sources-item__text">
                        {s.domain && (
                          <span className="shiny-sources-item__site">
                            {s.domain}
                          </span>
                        )}
                        <span className="shiny-sources-item__title">
                          {s.title ?? s.domain ?? s.url}
                        </span>
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          </FloatingFocusManager>
        </FloatingPortal>
      )}
    </div>
  )
}

export const SourcesSummary = memo(function SourcesSummary() {
  return <SourcesSummaryView sources={useCitations()} />
})
