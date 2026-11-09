import { apiFetch } from './client'
import type { Payee } from './rules'
import type { PendingSignature } from './signing'
import type { Shop } from './shops'

export type Supplier = { id: string; slug: string; name: string; wallet_account_id: string | null }

export const pauseShop = (shopId: string) => apiFetch<Shop>(`/shops/${shopId}/pause`, { method: 'POST' })

export const resumeShop = (shopId: string) => apiFetch<Shop>(`/shops/${shopId}/resume`, { method: 'POST' })

export const requestFreeze = (shopId: string, freeze: boolean) =>
  apiFetch<PendingSignature>(`/shops/${shopId}/wallet/freeze`, { method: 'POST', body: JSON.stringify({ freeze }) })

export const requestRulesChange = (shopId: string, body: { payees: Payee[]; daily_budget_usd: string; supplier_shop_ids: string[] }) =>
  apiFetch<PendingSignature>(`/shops/${shopId}/wallet/rules`, { method: 'POST', body: JSON.stringify(body) })

export const listSuppliers = (shopId: string) => apiFetch<Supplier[]>(`/shops/${shopId}/suppliers`)
