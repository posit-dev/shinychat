import { defaultSchema } from "rehype-sanitize"
import type { Schema } from "hast-util-sanitize"

/**
 * Custom sanitization schema extending GitHub's default.
 *
 * Key customizations:
 * - Allow <script type="application/json" data-for="..."> for htmlwidgets
 * - Whitelist shiny-tool-request/result custom elements with their attributes
 * - Allow form elements (select, label, button, etc.) for Shiny UI widgets
 *   delivered via {=html} fenced blocks
 * - Allow class, style, data-*, and other attributes Shiny inputs need
 * - Allow data-external-link, target, rel on <a> tags
 * - Allow hljs-* class patterns for syntax highlighting
 * - Disable clobberPrefix to preserve id/name attributes for Shiny binding
 * - Override defaultSchema's `required` to stop forcing input to disabled checkbox
 */
export const customSchema: Schema = {
  ...defaultSchema,

  // Remove script from strip list (gotcha #1: strip deletes content, not just the tag)
  strip: (defaultSchema.strip ?? []).filter((tag) => tag !== "script"),

  // Disable clobber prefix (gotcha #3: would rename id/name attributes)
  clobber: [],

  // Override defaultSchema.required which forces input to disabled checkbox
  required: {},

  tagNames: [
    ...(defaultSchema.tagNames ?? []),
    "script",
    "shiny-tool-request",
    "shiny-tool-result",
    "shiny-markdown-stream",
    // Form elements used by Shiny UI widgets (delivered via {=html} blocks)
    "select",
    "option",
    "optgroup",
    "label",
    "button",
    "form",
    "textarea",
    "fieldset",
    "legend",
    "output",
  ],

  attributes: {
    ...defaultSchema.attributes,

    // Allow class, style, data-*, role, and aria-* on all elements.
    // Shiny UI widgets use class extensively for binding (e.g.,
    // "shiny-input-container", "form-control", "shiny-input-select").
    // data-* attributes are used for Shiny binding metadata (e.g., data-update-on).
    "*": [
      ...(defaultSchema.attributes?.["*"] ?? []),
      "className",
      "style",
      "data*",
      "role",
      "aria*",
    ],

    // htmlwidget scripts: only allow type=application/json with data-for
    script: [["type", "application/json"], "data-for"],

    // Form element attributes needed by Shiny inputs
    input: [
      "type",
      "checked",
      "disabled",
      "min",
      "max",
      "step",
      "placeholder",
      "autocomplete",
      "required",
      "readonly",
      "pattern",
    ],
    select: ["multiple", "disabled", "required"],
    option: ["selected", "disabled"],
    optgroup: ["disabled"],
    button: ["type", "disabled"],
    textarea: [
      "placeholder",
      "disabled",
      "required",
      "readonly",
      "rows",
      "cols",
    ],
    label: ["htmlFor"],

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
    span: [...(defaultSchema.attributes?.span ?? []), ["className", /^hljs-/]],
    pre: [...(defaultSchema.attributes?.pre ?? []), "data*"],
  },
}
