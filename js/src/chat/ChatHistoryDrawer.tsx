import React, { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  FloatingFocusManager,
  FloatingPortal,
  autoUpdate,
  flip,
  offset,
  shift,
  useClick,
  useDismiss,
  useFloating,
  useInteractions,
} from "@floating-ui/react"
import type { ConversationMeta } from "../transport/types"
import { portalTheme } from "./portalTheme"
import { usePrefersReducedMotion } from "./usePrefersReducedMotion"

// Matches the 0.2s CSS animation in _history.scss, plus a margin of safety.
const DRAWER_CLOSE_FALLBACK_MS = 300

const HISTORY_PORTAL_VARIABLES = [
  "--shiny-chat-history-accent",
  "--shiny-chat-history-bg",
  "--shiny-chat-history-border-color",
  "--shiny-chat-history-item-hover-bg",
  "--shiny-chat-history-item-active-bg",
  "--_history-accent",
  "--_history-bg",
  "--_history-border-color",
  "--_history-muted",
  "--_history-fg",
  "--_history-danger",
  "--_history-item-hover-bg",
  "--_history-item-active-bg",
] as const

const HistoryMenuPortalContext = React.createContext<HTMLElement | null>(null)

export interface ChatHistoryDrawerProps {
  isOpen: boolean
  onClose: () => void
  triggerRef: React.RefObject<HTMLButtonElement | null>
  children: React.ReactNode
}

export interface ChatHistoryContentProps {
  conversations: readonly ConversationMeta[]
  activeId: string | null
  /** True while a stream is in flight: disables unsafe conversation actions. */
  busy: boolean
  /** False while the chat's transport is temporarily unavailable. */
  connected?: boolean
  onSelect: (id: string) => void
  onNew: () => void
  onRename: (id: string, title: string) => void
  onDelete: (id: string) => void
  onActionComplete?: () => void
}

export function ChatHistoryDrawer({
  isOpen,
  onClose,
  triggerRef,
  children,
}: ChatHistoryDrawerProps) {
  // visible stays true through the close animation, unlike isOpen
  const [visible, setVisible] = useState(isOpen)
  const [closing, setClosing] = useState(false)
  // Ref mirrors visible so the isOpen effect can read it without being in deps.
  const visibleRef = useRef(isOpen)
  visibleRef.current = visible
  const reducedMotion = usePrefersReducedMotion()
  const drawerRef = useRef<HTMLDivElement>(null)
  const [menuPortalRoot, setMenuPortalRoot] = useState<HTMLDivElement | null>(
    null,
  )

  const handleClose = useCallback(() => {
    onClose()
  }, [onClose])

  const finishClosing = useCallback(() => {
    setVisible(false)
    setClosing(false)
    triggerRef.current?.focus({ preventScroll: true })
  }, [triggerRef])

  useEffect(() => {
    if (isOpen) {
      setVisible(true)
      setClosing(false)
    } else if (visibleRef.current) {
      setClosing(true)
    }
  }, [isOpen])

  // Close is normally driven by the drawer's slide-out CSS animation
  // finishing (see handleDrawerAnimationEnd), but `animationend` never fires
  // when prefers-reduced-motion (or some other mechanism) disables the
  // animation — so don't rely on it alone. Finish immediately for reduced
  // motion, and fall back to a timer otherwise as a safety net.
  useEffect(() => {
    if (!closing) return
    if (reducedMotion) {
      finishClosing()
      return
    }
    const timer = setTimeout(finishClosing, DRAWER_CLOSE_FALLBACK_MS)
    return () => clearTimeout(timer)
  }, [closing, reducedMotion, finishClosing])

  useEffect(() => {
    if (!visible || closing) return
    const drawer = drawerRef.current
    if (!drawer) return

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        // Scope Escape to whatever sub-state is active before closing the
        // whole drawer. Inline history controls stop propagation when they
        // need to consume Escape themselves.
        handleClose()
        return
      }
      if (e.key === "Tab") {
        const focusable = drawer.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"]):not([data-floating-ui-focus-guard])',
        )
        if (focusable.length === 0) return
        const first = focusable[0]!
        const last = focusable[focusable.length - 1]!
        // Initial focus is on the dialog container (tabIndex -1, not in
        // `focusable`); treat it like "before first" so Shift+Tab wraps to the
        // end instead of escaping backward to the page.
        const onContainer = document.activeElement === drawer
        if (e.shiftKey && (document.activeElement === first || onContainer)) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [visible, closing, handleClose])

  // Move focus into the drawer on open (so Escape / focus-trap work and screen
  // readers announce the dialog) without landing on the search field — search
  // isn't what most people want first. Tab then advances into the controls.
  useEffect(() => {
    if (visible && !closing) drawerRef.current?.focus({ preventScroll: true })
  }, [visible, closing])

  function handleDrawerAnimationEnd(e: React.AnimationEvent<HTMLDivElement>) {
    // onAnimationEnd bubbles from descendants; only react to the drawer's
    // own close animation, not a child's.
    if (e.target !== e.currentTarget) return
    if (!closing) return
    finishClosing()
  }

  if (!visible) return null

  return (
    <div
      ref={drawerRef}
      className="shiny-chat-history"
      data-closing={closing || undefined}
      role="dialog"
      aria-modal="true"
      aria-label="Conversation history"
      tabIndex={-1}
    >
      <HistoryMenuPortalContext.Provider value={menuPortalRoot}>
        <div className="shiny-chat-history-scrim" onClick={handleClose} />
        <div
          className="shiny-chat-history-drawer"
          onAnimationEnd={handleDrawerAnimationEnd}
        >
          <div className="shiny-chat-history-header">
            <h2 className="shiny-chat-history-title">History</h2>
            <button
              type="button"
              className="shiny-chat-history-close"
              aria-label="Close history"
              onClick={handleClose}
            >
              <CloseIcon />
            </button>
          </div>
          {children}
        </div>
        <div ref={setMenuPortalRoot} />
      </HistoryMenuPortalContext.Provider>
    </div>
  )
}

