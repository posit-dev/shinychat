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
import type { ChatDrawerState } from "./state"
import { usePrefersReducedMotion } from "./usePrefersReducedMotion"
import {
  getResizeHandleProvider,
  type ResizeHandleElement,
  type ResizeRequestDetail,
} from "../resize-handle"

const MIN_DRAWER_WIDTH = 240
const MIN_CHAT_WIDTH = 360
const MAX_DRAWER_LAYOUT_GAP = 24
const DRAWER_LAYOUT_TRANSITION_DURATION = 180
// Keep both columns adjacent until their established minimums need more room.
// The extra margin avoids switching layouts at the exact mathematical limit.
export const DRAWER_TAKEOVER_WIDTH =
  MIN_DRAWER_WIDTH + MIN_CHAT_WIDTH + MAX_DRAWER_LAYOUT_GAP + 16

function clampWidth(width: number, maxWidth: number): number {
  return Math.round(Math.min(Math.max(width, MIN_DRAWER_WIDTH), maxWidth))
}

function pixelWidth(width: string): number | undefined {
  const match = /^\s*(\d+(?:\.\d+)?)px\s*$/i.exec(width)
  return match ? Number.parseFloat(match[1]!) : undefined
}

function triggerResize(): void {
  window.dispatchEvent(new Event("resize"))
}

