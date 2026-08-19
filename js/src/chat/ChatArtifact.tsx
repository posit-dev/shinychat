import {
  useCallback,
  useContext,
  createElement,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react"
import { ShinyLifecycleContext } from "./context"
import type { ChatArtifactState } from "./state"
import {
  getResizeHandleProvider,
  type ResizeHandleElement,
  type ResizeRequestDetail,
} from "../resize-handle"

const MIN_ARTIFACT_WIDTH = 240
const MIN_CHAT_WIDTH = 360
export const ARTIFACT_TAKEOVER_WIDTH = 1120

function clampWidth(width: number, maxWidth: number): number {
  return Math.round(Math.min(Math.max(width, MIN_ARTIFACT_WIDTH), maxWidth))
}

function pixelWidth(width: string): number | undefined {
  const match = /^\s*(\d+(?:\.\d+)?)px\s*$/i.exec(width)
  return match ? Number.parseFloat(match[1]!) : undefined
}

function triggerResize(): void {
  window.dispatchEvent(new Event("resize"))
}

function ArtifactCloseIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m3 3 10 10M13 3 3 13" />
    </svg>
  )
}

function ArtifactContent({
  content,
  htmlDeps,
  source,
  visible,
}: {
  content: string
  htmlDeps: ChatArtifactState["htmlDeps"]
  source?: Element
  visible: boolean
}) {
  const hostRef = useRef<HTMLDivElement>(null)
  const shiny = useContext(ShinyLifecycleContext)
  const initialSourceRef = useRef(source)
  const initialContentRef = useRef(content)
  const adoptedInitialSourceRef = useRef(false)
  const generationRef = useRef(0)
  const currentWrapperRef = useRef<HTMLDivElement | null>(null)
  const shinyRef = useRef(shiny)
  shinyRef.current = shiny
  const visibleRef = useRef(visible)
  visibleRef.current = visible

  useLayoutEffect(() => {
    const host = hostRef.current
    if (!host) return

    const generation = generationRef.current + 1
    generationRef.current = generation
    let cancelled = false
    const isCurrent = () => generationRef.current === generation
    const wrapper = document.createElement("div")
    wrapper.className = "shiny-chat-artifact-generation"

    const replaceContent = async () => {
      // A server action makes the artifact visible before its dependencies
      // resolve. Remove the old dynamic subtree in this layout effect so it
      // cannot paint during that wait.
      const previousWrapper = currentWrapperRef.current
      if (previousWrapper) {
        shiny?.unbindAll(previousWrapper)
        previousWrapper.remove()
      }
      currentWrapperRef.current = wrapper
      host.replaceChildren(wrapper)

      if (htmlDeps.length > 0) {
        await shiny?.renderDependencies(htmlDeps)
      }
      if (cancelled || !isCurrent()) return

      const initialSource = initialSourceRef.current
      if (
        !adoptedInitialSourceRef.current &&
        initialSource &&
        content === initialContentRef.current
      ) {
        while (initialSource.firstChild) {
          wrapper.appendChild(initialSource.firstChild)
        }
        adoptedInitialSourceRef.current = true
      } else {
        wrapper.innerHTML = content
      }

      if (cancelled || !isCurrent() || !wrapper.hasChildNodes()) return
      // Treat an in-flight bind as bound for cleanup purposes. A component
      // unmount can happen while Shiny's bind promise is still pending.
      await shiny?.bindAll(wrapper)
      if (!isCurrent()) {
        shiny?.unbindAll(wrapper)
        wrapper.remove()
        return
      }
      if (cancelled) {
        shiny?.unbindAll(wrapper)
        wrapper.remove()
        if (currentWrapperRef.current === wrapper) {
          currentWrapperRef.current = null
        }
        return
      }
      if (visibleRef.current) triggerResize()
    }

    void replaceContent()
    return () => {
      cancelled = true
    }
  }, [content, htmlDeps, shiny])

  useEffect(() => {
    const host = hostRef.current
    return () => {
      generationRef.current += 1
      const wrapper = currentWrapperRef.current
      if (!host || !wrapper) return
      currentWrapperRef.current = null
      shinyRef.current?.unbindAll(wrapper)
      wrapper.remove()
    }
  }, [])

  useEffect(() => {
    if (visible) triggerResize()
  }, [visible])

  return <div ref={hostRef} className="shiny-chat-artifact-content" />
}

export interface ChatArtifactProps {
  artifact: ChatArtifactState
  source?: Element
  panelId?: string
  titleId: string
  takeover: boolean
  closeButtonRef: React.RefObject<HTMLButtonElement | null>
  onClose(): void
  onWidthChange(width: string): void
}