export function ChatHistoryContent({
  conversations,
  activeId,
  busy,
  connected = true,
  onSelect,
  onNew,
  onRename,
  onDelete,
  onActionComplete,
}: ChatHistoryContentProps) {
  const [query, setQuery] = useState("")
  const [menuFor, setMenuFor] = useState<string | null>(null)
  const [renaming, setRenaming] = useState<string | null>(null)
  const [confirmingDelete, setConfirmingDelete] = useState<string | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const dialogPortalRoot = React.useContext(HistoryMenuPortalContext)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return conversations
    return conversations.filter((c) => c.title.toLowerCase().includes(q))
  }, [conversations, query])

  const groups = useMemo(() => groupByRecency(filtered), [filtered])

  function handleSelect(id: string) {
    if (busy || !connected) return
    onSelect(id)
    onActionComplete?.()
  }

  function handleNew() {
    if (busy || !connected) return
    onNew()
    onActionComplete?.()
  }

  const handleEscape = useCallback((): boolean => {
    if (confirmingDelete) {
      setConfirmingDelete(null)
      return true
    }
    if (menuFor) {
      setMenuFor(null)
      return true
    }
    return false
  }, [confirmingDelete, menuFor])

  useEffect(() => {
    if (!menuFor && !confirmingDelete) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return
      event.stopPropagation()
      handleEscape()
    }
    window.addEventListener("keydown", onKeyDown, true)
    return () => window.removeEventListener("keydown", onKeyDown, true)
  }, [menuFor, confirmingDelete, handleEscape])

  return (
    <div
      ref={contentRef}
      onKeyDown={(event) => {
        if (event.key === "Escape" && handleEscape()) {
          event.stopPropagation()
        }
      }}
    >
      <div className="shiny-chat-history-toprow">
        <button
          type="button"
          className="shiny-chat-history-new"
          disabled={busy || !connected}
          title={
            busy
              ? "Wait for the response to finish"
              : !connected
                ? "History is unavailable while chat reconnects"
                : undefined
          }
          aria-label="New conversation"
          onClick={handleNew}
        >
          <NewChatIcon />
          New
        </button>
        <span className="shiny-chat-history-search-wrap">
          <span className="shiny-chat-history-search-icon">
            <SearchIcon />
          </span>
          <input
            className="shiny-chat-history-search form-control"
            ref={searchRef}
            placeholder="Search…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search conversations"
          />
        </span>
      </div>
      <div className="shiny-chat-history-list">
        {filtered.length === 0 && (
          <div className="shiny-chat-history-empty">
            {query.trim() ? "No conversations found" : "No conversations yet"}
          </div>
        )}
        {groups.map(([label, items]) => (
          <React.Fragment key={label}>
            <div className="shiny-chat-history-section">{label}</div>
            {items.map((c) => (
              <ConversationItem
                key={c.id}
                meta={c}
                active={c.id === activeId}
                busy={busy}
                connected={connected}
                portalRoot={dialogPortalRoot ?? contentRef.current}
                menuOpen={menuFor === c.id}
                renaming={renaming === c.id}
                confirmingDelete={confirmingDelete === c.id}
                onMenuOpenChange={(open) => setMenuFor(open ? c.id : null)}
                onStartRename={() => {
                  if (busy || !connected) return
                  setRenaming(c.id)
                  setMenuFor(null)
                }}
                onStartDelete={() => {
                  if (busy || !connected) return
                  setConfirmingDelete(c.id)
                  setMenuFor(null)
                }}
                onCancelEdit={() => {
                  setRenaming(null)
                  setConfirmingDelete(null)
                }}
                onRename={(title) => {
                  if (busy || !connected) return
                  onRename(c.id, title)
                  setRenaming(null)
                }}
                onDelete={() => {
                  if (busy || !connected) return
                  onDelete(c.id)
                  setConfirmingDelete(null)
                }}
                onSelect={() => handleSelect(c.id)}
              />
            ))}
          </React.Fragment>
        ))}
      </div>
    </div>
  )
}

