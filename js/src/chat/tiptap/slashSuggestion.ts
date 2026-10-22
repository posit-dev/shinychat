import type { SlashCommandDef } from "../../transport/types"

export function slashPaletteAllowed(
  from: number,
  commands: SlashCommandDef[],
): boolean {
  return from === 0 && commands.length > 0
}

export function paletteOwnsEnter(
  suggestion: { active?: boolean } | null | undefined,
  listedCommands: SlashCommandDef[],
): boolean {
  return Boolean(suggestion?.active) && listedCommands.length > 0
}
