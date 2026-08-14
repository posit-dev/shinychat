// <shiny-aside> is a data carrier consumed by <shiny-aside-group>
// (see rehypeGroupAsides). If one ever reaches the React tree ungrouped —
// e.g. content that bypassed the markdown pipeline's grouping pass — it
// renders nothing instead of showing a stray custom element. Also used as
// the defensive fallback for standalone web-activity carriers.
export function Aside(): null {
  return null
}
