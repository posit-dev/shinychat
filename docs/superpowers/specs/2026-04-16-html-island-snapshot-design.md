# Snapshot HTML Island Payloads

## Goal

Guarantee that `shinychat-raw-html` islands preserve the exact HTML string that the server sent even after the markdown rehype pipeline continues to run, so downstream rendering can treat each island as an opaque payload.

## Background

- `markdownProcessor` already mixes markdown content with HTML islands by running `remarkRehype` followed by `rehypeRaw`.
- Later rehype plugins such as `rehypeAccessibleSuggestions` and `rehypeExternalLinks` mutate the tree in place, which means the node children in a `shinychat-raw-html` island no longer match the original markup that was rendered by the server.
- The island contract should restore the pre-React behavior: React may treat islands as black boxes, but the server owns the markup.

## Requirements

1. Snapshot the inner HTML of each `<shinychat-raw-html>` node immediately after `rehypeRaw` runs (before any other rehype plugin mutates its children).
2. Store that HTML string on the node so renderers can reference it even after further rehype steps.
3. Expose a well-known key (`HTML_ISLAND_RAW_HTML`) so rendering code can read the payload without hardcoding `rawHtml`.
4. Keep subsequent rehype plugins connected to the rest of the tree so they can still touch attributes inside islands for the future DOM helper layer.
5. Limit the plugin to `markdownProcessor` so we do not snapshot raw HTML fragments that go through the simpler `htmlProcessor`/`userMarkdownProcessor`.

## Proposed Implementation

- Add `js/src/markdown/plugins/rehypeSnapshotHtmlIslands.ts`:
  - Import `visit` from `unist-util-visit`, `Plugin`, and `Element`/`Root` types from `hast`, plus `toHtml` from `hast-util-to-html`.
  - Export `HTML_ISLAND_RAW_HTML = "rawHtml"`.
  - The plugin visits elements whose `tagName === "shinychat-raw-html"`.
  - For each island, use `toHtml(node.children ?? [])` to render the current child tree back into a string, then stash it on `node.data ??= {}` so that `node.data[HTML_ISLAND_RAW_HTML] = serialized`.
  - Do nothing if the node lacks children or already has a snapshot.

- Update `js/src/markdown/processors.ts`:
  - Import the new plugin.
  - Register it in `markdownProcessor` immediately after `.use(rehypeRaw)` so that all downstream plugins mutate the tree after the snapshot is stored.
  - Leave `htmlProcessor`/`userMarkdownProcessor` untouched.

- Add `js/tests/markdown/plugins/rehypeSnapshotHtmlIslands.test.ts`:
  - Build a small pipeline (`remarkParse` → `remarkRehype` allow dangerous HTML → `rehypeRaw` → snapshot plugin → `rehypeAccessibleSuggestions` → custom visitor) and run `processSync`.
  - After processing, find the `shinychat-raw-html` node and assert that `node.data?.rawHtml` (the exported key) matches the HTML string that was inside the island before `rehypeAccessibleSuggestions` added `tabindex`, `role`, etc.
  - Confirm the plugin runs even when other rehype transformations touch the island tree, but the stored payload remains stable.

## Testing

1. Run the new plugin test to validate the snapshot behavior fails before the implementation and passes afterward.
2. After wiring the plugin into `markdownProcessor`, rerun the existing plugin suites (`rehypeAccessibleSuggestions`, `rehypeExternalLinks`, `rehypeSnapshotHtmlIslands`) to ensure there are no regressions in their expectations.

## Risks

- If we serialize children with `toHtml` and the `HAST` has already been mutated by `rehypeRaw`, the snapshot may include normalized spacing/quotes. That is acceptable because the children at this point exactly reflect the server payload parsed by `rehypeRaw`; any later mutations should not affect this historic string.
- Forgetting to export or register `HTML_ISLAND_RAW_HTML` would mean downstream renderers keep computing from `node.children`. The spec enforces both.

## Next Steps

1. Have the user review this design (spec file committed under `docs/superpowers/specs/`).
2. After approval, invoke the `writing-plans` skill to break the work into implementation steps.
