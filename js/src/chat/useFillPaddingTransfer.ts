import { useEffect, type RefObject } from "react"

// When a fill-enabled chat is the sole child of a padded bslib fillable
// container (sidebar main, card body, page_fillable, …), the parent's padding
// insets the whole chat — including the full-width history trigger and drawer,
// which anchor to shiny-chat-container. Move that padding onto the centered
// content column instead: zero the parent's padding and hand the captured
// value to --shiny-chat-fill-padding, so the trigger/drawer sit flush with the
// parent edge while the messages + input keep equivalent breathing room.
// Setting the parent's inline padding directly beats a card_body(padding=)
// inline style, which a stylesheet rule could not.
export function useFillPaddingTransfer(
  scrollRef: RefObject<HTMLElement | null>,
): void {
  useEffect(() => {
    const container = scrollRef.current?.closest<HTMLElement>(
      "shiny-chat-container",
    )
    if (!container?.hasAttribute("fill")) return
    if (!container.classList.contains("html-fill-item")) return

    // Walk up the chain of fillable containers the chat solely occupies (each an
    // .html-fill-container whose only element child is the node below it) to the
    // FIRST one that actually carries padding, and stop there. The chat is a fill
    // item inside its fillable parent, but bslib can insert zero-padding wrapper
    // layers — e.g. page_sidebar(fillable=TRUE) nests a .bslib-page-main inside
    // the padded sidebar .main — so the padded box may sit a level or two up.
    // Stopping at the first padded ancestor keeps us inside the chat's own visual
    // container: in a card the .card-body padding transfers, but we must NOT climb
    // past the card to also strip the surrounding sidebar-main padding (that would
    // pull the whole card flush to the layout edge).
    let target: HTMLElement | null = null
    let targetPadding = ""
    let node: HTMLElement = container
    while (
      node.parentElement instanceof HTMLElement &&
      node.parentElement.classList.contains("html-fill-container") &&
      node.parentElement.children.length === 1
    ) {
      node = node.parentElement
      const pad = getComputedStyle(node).paddingLeft
      if (parseFloat(pad) > 0) {
        target = node
        targetPadding = pad
        break
      }
    }
    if (!target) return

    // Zeroing the padded ancestor's inline padding beats a card_body(padding=)
    // inline style, which a stylesheet rule could not. --_chat-container-padding
    // is a single-value token (used in calc() and padding-inline), so hand it the
    // horizontal inset; fillable paddings are uniform.
    const prevInlinePadding = target.style.padding
    target.style.padding = "0"
    container.style.setProperty("--shiny-chat-fill-padding", targetPadding)

    return () => {
      target.style.padding = prevInlinePadding
      container.style.removeProperty("--shiny-chat-fill-padding")
    }
  }, [scrollRef])
}
