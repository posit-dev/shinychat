import { useRef, useState } from "react"
import {
  useFloating,
  autoUpdate,
  offset,
  flip,
  shift,
  arrow,
  useHover,
  useFocus,
  useClick,
  useDismiss,
  useRole,
  useInteractions,
} from "@floating-ui/react"

/**
 * Hover/focus/tap tooltip wiring that mirrors Bootstrap's tooltip behavior.
 * Owns its open state. Click is included so touch users, who have no hover,
 * can open the tooltip by tapping a (typically aria-disabled) trigger.
 *
 * strategy "fixed" + flip/shift let the tooltip escape the message list's
 * overflow:auto, as in useDismissiblePopover.
 */
export function useTooltip() {
  const [open, setOpen] = useState(false)
  const arrowRef = useRef<SVGSVGElement>(null)
  const { refs, floatingStyles, context } = useFloating({
    open,
    onOpenChange: setOpen,
    strategy: "fixed",
    placement: "bottom",
    middleware: [
      offset(6),
      flip(),
      shift({ padding: 8 }),
      arrow({ element: arrowRef }),
    ],
    whileElementsMounted: autoUpdate,
  })
  const hover = useHover(context, { move: false })
  const focus = useFocus(context)
  const click = useClick(context)
  const dismiss = useDismiss(context, { outsidePressEvent: "mousedown" })
  const role = useRole(context, { role: "tooltip" })
  const { getReferenceProps, getFloatingProps } = useInteractions([
    hover,
    focus,
    click,
    dismiss,
    role,
  ])
  return {
    open,
    refs,
    floatingStyles,
    context,
    arrowRef,
    getReferenceProps,
    getFloatingProps,
  }
}
