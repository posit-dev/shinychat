// <shiny-sidenote> is a data carrier consumed by <shiny-sidenote-group>
// (see rehypeGroupSidenotes). If one ever reaches the React tree ungrouped —
// e.g. content that bypassed the markdown pipeline's grouping pass — it
// renders nothing instead of showing a stray custom element. Also used as
// the defensive fallback for standalone web-activity carriers.
export function Sidenote(): null {
  return null
}