interface ConversationItemProps {
  meta: ConversationMeta
  active: boolean
  busy: boolean
  connected: boolean
  portalRoot: HTMLElement | null
  menuOpen: boolean
  renaming: boolean
  confirmingDelete: boolean
  onMenuOpenChange: (open: boolean) => void
  onStartRename: () => void
  onStartDelete: () => void
  onCancelEdit: () => void
  onRename: (title: string) => void
  onDelete: () => void
  onSelect: () => void
}

function ConversationItem({
  meta,
  active,
  busy,
  connected,
  portalRoot,
  menuOpen,
  renaming,
  confirmingDelete,
  onMenuOpenChange,
  onStartRename,
  onStartDelete,
  onCancelEdit,
  onRename,
  onDelete,
  onSelect,
}: ConversationItemProps) {
  const [draft, setDraft] = useState(meta.title)
  const { refs, floatingStyles, context } = useFloating({
    open: menuOpen,
    onOpenChange: onMenuOpenChange,
    strategy: "fixed",
    placement: "bottom-end",
    middleware: [offset(4), flip(), shift({ padding: 8, crossAxis: true })],
    whileElementsMounted: autoUpdate,
  })
  const click = useClick(context)
  const dismiss = useDismiss(context, { outsidePressEvent: "mousedown" })
  const { getReferenceProps, getFloatingProps } = useInteractions([
    click,
    dismiss,
  ])
  const portal = menuOpen
    ? portalTheme(refs.domReference.current, HISTORY_PORTAL_VARIABLES)
    : null

  // Resync if meta.title changes from outside this component (e.g. rename from another tab)
  useEffect(() => {
    if (!renaming) {
      setDraft(meta.title)
    }
  }, [meta.title, renaming])

  if (renaming) {
    return (
      <div className="shiny-chat-history-item">
        <input
          className="shiny-chat-history-rename-input form-control form-control-sm"
          autoFocus
          disabled={busy || !connected}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              if (!draft.trim()) return
              onRename(draft)
              return
            }
            if (e.key === "Escape") {
              // Cancel the rename in place; don't let this bubble to the
              // drawer's document-level Escape handler and close the drawer.
              e.stopPropagation()
              onCancelEdit()
            }
          }}
          onBlur={onCancelEdit}
          aria-label="Rename conversation"
        />
      </div>
    )
  }

  return (
    <div className={`shiny-chat-history-item${active ? " active" : ""}`}>
      <button
        type="button"
        className="shiny-chat-history-item-select"
        disabled={busy || !connected}
        title={
          busy
            ? "Wait for the response to finish"
            : !connected
              ? "History is unavailable while chat reconnects"
              : undefined
        }
        onClick={onSelect}
      >
        <span className="shiny-chat-history-item-title">{meta.title}</span>
        <span className="shiny-chat-history-item-time">
          {relativeTime(meta.created_at)}
        </span>
      </button>
      {confirmingDelete ? (
        <span className="shiny-chat-history-confirm">
          Delete?
          <button
            type="button"
            className="shiny-chat-history-confirm-yes"
            disabled={busy || !connected}
            onClick={onDelete}
            aria-label="Confirm delete"
          >
            <CheckIcon />
          </button>
          <button
            type="button"
            className="shiny-chat-history-confirm-no"
            onClick={onCancelEdit}
            aria-label="Cancel delete"
          >
            <CloseIcon />
          </button>
        </span>
      ) : (
        <span
          className="shiny-chat-history-itemmenu"
          data-menu-id={meta.id}
          data-menu-open={menuOpen || undefined}
        >
          <button
            ref={refs.setReference}
            type="button"
            aria-label="Conversation actions"
            disabled={busy || !connected}
            title={
              !connected
                ? "History is unavailable while chat reconnects"
                : undefined
            }
            {...getReferenceProps()}
          >
            <MoreIcon />
          </button>
          {menuOpen && (
            <FloatingPortal root={portalRoot}>
              <FloatingFocusManager
                context={context}
                modal={false}
                initialFocus={-1}
                returnFocus
              >
                <div
                  ref={refs.setFloating}
                  className="shiny-chat-history-menu"
                  style={{ ...portal?.style, ...floatingStyles }}
                  data-bs-theme={portal?.theme}
                  {...getFloatingProps()}
                >
                  <button
                    type="button"
                    disabled={busy || !connected}
                    title={
                      !connected
                        ? "History is unavailable while chat reconnects"
                        : undefined
                    }
                    onClick={onStartRename}
                  >
                    <PencilIcon />
                    Rename
                  </button>
                  <button
                    type="button"
                    className="shiny-chat-history-menu-danger"
                    disabled={busy || !connected}
                    title={
                      busy
                        ? "Wait for the response to finish"
                        : !connected
                          ? "History is unavailable while chat reconnects"
                          : undefined
                    }
                    onClick={onStartDelete}
                  >
                    <TrashIcon />
                    Delete
                  </button>
                </div>
              </FloatingFocusManager>
            </FloatingPortal>
          )}
        </span>
      )}
    </div>
  )
}

