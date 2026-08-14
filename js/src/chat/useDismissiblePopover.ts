import {
  useFloating,
  autoUpdate,
  offset,
  flip,
  shift,
  useHover,
  useFocus,
  useClick,
  useDismiss,
  useRole,
  useInteractions,
} from "@floating-ui/react"

// Gap between the pill and the popover is a dead zone the pointer must cross.
// useHover's delay.close keeps the popover alive long enough to reach it, and
// is canceled automatically if the pointer lands back on the pill or popover
// before it elapses.
const CLOSE_GRACE_PERIOD_MS = 150

/**
 * Shared hover/focus/click/dismiss popover wiring for the citation aside pill
 * and the Sources summary pill. Caller owns the open state.
 *
 * strategy "fixed" + flip/shift let the popover escape the message list's
 * overflow:auto and reposition when there isn't room where it'd normally go.
 * useClick pins the popover (clicking again un-pins); useHover then no longer
 * auto-closes it on mouse-leave.
 */
export function useDismissiblePopover(
  open: boolean,
  setOpen: (open: boolean) => void,
) {
  const { refs, floatingStyles, context } = useFloating({
    open,
    onOpenChange: setOpen,
    strategy: "fixed",
    placement: "bottom-start",
    middleware: [offset(6), flip(), shift({ padding: 8, crossAxis: true })],
    whileElementsMounted: autoUpdate,
  })
  const hover = useHover(context, { delay: { close: CLOSE_GRACE_PERIOD_MS } })
  const focus = useFocus(context)
  const click = useClick(context)
  const dismiss = useDismiss(context, { outsidePressEvent: "mousedown" })
  const role = useRole(context)
  const { getReferenceProps, getFloatingProps } = useInteractions([
    hover,
    focus,
    click,
    dismiss,
    role,
  ])
  return { refs, floatingStyles, context, getReferenceProps, getFloatingProps }
}
