import { forwardRef, useImperativeHandle, useRef } from "react"
import { useEditor, EditorContent } from "@tiptap/react"
import StarterKit from "@tiptap/starter-kit"
import { Extension } from "@tiptap/core"
import { Plugin, PluginKey } from "@tiptap/pm/state"
import { Decoration, DecorationSet } from "@tiptap/pm/view"
import { Editor, type JSONContent, type Range } from "@tiptap/core"
import { CommandMention } from "./tiptap/commandMention"
import { createSuggestionRender } from "./tiptap/suggestionRender"
import type { SubmitKey } from "./tiptap/submitShortcut"
import { filterSlashCommands } from "./SlashCommandPalette"
import { useInputHistory } from "./useInputHistory"
import type { SlashCommandDef } from "../transport/types"

export interface TiptapInputHandle {
  setInputValue(
    value: string,
    options?: { submit?: boolean; focus?: boolean },
  ): void
  focus(): void
  serializeEditor(): string
}

export interface TiptapInputProps {
  inputId: string
  placeholder: string
  hasTopShadow?: boolean
  slashCommands: SlashCommandDef[]
  onHasTextChange: (hasText: boolean) => void
  onSubmit: (content: string) => boolean
  userMessages: string[]
  submitKey: SubmitKey
}

export function serializeEditor(editor: Editor): string {
  const doc = editor.state.doc
  const parts: string[] = []

  doc.descendants((node) => {
    if (node.type.name === "commandMention") {
      parts.push(`/${node.attrs.name}`)
      return false
    }
    if (node.type.name === "text") {
      parts.push(node.text ?? "")
      return false
    }
    if (node.type.name === "hardBreak") {
      parts.push("\n")
      return false
    }
    if (node.type.name === "paragraph" && parts.length > 0) {
      parts.push("\n")
    }
    return true
  })

  return parts.join("")
}

function parseToDoc(text: string, commands: SlashCommandDef[]): JSONContent {
  if (!text) {
    return { type: "doc", content: [{ type: "paragraph" }] }
  }

  if (text.startsWith("/")) {
    const withoutSlash = text.slice(1)
    const spaceIndex = withoutSlash.indexOf(" ")
    const commandName =
      spaceIndex === -1 ? withoutSlash : withoutSlash.slice(0, spaceIndex)
    const rest = spaceIndex === -1 ? "" : withoutSlash.slice(spaceIndex + 1)
    const matched = commands.find((cmd) => cmd.name === commandName)
    if (matched) {
      const content: JSONContent[] = [
        { type: "commandMention", attrs: { name: commandName } },
      ]
      if (rest) {
        content.push({ type: "text", text: " " + rest })
      }
      return { type: "doc", content: [{ type: "paragraph", content }] }
    }
  }

  const lines = text.split("\n")
  const content = lines.map((line) => {
    if (line === "") return { type: "paragraph" }
    return { type: "paragraph", content: [{ type: "text", text: line }] }
  })
  return { type: "doc", content }
}

