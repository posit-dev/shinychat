import { Node, mergeAttributes, type Editor, type Range } from "@tiptap/core"
import { Suggestion, type SuggestionOptions } from "@tiptap/suggestion"
import {
  NodeSelection,
  Plugin,
  PluginKey,
  TextSelection,
} from "@tiptap/pm/state"
import type { SlashCommandDef } from "../../transport/types"

export const CommandMention = Node.create({
  name: "commandMention",

  group: "inline",

  inline: true,

  atom: true,

  selectable: true,

  addOptions() {
    return {
      commands: [] as SlashCommandDef[],
      suggestion: {
        char: "/",
        allowSpaces: false,
        allow({ range }: { range: { from: number } }) {
          return range.from === 1
        },
        command: ({
          editor: ed,
          range,
          props,
        }: {
          editor: Editor
          range: Range
          props: { name: string }
        }) => {
          ed.chain()
            .focus()
            .deleteRange(range)
            .insertContent([
              { type: "commandMention", attrs: { name: props.name } },
              { type: "text", text: " " },
            ])
            .run()
        },
      } as Partial<SuggestionOptions>,
    }
  },

  addAttributes() {
    return {
      name: {
        default: null,
      },
    }
  },

  parseHTML() {
    return [
      {
        tag: "span[data-command-mention]",
        getAttrs: (el) => ({
          name: (el as HTMLElement).getAttribute("data-command-mention"),
        }),
      },
    ]
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(HTMLAttributes, {
        "data-command-mention": node.attrs.name,
        class: "command-chip",
      }),
      `/${node.attrs.name}`,
    ]
  },

  addKeyboardShortcuts() {
    return {
      Backspace: () => {
        const { state, view } = this.editor
        const { selection } = state
        const { $from } = selection

        if (
          selection instanceof NodeSelection &&
          selection.node.type.name === "commandMention"
        ) {
          const name = selection.node.attrs.name
          const pos = selection.from
          const tr = state.tr.replaceWith(
            pos,
            selection.to,
            state.schema.text(`/${name}`),
          )
          tr.setSelection(TextSelection.create(tr.doc, pos + name.length + 1))
          view.dispatch(tr)
          return true
        }

        const nodeBefore = $from.nodeBefore
        if (nodeBefore?.type.name === "commandMention") {
          const name = nodeBefore.attrs.name
          const pos = $from.pos - nodeBefore.nodeSize
          const tr = state.tr.replaceWith(
            pos,
            $from.pos,
            state.schema.text(`/${name}`),
          )
          tr.setSelection(TextSelection.create(tr.doc, pos + name.length + 1))
          view.dispatch(tr)
          return true
        }

        return false
      },
    }
  },

  addProseMirrorPlugins() {
    const extensionOptions = this.options

    return [
      Suggestion({
        editor: this.editor,
        ...this.options.suggestion,
      }),
      new Plugin({
        key: new PluginKey("commandMentionPaste"),
        props: {
          handlePaste: (view, event) => {
            const text = event.clipboardData?.getData("text/plain") ?? ""
            if (!text.startsWith("/")) return false

            const withoutSlash = text.slice(1)
            const spaceIndex = withoutSlash.indexOf(" ")
            const commandName =
              spaceIndex === -1
                ? withoutSlash
                : withoutSlash.slice(0, spaceIndex)
            const rest = spaceIndex === -1 ? "" : withoutSlash.slice(spaceIndex)

            const commands: SlashCommandDef[] = extensionOptions.commands
            const matched = commands.find((cmd) => cmd.name === commandName)
            if (!matched) return false

            const { state } = view
            const commandMentionType = state.schema.nodes["commandMention"]
            if (!commandMentionType) return false

            const nodes = []
            nodes.push(commandMentionType.create({ name: commandName }))
            if (rest) {
              nodes.push(state.schema.text(rest))
            }

            const tr = state.tr
            const { from, to } = state.selection
            tr.replaceWith(from, to, nodes)
            view.dispatch(tr)
            return true
          },
        },
      }),
    ]
  },
})

export default CommandMention
