import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent, act, within } from "@testing-library/react"
import React from "react"
import type { ConversationMeta } from "../../src/transport/types"
import {
  ChatHistoryDrawer,
  type ChatHistoryDrawerProps,
  HistoryIcon,
} from "../../src/chat/ChatHistoryDrawer"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** ISO timestamp for today at a given hour */
function todayAt(hour: number): string {
  const d = new Date()
  d.setHours(hour, 0, 0, 0)
  return d.toISOString()
}

/** ISO timestamp for N days ago */
function daysAgo(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() - n)
  d.setHours(10, 0, 0, 0)
  return d.toISOString()
}

function makeConvo(
  overrides: Partial<ConversationMeta> & { id: string },
): ConversationMeta {
  return {
    title: "Untitled",
    created_at: overrides.updated_at ?? todayAt(9),
    updated_at: todayAt(9),
    ...overrides,
  }
}

const DEFAULT_CONVOS: ConversationMeta[] = [
  makeConvo({ id: "a", title: "Today's chat", updated_at: todayAt(14) }),
  makeConvo({ id: "b", title: "Yesterday's chat", updated_at: daysAgo(1) }),
  makeConvo({ id: "c", title: "Old chat", updated_at: daysAgo(10) }),
]

// Mimics how ChatContainer wires up the trigger + drawer.
type WrapperProps = Omit<
  ChatHistoryDrawerProps,
  "isOpen" | "onClose" | "triggerRef"
> & { startOpen?: boolean }

function DrawerWrapper(props: WrapperProps) {
  const { startOpen = false, ...rest } = props
  const [isOpen, setIsOpen] = React.useState(startOpen)
  const triggerRef = React.useRef<HTMLButtonElement>(null)
  return (
    <>
      <button
        type="button"
        ref={triggerRef}
        aria-label="Conversation history"
        aria-expanded={isOpen}
        onClick={() => setIsOpen((v) => !v)}
      >
        <HistoryIcon />
      </button>
      {/* Conditional render skips the CSS close-animation in jsdom so tests
          don't need to fire animationEnd manually. Production uses isOpen prop
          to play the slide-out animation before unmounting. */}
      {isOpen && (
        <ChatHistoryDrawer
          {...rest}
          isOpen={true}
          onClose={() => setIsOpen(false)}
          triggerRef={triggerRef}
        />
      )}
    </>
  )
}

function renderDrawer(props: Partial<WrapperProps> = {}) {
  const onSelect = vi.fn()
  const onNew = vi.fn()
  const onRename = vi.fn()
  const onDelete = vi.fn()

  const result = render(
    <DrawerWrapper
      conversations={props.conversations ?? DEFAULT_CONVOS}
      activeId={props.activeId ?? null}
      busy={props.busy ?? false}
      startOpen={props.startOpen}
      onSelect={props.onSelect ?? onSelect}
      onNew={props.onNew ?? onNew}
      onRename={props.onRename ?? onRename}
      onDelete={props.onDelete ?? onDelete}
    />,
  )

  return { ...result, onSelect, onNew, onRename, onDelete }
}

function openDrawer() {
  const trigger = screen.getByRole("button", { name: /conversation history/i })
  fireEvent.click(trigger)
  return screen.getByRole("dialog")
}

function openMenuFor(title: string): HTMLElement {
  const titleEl = screen.getByText(title)
  const row = titleEl.closest(".shiny-chat-history-item") as HTMLElement
  const menuWrapper = row.querySelector(
    ".shiny-chat-history-itemmenu",
  ) as HTMLElement
  const menuBtn = within(menuWrapper).getByRole("button", {
    name: /conversation actions/i,
  })
  fireEvent.click(menuBtn)
  return menuWrapper
}

// ---------------------------------------------------------------------------
// Trigger button
// ---------------------------------------------------------------------------

