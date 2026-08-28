export type ToolResultOpenStyle = "minimal" | "framed"

export function isTruthyAttribute(
  value: string | boolean | undefined,
): boolean {
  return value === true || value === "" || value === "true"
}
