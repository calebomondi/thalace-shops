import { apiFetch } from './client'

export type ShopStatus = 'draft' | 'live' | 'paused'

/** Mirrors the backend's ShopOut. */
export type Shop = {
  id: string
  slug: string
  name: string
  tagline: string
  description: string
  website: string | null
  status: ShopStatus
  settlement_asset: string
  daily_budget_usd: string
  wallet_account_id: string | null
  frozen: boolean
  live_since: string | null
  created_at: string
}

export type ShopCreate = {
  name: string
  slug?: string
  tagline?: string
  description?: string
  website?: string
}

export const listShops = () => apiFetch<Shop[]>('/shops')

export const createShop = (body: ShopCreate) =>
  apiFetch<Shop>('/shops', { method: 'POST', body: JSON.stringify(body) })