describe("trigger button", () => {
  it("renders the trigger button", () => {
    renderDrawer()
    expect(
      screen.getByRole("button", { name: /conversation history/i }),
    ).toBeTruthy()
  })

  it("trigger has aria-expanded=false when closed", () => {
    renderDrawer()
    const btn = screen.getByRole("button", { name: /conversation history/i })
    expect(btn.getAttribute("aria-expanded")).toBe("false")
  })

  it("trigger has aria-expanded=true when open", () => {
    renderDrawer()
    const btn = screen.getByRole("button", { name: /conversation history/i })
    fireEvent.click(btn)
    expect(btn.getAttribute("aria-expanded")).toBe("true")
  })

  it("drawer is not shown before trigger click", () => {
    renderDrawer()
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("drawer opens on trigger click", () => {
    renderDrawer()
    openDrawer()
    expect(screen.getByRole("dialog")).toBeTruthy()
  })

  it("drawer closes on second trigger click", () => {
    renderDrawer()
    const btn = screen.getByRole("button", { name: /conversation history/i })
    fireEvent.click(btn)
    fireEvent.click(btn)
    expect(screen.queryByRole("dialog")).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Drawer structure
// ---------------------------------------------------------------------------

describe("drawer structure", () => {
  it("drawer has role=dialog with aria-label", () => {
    renderDrawer()
    openDrawer()
    const dialog = screen.getByRole("dialog")
    expect(dialog.getAttribute("aria-label")).toBeTruthy()
  })

  it("renders + New button on the left inside drawer", () => {
    renderDrawer()
    openDrawer()
    const dialog = screen.getByRole("dialog")
    const newBtn = within(dialog).getByRole("button", { name: /new/i })
    expect(newBtn).toBeTruthy()
  })

  it("renders search input inside drawer", () => {
    renderDrawer()
    openDrawer()
    const dialog = screen.getByRole("dialog")
    expect(within(dialog).getByPlaceholderText(/search/i)).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Conversation list grouping
// ---------------------------------------------------------------------------

describe("conversation list grouping", () => {
  it("shows Today group for conversations updated today", () => {
    renderDrawer()
    openDrawer()
    expect(screen.getByText("Today")).toBeTruthy()
  })

  it("shows Previous group for older conversations", () => {
    renderDrawer()
    openDrawer()
    expect(screen.getByText("Previous")).toBeTruthy()
  })

  it("shows only Today group when all conversations are from today", () => {
    renderDrawer({
      conversations: [
        makeConvo({ id: "x", title: "A", updated_at: todayAt(10) }),
        makeConvo({ id: "y", title: "B", updated_at: todayAt(11) }),
      ],
    })
    openDrawer()
    expect(screen.getByText("Today")).toBeTruthy()
    expect(screen.queryByText("Previous")).toBeNull()
  })

  it("shows only Previous group when all conversations are older", () => {
    renderDrawer({
      conversations: [
        makeConvo({ id: "x", title: "A", updated_at: daysAgo(8) }),
        makeConvo({ id: "y", title: "B", updated_at: daysAgo(10) }),
      ],
    })
    openDrawer()
    expect(screen.queryByText("Today")).toBeNull()
    expect(screen.getByText("Previous")).toBeTruthy()
  })

  it("renders conversation titles", () => {
    renderDrawer()
    openDrawer()
    expect(screen.getByText("Today's chat")).toBeTruthy()
    expect(screen.getByText("Yesterday's chat")).toBeTruthy()
    expect(screen.getByText("Old chat")).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Search filtering
// ---------------------------------------------------------------------------

describe("search filtering", () => {
  it("filters conversations by title substring (case-insensitive)", () => {
    renderDrawer()
    openDrawer()
    const input = screen.getByPlaceholderText(/search/i)
    fireEvent.change(input, { target: { value: "today" } })
    expect(screen.getByText("Today's chat")).toBeTruthy()
    expect(screen.queryByText("Yesterday's chat")).toBeNull()
    expect(screen.queryByText("Old chat")).toBeNull()
  })

  it("shows empty state when no conversations match search", () => {
    renderDrawer()
    openDrawer()
    const input = screen.getByPlaceholderText(/search/i)
    fireEvent.change(input, { target: { value: "xyzzy_nonexistent" } })
    expect(screen.getByText(/no conversations found/i)).toBeTruthy()
  })

  it("restores full list when search is cleared", () => {
    renderDrawer()
    openDrawer()
    const input = screen.getByPlaceholderText(/search/i)
    fireEvent.change(input, { target: { value: "today" } })
    fireEvent.change(input, { target: { value: "" } })
    expect(screen.getByText("Today's chat")).toBeTruthy()
    expect(screen.getByText("Yesterday's chat")).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Active conversation highlighting
// ---------------------------------------------------------------------------

describe("active conversation", () => {
  it("marks the active conversation row", () => {
    renderDrawer({ activeId: "a" })
    openDrawer()
    const row = screen
      .getByText("Today's chat")
      .closest("[role=button], .shiny-chat-history-item") as HTMLElement
    expect(row?.className).toMatch(/active/)
  })

  it("does not mark non-active rows", () => {
    renderDrawer({ activeId: "a" })
    openDrawer()
    const row = screen
      .getByText("Yesterday's chat")
      .closest("[role=button], .shiny-chat-history-item") as HTMLElement
    expect(row?.className ?? "").not.toMatch(/active/)
  })
})

// ---------------------------------------------------------------------------
// Select conversation
// ---------------------------------------------------------------------------

describe("select conversation", () => {
  it("calls onSelect with the conversation id when a row is clicked", () => {
    const { onSelect } = renderDrawer()
    openDrawer()
    const row = screen
      .getByText("Today's chat")
      .closest("[role=button], .shiny-chat-history-item") as HTMLElement
    fireEvent.click(row!)
    expect(onSelect).toHaveBeenCalledWith("a")
  })

  it("closes the drawer after selecting a conversation", () => {
    renderDrawer()
    openDrawer()
    const row = screen
      .getByText("Today's chat")
      .closest("[role=button], .shiny-chat-history-item") as HTMLElement
    fireEvent.click(row!)
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("activates row on Enter key", () => {
    const { onSelect } = renderDrawer()
    openDrawer()
    const row = screen
      .getByText("Today's chat")
      .closest("[role=button], .shiny-chat-history-item") as HTMLElement
    fireEvent.keyDown(row!, { key: "Enter" })
    expect(onSelect).toHaveBeenCalledWith("a")
  })

  it("activates row on Space key", () => {
    const { onSelect } = renderDrawer()
    openDrawer()
    const row = screen
      .getByText("Today's chat")
      .closest("[role=button], .shiny-chat-history-item") as HTMLElement
    fireEvent.keyDown(row!, { key: " " })
    expect(onSelect).toHaveBeenCalledWith("a")
  })
})

// ---------------------------------------------------------------------------
// New conversation
// ---------------------------------------------------------------------------

describe("+ New button", () => {
  it("calls onNew when + New is clicked", () => {
    const { onNew } = renderDrawer()
    openDrawer()
    const dialog = screen.getByRole("dialog")
    const newBtn = within(dialog).getByRole("button", { name: /new/i })
    fireEvent.click(newBtn)
    expect(onNew).toHaveBeenCalled()
  })

  it("closes the drawer after clicking + New", () => {
    renderDrawer()
    openDrawer()
    const dialog = screen.getByRole("dialog")
    const newBtn = within(dialog).getByRole("button", { name: /new/i })
    fireEvent.click(newBtn)
    expect(screen.queryByRole("dialog")).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Rename flow
// ---------------------------------------------------------------------------

describe("rename flow", () => {
  it("opens actions menu for a conversation", () => {
    renderDrawer()
    openDrawer()
    const menuWrapper = openMenuFor("Today's chat")
    expect(within(menuWrapper).getByText("Rename")).toBeTruthy()
  })

  it("shows inline rename input after clicking Rename", () => {
    renderDrawer()
    openDrawer()
    const menuWrapper = openMenuFor("Today's chat")
    fireEvent.click(within(menuWrapper).getByText("Rename"))
    expect(screen.getByDisplayValue("Today's chat")).toBeTruthy()
  })

  it("commits rename on Enter", () => {
    const { onRename } = renderDrawer()
    openDrawer()
    const menuWrapper = openMenuFor("Today's chat")
    fireEvent.click(within(menuWrapper).getByText("Rename"))
    const input = screen.getByDisplayValue("Today's chat")
    fireEvent.change(input, { target: { value: "New Name" } })
    fireEvent.keyDown(input, { key: "Enter" })
    expect(onRename).toHaveBeenCalledWith("a", "New Name")
  })

  it("cancels rename on Escape", () => {
    const { onRename } = renderDrawer()
    openDrawer()
    const menuWrapper = openMenuFor("Today's chat")
    fireEvent.click(within(menuWrapper).getByText("Rename"))
    const input = screen.getByDisplayValue("Today's chat")
    fireEvent.change(input, { target: { value: "Changed" } })
    fireEvent.keyDown(input, { key: "Escape" })
    expect(onRename).not.toHaveBeenCalled()
    expect(screen.queryByDisplayValue("Changed")).toBeNull()
  })

  it("cancels rename on blur", () => {
    const { onRename } = renderDrawer()
    openDrawer()
    const menuWrapper = openMenuFor("Today's chat")
    fireEvent.click(within(menuWrapper).getByText("Rename"))
    const input = screen.getByDisplayValue("Today's chat")
    fireEvent.blur(input)
    expect(onRename).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// Delete flow (inline confirm, no modal)
// ---------------------------------------------------------------------------

describe("delete flow", () => {
  it("shows Delete… option in actions menu", () => {
    renderDrawer()
    openDrawer()
    const menuWrapper = openMenuFor("Today's chat")
    expect(within(menuWrapper).getByText("Delete…")).toBeTruthy()
  })

  it("shows inline confirm after clicking Delete…", () => {
    renderDrawer()
    openDrawer()
    const menuWrapper = openMenuFor("Today's chat")
    fireEvent.click(within(menuWrapper).getByText("Delete…"))
    expect(screen.getByRole("button", { name: /confirm delete/i })).toBeTruthy()
    expect(screen.getByRole("button", { name: /cancel delete/i })).toBeTruthy()
  })

  it("does NOT call onDelete without the inline confirm step", () => {
    const { onDelete } = renderDrawer()
    openDrawer()
    const menuWrapper = openMenuFor("Today's chat")
    // Clicking Delete… should show confirm, not immediately delete
    fireEvent.click(within(menuWrapper).getByText("Delete…"))
    expect(onDelete).not.toHaveBeenCalled()
  })

  it("calls onDelete after confirming", () => {
    const { onDelete } = renderDrawer()
    openDrawer()
    const menuWrapper = openMenuFor("Today's chat")
    fireEvent.click(within(menuWrapper).getByText("Delete…"))
    fireEvent.click(screen.getByRole("button", { name: /confirm delete/i }))
    expect(onDelete).toHaveBeenCalledWith("a")
  })

  it("cancels delete on cancel button", () => {
    const { onDelete } = renderDrawer()
    openDrawer()
    const menuWrapper = openMenuFor("Today's chat")
    fireEvent.click(within(menuWrapper).getByText("Delete…"))
    fireEvent.click(screen.getByRole("button", { name: /cancel delete/i }))
    expect(onDelete).not.toHaveBeenCalled()
    expect(screen.queryByRole("button", { name: /confirm delete/i })).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Busy state (stream in flight)
// ---------------------------------------------------------------------------

describe("busy state", () => {
  it("disables + New button while busy", () => {
    renderDrawer({ busy: true })
    openDrawer()
    const dialog = screen.getByRole("dialog")
    const newBtn = within(dialog).getByRole("button", { name: /new/i })
    expect((newBtn as HTMLButtonElement).disabled).toBe(true)
  })

  it("+ New button has tooltip while busy", () => {
    renderDrawer({ busy: true })
    openDrawer()
    const dialog = screen.getByRole("dialog")
    const newBtn = within(dialog).getByRole("button", { name: /new/i })
    expect(newBtn.getAttribute("title")).toBeTruthy()
  })

  it("does not call onNew when busy and + New is clicked", () => {
    const { onNew } = renderDrawer({ busy: true })
    openDrawer()
    const dialog = screen.getByRole("dialog")
    const newBtn = within(dialog).getByRole("button", { name: /new/i })
    fireEvent.click(newBtn)
    expect(onNew).not.toHaveBeenCalled()
  })

  it("does not call onSelect when busy and row is clicked", () => {
    const { onSelect } = renderDrawer({ busy: true })
    openDrawer()
    const row = screen
      .getByText("Today's chat")
      .closest("[role=button], .shiny-chat-history-item") as HTMLElement
    fireEvent.click(row!)
    expect(onSelect).not.toHaveBeenCalled()
  })

  it("disables Delete… option in actions menu while busy", () => {
    renderDrawer({ busy: true })
    openDrawer()
    const titleEl = screen.getByText("Today's chat")
    const row = titleEl.closest(".shiny-chat-history-item") as HTMLElement
    const menuWrapper = row.querySelector(
      ".shiny-chat-history-itemmenu",
    ) as HTMLElement
    const menuBtn = within(menuWrapper).getByRole("button", {
      name: /conversation actions/i,
    })
    fireEvent.click(menuBtn)
    const deleteBtn = within(menuWrapper).getByText("Delete…")
    expect((deleteBtn as HTMLButtonElement).disabled).toBe(true)
  })

  it("allows Rename while busy (rename is not a destructive action)", () => {
    renderDrawer({ busy: true })
    openDrawer()
    const titleEl = screen.getByText("Today's chat")
    const row = titleEl.closest(".shiny-chat-history-item") as HTMLElement
    const menuWrapper = row.querySelector(
      ".shiny-chat-history-itemmenu",
    ) as HTMLElement
    const menuBtn = within(menuWrapper).getByRole("button", {
      name: /conversation actions/i,
    })
    fireEvent.click(menuBtn)
    const renameBtn = within(menuWrapper).getByText("Rename")
    expect((renameBtn as HTMLButtonElement).disabled).toBe(false)
  })

  it("conversation rows have aria-disabled and title while busy", () => {
    renderDrawer({ busy: true })
    openDrawer()
    const row = screen
      .getByText("Today's chat")
      .closest("[role=button]") as HTMLElement
    expect(row.getAttribute("aria-disabled")).toBe("true")
    expect(row.getAttribute("title")).toBeTruthy()
  })

  it("conversation rows do not have aria-disabled or title when not busy", () => {
    renderDrawer({ busy: false })
    openDrawer()
    const row = screen
      .getByText("Today's chat")
      .closest("[role=button]") as HTMLElement
    expect(row.getAttribute("aria-disabled")).toBeNull()
    expect(row.getAttribute("title")).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Closing behavior
// ---------------------------------------------------------------------------

describe("closing behavior", () => {
  it("closes on Esc key", () => {
    renderDrawer()
    openDrawer()
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }))
    })
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("closes on scrim click", () => {
    renderDrawer()
    openDrawer()
    const scrim = document.querySelector(".shiny-chat-history-scrim")
    expect(scrim).not.toBeNull()
    fireEvent.click(scrim!)
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("closes when a conversation is selected", () => {
    renderDrawer()
    openDrawer()
    const row = screen
      .getByText("Today's chat")
      .closest("[role=button], .shiny-chat-history-item") as HTMLElement
    fireEvent.click(row!)
    expect(screen.queryByRole("dialog")).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Empty conversations list
// ---------------------------------------------------------------------------

describe("empty conversations list", () => {
  it("shows no sections when conversations is empty", () => {
    renderDrawer({ conversations: [] })
    openDrawer()
    expect(screen.queryByText("Today")).toBeNull()
    expect(screen.queryByText("Previous")).toBeNull()
  })

  it("drawer still opens with empty list", () => {
    renderDrawer({ conversations: [] })
    openDrawer()
    expect(screen.getByRole("dialog")).toBeTruthy()
  })

  it("shows 'No conversations yet' when conversations is empty and no search", () => {
    renderDrawer({ conversations: [] })
    openDrawer()
    expect(screen.getByText(/no conversations yet/i)).toBeTruthy()
  })
})
