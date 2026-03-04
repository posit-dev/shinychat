import { defaultSchema } from "rehype-sanitize"
import type { Schema } from "hast-util-sanitize"

/**
 * Custom sanitization schema extending GitHub's default.
 *
 * Key customizations:
 * - Allow <script type="application/json" data-for="..."> for htmlwidgets
 * - Whitelist shiny-tool-request/result custom elements with their attributes
 * - Allow data-external-link, target, rel on <a> tags
 * - Allow hljs-* class patterns for syntax highlighting
 * - Disable clobberPrefix to preserve id/name attributes for Shiny binding
 *
 * See design doc "Unified Pipeline Migration Risks & Gotchas" for details.
 */
export const customSchema: Schema = {
  ...defaultSchema,

  // Remove script from strip list (gotcha #1: strip deletes content, not just the tag)
  strip: (defaultSchema.strip ?? []).filter((tag) => tag !== "script"),

  // Disable clobber prefix (gotcha #3: would rename id/name attributes)
  clobber: [],

  tagNames: [
    ...(defaultSchema.tagNames ?? []),
    "script",
    "shiny-tool-request",
    "shiny-tool-result",
    "shiny-markdown-stream",
  ],

  attributes: {
    ...defaultSchema.attributes,

    // htmlwidget scripts: only allow type=application/json with data-for
    script: [["type", "application/json"], "data-for"],

    // Custom elements: enumerate all attributes (gotcha #2: no wildcards)
    "shiny-tool-request": [
      "request-id",
      "tool-name",
      "tool-title",
      "intent",
      "expanded",
      "hidden",
      "arguments",
      "class",
      "data*",
    ],
    "shiny-tool-result": [
      "request-id",
      "tool-name",
      "tool-title",
      "intent",
      "expanded",
      "status",
      "value",
      "value-type",
      "show-request",
      "request-call",
      "class",
      "data*",
    ],
    "shiny-markdown-stream": [
      "content",
      "content-type",
      "streaming",
      "auto-scroll",
      "class",
      "data*",
    ],

    // External link attributes (added by rehypeExternalLinks after sanitize)
    a: [
      ...(defaultSchema.attributes?.a ?? []),
      "dataExternalLink",
      "target",
      "rel",
    ],

    // Syntax highlighting classes (gotcha #7)
    code: [
      ...(defaultSchema.attributes?.code ?? []),
      ["className", /^language-/, /^hljs-/, "hljs"],
    ],
    span: [
      ...(defaultSchema.attributes?.span ?? []),
      ["className", /^hljs-/],
    ],
    pre: [...(defaultSchema.attributes?.pre ?? []), "data*"],
  },
}