function groupByRecency(
  items: readonly ConversationMeta[],
): Array<[string, readonly ConversationMeta[]]> {
  const startOfToday = new Date()
  startOfToday.setHours(0, 0, 0, 0)

  const sevenDaysAgo = new Date(startOfToday)
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7)

  const today: ConversationMeta[] = []
  const lastWeek: ConversationMeta[] = []
  const previous: ConversationMeta[] = []

  for (const c of items) {
    const created = new Date(c.created_at)
    if (created >= startOfToday) {
      today.push(c)
    } else if (created >= sevenDaysAgo) {
      lastWeek.push(c)
    } else {
      previous.push(c)
    }
  }

  const groups: Array<[string, ConversationMeta[]]> = []
  if (today.length) groups.push(["Today", today])
  if (lastWeek.length) groups.push(["Last 7 days", lastWeek])
  if (previous.length) groups.push(["Previous", previous])
  return groups
}

function relativeTime(iso: string): string {
  const then = new Date(iso)
  const startOfToday = new Date()
  startOfToday.setHours(0, 0, 0, 0)

  if (then >= startOfToday) {
    return then.toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    })
  }
  return then.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  })
}

// Clock-rewind glyph: reads as "past conversations", unlike the hamburger it
// replaced (which read as a navigation menu).
export function HistoryIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M2.5 3v3h3"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M2.75 6A5.5 5.5 0 1 1 3 9.6"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M8 5v3.2l2.2 1.3"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

// Compose / new-conversation glyph (pencil in a square).
function NewChatIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M8 2.5H3.5A1.5 1.5 0 0 0 2 4v8.5A1.5 1.5 0 0 0 3.5 14H12a1.5 1.5 0 0 0 1.5-1.5V8"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M11.7 2.3a1.2 1.2 0 0 1 1.7 1.7L8 9.4l-2.3.6.6-2.3 5.4-5.4z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function SearchIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="m10.5 10.5 3 3"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="m4 4 8 8M12 4l-8 8"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="m3.5 8.5 3 3 6-7"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function MoreIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="currentColor"
      aria-hidden="true"
    >
      <circle cx="3.5" cy="8" r="1.35" />
      <circle cx="8" cy="8" r="1.35" />
      <circle cx="12.5" cy="8" r="1.35" />
    </svg>
  )
}

function PencilIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M11.7 2.3a1.2 1.2 0 0 1 1.7 1.7l-8 8-2.8.9.9-2.8 8.2-8.2z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="m10.5 3.5 2 2"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M3 4.5h10M6.5 4.5V3a.8.8 0 0 1 .8-.8h1.4a.8.8 0 0 1 .8.8v1.5M4.5 4.5l.5 8a1 1 0 0 0 1 .95h4a1 1 0 0 0 1-.95l.5-8M6.75 7v3.75M9.25 7v3.75"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
