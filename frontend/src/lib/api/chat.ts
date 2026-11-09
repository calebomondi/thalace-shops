import { apiFetch } from './client'

/** Mirrors the backend's ChatMessageOut. */
export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  actions: string[]
  created_at: string
}

export const getConversation = (shopId: string) => apiFetch<ChatMessage[]>(`/shops/${shopId}/chat`)

export const sendMessage = (shopId: string, message: string) =>
  apiFetch<ChatMessage[]>(`/shops/${shopId}/chat`, { method: 'POST', body: JSON.stringify({ message }) })
