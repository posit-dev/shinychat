import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import { rehypeUncontrolledInputs } from "../../../src/markdown/plugins/rehypeUncontrolledInputs"

function process(md: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRaw)
      .use(rehypeUncontrolledInputs)
      .use(rehypeStringify)
      .processSync(md),
  )
}

describe("rehypeUncontrolledInputs", () => {
  it("converts value to defaultvalue on <input> and removes value attribute", () => {
    const md = '<input value="x">'
    const html = process(md)
    expect(html).toContain("defaultValue")
    expect(html).not.toContain('value="x"')
  })

  it("converts checked to defaultchecked on <input>", () => {
    const md = "<input checked>"
    const html = process(md)
    expect(html).toContain("defaultChecked")
    expect(html).not.toContain(" checked")
  })

  it("converts value to defaultvalue on <textarea>", () => {
    const md = '<textarea value="x"></textarea>'
    const html = process(md)
    expect(html).toContain("defaultValue")
    expect(html).not.toContain('value="x"')
  })

  it("leaves <input> without value or checked unchanged", () => {
    const md = '<input type="text">'
    const html = process(md)
    expect(html).not.toContain("defaultValue")
    expect(html).not.toContain("defaultChecked")
    expect(html).toContain("<input")
  })

  it("does not modify value attribute on non-input elements", () => {
    const md = '<div value="x"></div>'
    const html = process(md)
    // div is not input/textarea, so value should remain
    expect(html).not.toContain("defaultvalue")
  })
})
