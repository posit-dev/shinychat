/**
 * Formats a string as a Markdown fenced code block with the specified language.
 */
export function markdownCodeBlock(
  content: string,
  language: string = "markdown",
): string {
  const backticks = "`".repeat(8)
  return `${backticks}${language}\n${content}\n${backticks}`
}
