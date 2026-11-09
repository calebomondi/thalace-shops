import { apiFetch } from './client'
import type { Shop } from './shops'

export type ShopSignatureType = 'agent_create' | 'grant_issue' | 'policy_update' | 'agent_freeze' | 'agent_unfreeze'
export type SignatureStatus = 'awaiting_signature' | 'submitted' | 'succeeded' | 'failed' | 'expired'

/** Public data only: the private key never leaves the founder's device. */
export type PasskeyOwner = { credential_id: string; public_key: string; rp_id: string; origin: string }

export type PasskeyStatus = { has_passkey: boolean; rp_id: string; origin: string }

/** Mirrors the backend's PendingSignatureOut. `intent` goes to the passkey prompt unchanged. */
export type PendingSignature = {
  correlation_id: string
  type: ShopSignatureType
  intent: { standard: string; payload: unknown }
  preview: { summary?: string; policy?: unknown }
  expires_at: string
}

export type SignatureState = {
  correlation_id: string
  type: ShopSignatureType
  status: SignatureStatus
  failure_code: string | null
  shop: Shop
}

export const getPasskeyStatus = () => apiFetch<PasskeyStatus>('/passkeys/current')

export const addPasskey = (passkey: PasskeyOwner) =>
  apiFetch<PasskeyStatus>('/passkeys', { method: 'POST', body: JSON.stringify(passkey) })

export const requestSignature = (shopId: string) =>
  apiFetch<PendingSignature>(`/shops/${shopId}/signatures`, { method: 'POST' })

export const submitSignature = (shopId: string, correlationId: string, signedData: Record<string, unknown>) =>
  apiFetch<SignatureState>(`/shops/${shopId}/signatures/${correlationId}`, {
    method: 'POST',
    body: JSON.stringify({ signed_data: signedData }),
  })

export const getSignature = (shopId: string, correlationId: string) =>
  apiFetch<SignatureState>(`/shops/${shopId}/signatures/${correlationId}`)
