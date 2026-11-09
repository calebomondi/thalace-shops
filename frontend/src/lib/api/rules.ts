import { apiFetch } from './client'
import type { Shop } from './shops'

export type PayeeRoute = 'transfer' | 'withdraw'

/** Mirrors the backend's PayeeIn / PayeeOut. */
export type Payee = {
  label: string
  route: PayeeRoute
  chain: string | null
  address: string
  memo: string | null
  share_bps: number
}

export type PlatformTerms = {
  fee_bps: number
  max_fee_bps: number
  fee_account: string
}

export const getPlatformTerms = () => apiFetch<PlatformTerms>('/platform/terms')

export const listPayees = (shopId: string) => apiFetch<Payee[]>(`/shops/${shopId}/payees`)

export const replacePayees = (shopId: string, payees: Payee[]) =>
  apiFetch<Payee[]>(`/shops/${shopId}/payees`, { method: 'PUT', body: JSON.stringify({ payees }) })

export const setDailyBudget = (shopId: string, dailyBudgetUsd: string) =>
  apiFetch<Shop>(`/shops/${shopId}/budget`, {
    method: 'PUT',
    body: JSON.stringify({ daily_budget_usd: dailyBudgetUsd }),
  })
