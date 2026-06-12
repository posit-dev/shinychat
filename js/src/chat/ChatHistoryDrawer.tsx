import React, { useEffect, useMemo, useRef, useState } from "react"
import type { ConversationMeta } from "../transport/types"

export interface ChatHistoryDrawerProps {
  conversations: ConversationMeta[]
  activeId: string | null
  /** True while a stream is in flight: disables select, + New, and Delete. */
  busy: boolean
  onSelect: (id: string) => void
  onNew: () => void
  onRename: (id: string, title: string) => void
  onDelete: (id: string) => void
}

export function ChatHistoryDrawer({
  conversations,
  activeId,
  busy,
  onSelect,
  onNew,
  onRename,
  onDelete,
}: ChatHistoryDrawerProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [menuFor, setMenuFor] = useState<string | null>(null)
  const [renaming, setRenaming] = useState<string | null>(null)
  const [confirmingDelete, setConfirmingDelete] = useState<string | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        close()
      }
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [open])

  useEffect(() => {
    if (open) searchRef.current?.focus()
  }, [open])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return conversations
    return conversations.filter((c) => c.title.toLowerCase().includes(q))
  }, [conversations, query])

  const groups = useMemo(() => groupByRecency(filtered), [filtered])

  function close() {
    setOpen(false)
    setQuery("")
    setMenuFor(null)
    setRenaming(null)
    setConfirmingDelete(null)
  }

  function handleSelect(id: string) {
    if (busy) return
    onSelect(id)
    close()
  }

  function handleNew() {
    if (busy) return
    onNew()
    close()
  }

  return (
    <>
      <button
        type="button"
        className="shiny-chat-history-trigger"
        aria-label="Conversation history"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
      >
        <HistoryIcon />
      </button>
      {open && (
        <div
          className="shiny-chat-history"
          role="dialog"
          aria-modal="true"
          aria-label="Conversation history"
        >
          <div className="shiny-chat-history-scrim" onClick={close} />
          <div className="shiny-chat-history-drawer">
            <div className="shiny-chat-history-toprow">
              <button
                type="button"
                className="shiny-chat-history-new"
                disabled={busy}
                title={busy ? "Wait for the response to finish" : undefined}
                onClick={handleNew}
              >
                ＋ New
              </button>
              <input
                className="shiny-chat-history-search form-control"
                ref={searchRef}
                placeholder="Search…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search conversations"
              />
            </div>
            <div className="shiny-chat-history-list">
              {filtered.length === 0 && (
                <div className="shiny-chat-history-empty">
                  {query.trim()
                    ? "No conversations found"
                    : "No conversations yet"}
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
                      menuOpen={menuFor === c.id}
                      renaming={renaming === c.id}
                      confirmingDelete={confirmingDelete === c.id}
                      onToggleMenu={() =>
                        setMenuFor(menuFor === c.id ? null : c.id)
                      }
                      onStartRename={() => {
                        setRenaming(c.id)
                        setMenuFor(null)
                      }}
                      onStartDelete={() => {
                        setConfirmingDelete(c.id)
                        setMenuFor(null)
                      }}
                      onCancelEdit={() => {
                        setRenaming(null)
                        setConfirmingDelete(null)
                      }}
                      onRename={(title) => {
                        onRename(c.id, title)
                        setRenaming(null)
                      }}
                      onDelete={() => {
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
        </div>
      )}
    </>
  )
}

interface ConversationItemProps {
  meta: ConversationMeta
  active: boolean
  busy: boolean
  menuOpen: boolean
  renaming: boolean
  confirmingDelete: boolean
  onToggleMenu: () => void
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
  menuOpen,
  renaming,
  confirmingDelete,
  onToggleMenu,
  onStartRename,
  onStartDelete,
  onCancelEdit,
  onRename,
  onDelete,
  onSelect,
}: ConversationItemProps) {
  const [draft, setDraft] = useState(meta.title)

  // Keep draft in sync if title changes externally while not editing
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
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onRename(draft)
            if (e.key === "Escape") onCancelEdit()
          }}
          onBlur={onCancelEdit}
          aria-label="Rename conversation"
        />
      </div>
    )
  }

  return (
    <div
      className={`shiny-chat-history-item${active ? " active" : ""}`}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      aria-disabled={busy ? true : undefined}
      title={busy ? "Wait for the response to finish" : undefined}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          onSelect()
        }
      }}
    >
      <span className="shiny-chat-history-item-title">
        {meta.title}
        <span className="shiny-chat-history-item-time">
          {relativeTime(meta.updated_at)}
        </span>
      </span>
      {confirmingDelete ? (
        <span
          className="shiny-chat-history-confirm"
          onClick={(e) => e.stopPropagation()}
        >
          Delete?
          <button type="button" onClick={onDelete} aria-label="Confirm delete">
            ✓
          </button>
          <button
            type="button"
            onClick={onCancelEdit}
            aria-label="Cancel delete"
          >
            ✕
          </button>
        </span>
      ) : (
        <span
          className="shiny-chat-history-itemmenu"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            aria-label="Conversation actions"
            onClick={onToggleMenu}
          >
            ⋯
          </button>
          {menuOpen && (
            <span className="shiny-chat-history-menu">
              <button type="button" onClick={onStartRename}>
                Rename
              </button>
              <button
                type="button"
                disabled={busy}
                title={busy ? "Wait for the response to finish" : undefined}
                onClick={onStartDelete}
              >
                Delete…
              </button>
            </span>
          )}
        </span>
      )}
    </div>
  )
}

function groupByRecency(
  items: ConversationMeta[],
): Array<[string, ConversationMeta[]]> {
  const startOfToday = new Date()
  startOfToday.setHours(0, 0, 0, 0)

  const today: ConversationMeta[] = []
  const previous: ConversationMeta[] = []

  for (const c of items) {
    if (new Date(c.updated_at) >= startOfToday) {
      today.push(c)
    } else {
      previous.push(c)
    }
  }

  // Two groups for now; expand (Last 7 days / by month) if lists grow long.
  const groups: Array<[string, ConversationMeta[]]> = []
  if (today.length) groups.push(["Today", today])
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

function HistoryIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M2 4h12M2 8h12M2 12h12"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  )
}
