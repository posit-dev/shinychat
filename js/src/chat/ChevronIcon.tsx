interface ChevronIconProps {
  className: string
  expanded: boolean
}

/**
 * Disclosure chevron for collapsible sections, pointing right when collapsed
 * and rotated to point down when expanded.
 *
 * The box is a fixed 12px square regardless of the surrounding font, so its
 * horizontal center is always 6px from the box's left edge. Collapsible left
 * rails align to that column via a `--_chevron-center: 6px` custom property;
 * a text glyph would put the column at a font-dependent offset instead.
 */
export function ChevronIcon({ className, expanded }: ChevronIconProps) {
  return (
    <svg
      className={className}
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      aria-hidden="true"
      {...(expanded ? { "data-expanded": "" } : {})}
    >
      <path
        d="M4.5 2.5L8 6L4.5 9.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