function DrawerCloseIcon() {
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

function DrawerContent({
  content,
  htmlDeps,
  source,
  visible,
}: {
  content: string
  htmlDeps: ChatDrawerState["htmlDeps"]
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
    wrapper.className = "shiny-chat-drawer-generation"

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

  return <div ref={hostRef} className="shiny-chat-drawer-content" />
}

export interface ChatDrawerProps {
  drawer: ChatDrawerState
  source?: Element
  panelId?: string
  titleId: string
  takeover: boolean
  closeButtonRef: React.RefObject<HTMLButtonElement | null>
  onClose(): void
  onWidthChange(width: string): void
  onPresentationChange?(present: boolean): void
  onResizeStateChange?(resizing: boolean): void
}

export function ChatDrawer({
  drawer,
  source,
  panelId,
  titleId,
  takeover,
  closeButtonRef,
  onClose,
  onWidthChange,
  onPresentationChange,
  onResizeStateChange,
}: ChatDrawerProps) {
  const panelRef = useRef<HTMLElement>(null)
  const prefersReducedMotion = usePrefersReducedMotion()
  const [present, setPresent] = useState(drawer.visible)
  const [motion, setMotion] = useState(drawer.visible ? "open" : "closed")
  const [resizing, setResizing] = useState(false)
  const wasVisibleRef = useRef(drawer.visible)
  const motionFrameRef = useRef<number | null>(null)
  const motionTimerRef = useRef<number | null>(null)
  const layoutReadyTimerRef = useRef<number | null>(null)
  const [layoutReady, setLayoutReady] = useState(drawer.visible)
  const [width, setWidth] = useState(() => drawer.width || "400px")
  const [maximumWidth, setMaximumWidth] = useState(840)
  const [renderedWidth, setRenderedWidth] = useState(
    () => pixelWidth(drawer.width || "400px") ?? 400,
  )
  const [resizeHandleProvider] = useState(() =>
    getResizeHandleProvider(customElements, { boundaryActivation: true }),
  )
  const resizeHandleRef = useRef<ResizeHandleElement>(null)
  const pendingWidthRef = useRef<number | null>(null)

  useLayoutEffect(() => {
    const wasVisible = wasVisibleRef.current
    if (motionFrameRef.current !== null) {
      window.cancelAnimationFrame(motionFrameRef.current)
      motionFrameRef.current = null
    }
    if (motionTimerRef.current !== null) {
      window.clearTimeout(motionTimerRef.current)
      motionTimerRef.current = null
    }
    if (
      layoutReadyTimerRef.current !== null &&
      (!drawer.visible || !wasVisible)
    ) {
      window.clearTimeout(layoutReadyTimerRef.current)
      layoutReadyTimerRef.current = null
    }

    wasVisibleRef.current = drawer.visible
    if (drawer.visible) {
      setPresent(true)
      if (!wasVisible) {
        setMotion("opening")
        if (prefersReducedMotion || takeover) {
          setLayoutReady(true)
        } else {
          setLayoutReady(false)
          layoutReadyTimerRef.current = window.setTimeout(() => {
            layoutReadyTimerRef.current = null
            setLayoutReady(true)
          }, DRAWER_LAYOUT_TRANSITION_DURATION)
        }
        motionFrameRef.current = window.requestAnimationFrame(() => {
          motionFrameRef.current = null
          setMotion("open")
        })
      } else {
        setMotion("open")
      }
      return
    }

    pendingWidthRef.current = null
    setResizing(false)
    setLayoutReady(false)
    if (!wasVisible) {
      setPresent(false)
      setMotion("closed")
      return
    }

    setMotion("closing")
    if (prefersReducedMotion || takeover) {
      setPresent(false)
      setMotion("closed")
      return
    }

    motionTimerRef.current = window.setTimeout(() => {
      motionTimerRef.current = null
      setPresent(false)
      setMotion("closed")
    }, DRAWER_LAYOUT_TRANSITION_DURATION)
  }, [drawer.visible, prefersReducedMotion, takeover])

  useEffect(() => {
    onPresentationChange?.(present)
  }, [onPresentationChange, present])

  useEffect(() => {
    onResizeStateChange?.(resizing)
  }, [onResizeStateChange, resizing])

  useEffect(
    () => () => {
      if (motionFrameRef.current !== null) {
        window.cancelAnimationFrame(motionFrameRef.current)
      }
      if (motionTimerRef.current !== null) {
        window.clearTimeout(motionTimerRef.current)
      }
      if (layoutReadyTimerRef.current !== null) {
        window.clearTimeout(layoutReadyTimerRef.current)
      }
    },
    [],
  )

  const maxWidth = useCallback(() => {
    const panel = panelRef.current
    const container = panel?.closest("shiny-chat-container")
    const available = container?.getBoundingClientRect().width ?? 0
    if (available <= 0) return 840
    // Match ChatContainer's layout reservation. The computed gap can be
    // smaller at constrained widths, but the grid still reserves this maximum.
    return Math.max(
      MIN_DRAWER_WIDTH,
      available - MIN_CHAT_WIDTH - MAX_DRAWER_LAYOUT_GAP,
    )
  }, [])

  const measureAndClampWidth = useCallback(() => {
    const panel = panelRef.current
    if (!panel || !drawer.visible) return

    const maximum = maxWidth()
    setMaximumWidth(maximum)
    const layout = panel.closest(".shiny-chat-layout")
    const layoutWidth = layout?.getBoundingClientRect().width ?? 0
    const measured = Math.round(panel.getBoundingClientRect().width)
    const configured = pixelWidth(drawer.width)

    // A child observer can run before ChatContainer applies its takeover
    // state. The panel is full-width in this range, so never persist that
    // temporary measurement as an adjacent drawer width.
    if (takeover || (layoutWidth > 0 && layoutWidth < DRAWER_TAKEOVER_WIDTH)) {
      pendingWidthRef.current = null
      return
    }

    if (measured <= 0) return

    const pending = pendingWidthRef.current
    if (pending !== null) {
      const bounded = clampWidth(pending, maximum)
      pendingWidthRef.current = bounded
      setWidth(`${bounded}px`)
      setRenderedWidth(bounded)

      // The parent state and grid track update independently. Keep this local
      // intent authoritative until both report the requested pixel width.
      if (configured === bounded && measured === bounded) {
        pendingWidthRef.current = null
      } else if (configured !== bounded) {
        onWidthChange(`${bounded}px`)
      }
      return
    }

    if (configured === undefined) {
      if (!layoutReady) return
      const bounded = clampWidth(measured, maximum)
      setRenderedWidth(bounded)
      if (bounded !== measured) {
        setWidth(`${bounded}px`)
        onWidthChange(`${bounded}px`)
      }
      return
    }

    // A ResizeObserver can run before the grid applies a just-requested pixel
    // width. Trust that configured value instead of restoring the stale,
    // pre-resize measurement.
    const bounded = clampWidth(configured, maximum)
    setWidth(`${bounded}px`)
    setRenderedWidth(bounded)
    if (
      bounded !== measured ||
      (configured !== undefined && bounded !== configured)
    ) {
      onWidthChange(`${bounded}px`)
    }
  }, [
    drawer.visible,
    drawer.width,
    layoutReady,
    takeover,
    maxWidth,
    onWidthChange,
  ])

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
      pendingWidthRef.current = bounded
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
      min: MIN_DRAWER_WIDTH,
      max: maximumWidth,
      panelSide: "inline-start",
      disabled: !drawer.resizable || takeover || !drawer.visible,
      label: "Resize drawer panel",
      boundaryActivation: true,
    })
    const onResizeRequest = (event: Event) => {
      setBoundedWidth((event as CustomEvent<ResizeRequestDetail>).detail.value)
    }
    const onResizeStart = () => setResizing(true)
    const onResizeEnd = () => setResizing(false)
    handle.addEventListener("resize-request", onResizeRequest)
    handle.addEventListener("resize-start", onResizeStart)
    handle.addEventListener("resize-end", onResizeEnd)
    return () => {
      handle.removeEventListener("resize-request", onResizeRequest)
      handle.removeEventListener("resize-start", onResizeStart)
      handle.removeEventListener("resize-end", onResizeEnd)
    }
  }, [
    drawer.resizable,
    drawer.visible,
    currentWidth,
    maximumWidth,
    setBoundedWidth,
    takeover,
  ])

  const title = drawer.title || "Drawer"
  const style = {
    "--_drawer-width": width,
  } as React.CSSProperties

  return (
    <aside
      ref={panelRef}
      id={panelId}
      className="shiny-chat-drawer"
      aria-labelledby={titleId}
      aria-hidden={!drawer.visible || undefined}
      hidden={!present}
      data-takeover={takeover ? "" : undefined}
      data-motion={motion}
      data-drawer-resizing={resizing ? "" : undefined}
      style={style}
    >
      {drawer.resizable &&
        !takeover &&
        createElement(resizeHandleProvider.tagName, {
          ref: resizeHandleRef,
          className: "shiny-chat-drawer-resizer",
          "data-shiny-chat-resize-handle-provider": resizeHandleProvider.name,
        })}
      <div className="shiny-chat-drawer-header">
        <h2 id={titleId}>{title}</h2>
        <button
          ref={closeButtonRef}
          type="button"
          className="shiny-chat-drawer-close"
          aria-label="Close drawer"
          onClick={onClose}
        >
          <DrawerCloseIcon />
        </button>
      </div>
      <DrawerContent
        content={drawer.content}
        htmlDeps={drawer.htmlDeps}
        source={source}
        visible={drawer.visible}
      />
    </aside>
  )
}
