export type ContentType = "markdown" | "semi-markdown" | "html" | "text"

export interface Message {
  content: string
  role: "user" | "assistant"
  chunk_type?: "message_start" | "message_end" | null
  content_type?: ContentType
  icon?: string
  operation?: "append" | null
  id?: string
}

export interface UpdateUserInput {
  value?: string
  placeholder?: string
  submit?: boolean
  focus?: boolean
}

export interface ChatInputSetInputOptions {
  submit?: boolean
  focus?: boolean
}