export const TiptapInput = forwardRef<TiptapInputHandle, TiptapInputProps>(
  function TiptapInput(
    {
      inputId,
      placeholder,
      hasTopShadow = false,
      slashCommands,
      onHasTextChange,
      onSubmit,
      userMessages,
      submitKey,
    },
    ref,
  ) {
    const { recall, reset, isActive } = useInputHistory(userMessages)
    const slashCommandsRef = useRef(slashCommands)
    slashCommandsRef.current = slashCommands
    const placeholderRef = useRef(placeholder)
    placeholderRef.current = placeholder
    const onSubmitRef = useRef(onSubmit)
    onSubmitRef.current = onSubmit
    const onHasTextChangeRef = useRef(onHasTextChange)
    onHasTextChangeRef.current = onHasTextChange
    const resetRef = useRef(reset)
    resetRef.current = reset
    const editorInstanceRef = useRef<Editor | null>(null)

    const editor = useEditor({
      extensions: [
        StarterKit.configure({
          blockquote: false,
          bulletList: false,
          codeBlock: false,
          heading: false,
          horizontalRule: false,
          listItem: false,
          orderedList: false,
          bold: false,
          italic: false,
          code: false,
          strike: false,
        }),
        Extension.create({
          name: "placeholder",
          addProseMirrorPlugins() {
            return [
              new Plugin({
                key: new PluginKey("placeholder"),
                props: {
                  decorations(state) {
                    const doc = state.doc
                    const isEmpty =
                      doc.childCount === 1 &&
                      doc.firstChild?.isTextblock &&
                      doc.firstChild.content.size === 0
                    if (!isEmpty) return DecorationSet.empty
                    return DecorationSet.create(doc, [
                      Decoration.node(0, doc.firstChild!.nodeSize, {
                        class: "is-empty",
                        "data-placeholder": placeholderRef.current,
                      }),
                    ])
                  },
                },
              }),
            ]
          },
        }),
        Extension.create({
          name: "submitShortcut",
          priority: 200,
          addKeyboardShortcuts() {
            const submit = () => {
              if (this.editor.isEmpty) return false
              const content = serializeEditor(this.editor)
              if (content.trim().length === 0) return false
              if (onSubmitRef.current(content)) {
                this.editor.commands.clearContent(true)
                onHasTextChangeRef.current(false)
                resetRef.current()
              }
              return true
            }
            const key = submitKey === "enter+modifier" ? "Mod-Enter" : "Enter"
            const shortcuts: Record<string, () => boolean> = { [key]: submit }
            if (submitKey === "enter+modifier") {
              shortcuts["Enter"] = () =>
                this.editor.commands.first(({ commands }) => [
                  () => commands.newlineInCode(),
                  () => commands.setHardBreak(),
                ])
            }
            return shortcuts
          },
        }),
        CommandMention.configure({
          commands: slashCommands,
          suggestion: {
            char: "/",
            allowSpaces: false,
            allow({ range }: { range: { from: number } }) {
              return range.from === 1
            },
            items: ({ query }: { query: string }) => {
              return filterSlashCommands(slashCommandsRef.current, query)
            },
            render: () =>
              createSuggestionRender({
                paletteId: `${inputId}-slash-palette`,
              }),
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
          },
        }),
      ],
      editorProps: {
        attributes: {
          "aria-label": "Chat message",
          "data-shiny-no-bind-input": "",
          role: "textbox",
          "aria-multiline": "true",
          ...(slashCommands.length > 0 ? { "aria-haspopup": "listbox" } : {}),
          class: `form-control${hasTopShadow ? " shadow" : ""}`,
        },
        handleKeyDown: (view, event) => {
          if (event.isComposing) return false

          if (event.key === "ArrowUp" || event.key === "ArrowDown") {
            const ed = editorInstanceRef.current
            if (!ed) return false
            const serialized = serializeEditor(ed)
            const { $from } = view.state.selection
            const atEnd = $from.pos === view.state.doc.content.size - 1
            const canRecall = isActive() ? atEnd : serialized.length === 0

            if (canRecall) {
              const value = recall(
                event.key === "ArrowUp" ? "up" : "down",
                serialized,
              )
              if (value !== undefined) {
                event.preventDefault()
                ed.commands.setContent(
                  parseToDoc(value, slashCommandsRef.current),
                )
                onHasTextChange(value.trim().length > 0)
                ed.commands.focus("end")
                return true
              }
            }
            return false
          }

          return false
        },
      },
      onCreate: ({ editor: ed }) => {
        editorInstanceRef.current = ed
        onHasTextChange(!ed.isEmpty)
      },
      onUpdate: ({ editor }) => {
        onHasTextChange(!editor.isEmpty)
      },
    })

    useImperativeHandle(
      ref,
      () => ({
        setInputValue(
          value: string,
          {
            submit = false,
            focus: shouldFocus = false,
          }: { submit?: boolean; focus?: boolean } = {},
        ) {
          if (!editor) return
          const oldContent = serializeEditor(editor)
          editor.commands.setContent(
            parseToDoc(value, slashCommandsRef.current),
          )
          onHasTextChange(value.trim().length > 0)

          if (submit) {
            const serialized = serializeEditor(editor)
            onSubmit(serialized)
            editor.commands.setContent(
              parseToDoc(oldContent, slashCommandsRef.current),
            )
            onHasTextChange(oldContent.trim().length > 0)
          }
          if (shouldFocus) {
            editor.commands.focus("end")
          }
        },
        focus() {
          editor?.commands.focus("end")
        },
        serializeEditor() {
          return editor ? serializeEditor(editor) : ""
        },
      }),
      [editor, onSubmit, onHasTextChange],
    )

    return <EditorContent editor={editor} id={inputId} />
  },
)