export function ChatArtifact({
  artifact,
  source,
  panelId,
  titleId,
  takeover,
  closeButtonRef,
  onClose,
  onWidthChange,
}: ChatArtifactProps) {
  const panelRef = useRef<HTMLElement>(null)
  const [width, setWidth] = useState(() => artifact.width || "400px")
  const [maximumWidth, setMaximumWidth] = useState(840)
  const [renderedWidth, setRenderedWidth] = useState(
    () => pixelWidth(artifact.width || "400px") ?? 400,
  )
  const resizeHandleRef = useRef<ResizeHandleElement>(null)

  const maxWidth = useCallback(() => {
    const panel = panelRef.current
    const container = panel?.closest("shiny-chat-container")
    const available = container?.getBoundingClientRect().width ?? 0
    if (available <= 0) return 840
    const layout = panel?.closest(".shiny-chat-layout") as HTMLElement | null
    const computedGap = layout
      ? Number.parseFloat(window.getComputedStyle(layout).columnGap)
      : NaN
    const gap = Number.isFinite(computedGap)
      ? computedGap
      : Number.parseFloat(layout?.style.columnGap ?? "") || 0
    return Math.max(MIN_ARTIFACT_WIDTH, available - MIN_CHAT_WIDTH - gap)
  }, [])

  const measureAndClampWidth = useCallback(() => {
    const panel = panelRef.current
    if (!panel || !artifact.visible) return

    const maximum = maxWidth()
    setMaximumWidth(maximum)
    const layout = panel.closest(".shiny-chat-layout")
    const layoutWidth = layout?.getBoundingClientRect().width ?? 0
    const measured = Math.round(panel.getBoundingClientRect().width)
    const configured = pixelWidth(artifact.width)
    if (configured === undefined) {
      if (measured > 0) setRenderedWidth(measured)
      setWidth((current) =>
        current === artifact.width ? current : artifact.width,
      )
      return
    }

    // A child observer can run before ChatContainer applies its takeover
    // state. The panel is full-width in this range, so never persist that
    // temporary measurement as a desktop artifact width.
    if (
      takeover ||
      (layoutWidth > 0 && layoutWidth < ARTIFACT_TAKEOVER_WIDTH)
    ) {
      return
    }

    if (measured <= 0) return

    const bounded = clampWidth(Math.max(measured, configured ?? 0), maximum)
    setWidth(`${bounded}px`)
    setRenderedWidth(bounded)
    if (
      bounded !== measured ||
      (configured !== undefined && bounded !== configured)
    ) {
      onWidthChange(`${bounded}px`)
    }
  }, [artifact.visible, artifact.width, takeover, maxWidth, onWidthChange])

  useLayoutEffect(() => {
    measureAndClampWidth()

    const panel = panelRef.current
    const container = panel?.closest("shiny-chat-container")
    if (!container || typeof ResizeObserver === "undefined") return

    const observer = new ResizeObserver(measureAndClampWidth)
    observer.observe(container)
    const layout = panel?.closest(".shiny-chat-layout")
    if (layout && layout !== container) observer.observe(layout)
    return () => observer.disconnect()
  }, [measureAndClampWidth])

  const currentWidth = pixelWidth(width) ?? renderedWidth

  const setBoundedWidth = useCallback(
    (next: number) => {
      const bounded = clampWidth(next, maxWidth())
      setWidth(`${bounded}px`)
      setRenderedWidth(bounded)
      onWidthChange(`${bounded}px`)
    },
    [maxWidth, onWidthChange],
  )

  useLayoutEffect(() => {
    const handle = resizeHandleRef.current
    if (!handle) return

    handle.configure({
      value: currentWidth,
      min: MIN_ARTIFACT_WIDTH,
      max: maximumWidth,
      panelSide: "inline-start",
      disabled: !artifact.resizable || takeover || !artifact.visible,
      label: "Resize artifact panel",
    })
    const onResizeRequest = (event: Event) => {
      setBoundedWidth((event as CustomEvent<ResizeRequestDetail>).detail.value)
    }
    handle.addEventListener("resize-request", onResizeRequest)
    return () => handle.removeEventListener("resize-request", onResizeRequest)
  }, [
    artifact.resizable,
    artifact.visible,
    currentWidth,
    maximumWidth,
    setBoundedWidth,
    takeover,
  ])

  const title = artifact.title || "Artifact"
  const resizeHandleProvider = getResizeHandleProvider()
  const style = {
    "--shiny-chat-artifact-width": width,
  } as React.CSSProperties

  return (
    <aside
      ref={panelRef}
      id={panelId}
      className="shiny-chat-artifact"
      aria-labelledby={titleId}
      hidden={!artifact.visible}
      data-takeover={takeover ? "" : undefined}
      style={style}
    >
      {artifact.resizable &&
        !takeover &&
        createElement(resizeHandleProvider.tagName, {
          ref: resizeHandleRef,
          className: "shiny-chat-artifact-resizer",
          "data-shiny-chat-resize-handle-provider": resizeHandleProvider.name,
        })}
      <div className="shiny-chat-artifact-header">
        <h2 id={titleId}>{title}</h2>
        <button
          ref={closeButtonRef}
          type="button"
          className="shiny-chat-artifact-close"
          aria-label="Close artifact"
          onClick={onClose}
        >
          <ArtifactCloseIcon />
        </button>
      </div>
      <ArtifactContent
        content={artifact.content}
        htmlDeps={artifact.htmlDeps}
        source={source}
        visible={artifact.visible}
      />
    </aside>
  )
}
