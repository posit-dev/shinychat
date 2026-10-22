export type SubmitKey = "enter" | "enter+modifier"

export function submitKeyLabel(submitKey: SubmitKey): string {
  if (submitKey === "enter") return "Enter"
  const isMac =
    typeof navigator !== "undefined" &&
    /Mac|iPhone|iPad/.test(navigator.platform)
  return isMac ? "⌘+Enter" : "Ctrl+Enter"
}
