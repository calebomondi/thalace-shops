import { apiFetch } from './client'

export type Tier = { min_quantity: number; unit_price_cents: number }

/** Mirrors the backend's GroupOrderOut. */
export type GroupOrder = {
  group_order_id: string
  shop_slug: string
  shop_name: string
  offer_id: string
  offer_title: string
  status: 'open' | 'closed' | 'cancelled'
  opened_by: string
  deadline: string
  committed_quantity: number
  unit_price_cents: number
  list_price_cents: number
  next_tier: Tier | null
  tiers: Tier[]
  members: { buyer_kind: 'person' | 'agent' | 'shop'; buyer_name: string; quantity: number; invoice_token: string | null }[]
  closed_at: string | null
}

export type Membership = { member_token: string; group_order: GroupOrder; invoice_token: string | null }

export type GroupBuying = { enabled: boolean; window_hours: number; tiers: Tier[] }

export const getMarket = () => apiFetch<GroupOrder[]>('/public/market')

export const getMembership = (token: string) => apiFetch<Membership>(`/public/memberships/${token}`)

export const openGroupOrder = (body: { offer_id: string; quantity: number; hours: number; buyer_name: string; buyer_email: string }) =>
  apiFetch<Membership>('/public/group-orders', { method: 'POST', body: JSON.stringify(body) })

export const joinGroupOrder = (groupId: string, body: { quantity: number; buyer_name: string; buyer_email: string }) =>
  apiFetch<Membership>(`/public/group-orders/${groupId}/join`, { method: 'POST', body: JSON.stringify(body) })

export const getGroupBuying = (shopId: string, offerId: string) =>
  apiFetch<GroupBuying>(`/shops/${shopId}/offers/${offerId}/group-buying`)

export const setGroupBuying = (shopId: string, offerId: string, body: GroupBuying) =>
  apiFetch<GroupBuying>(`/shops/${shopId}/offers/${offerId}/group-buying`, {
    method: 'PUT',
    body: JSON.stringify({ ...body, tiers: body.tiers.filter((t) => t.min_quantity > 1) }),
  })

export const listShopGroupOrders = (shopId: string) => apiFetch<GroupOrder[]>(`/shops/${shopId}/group-orders`)

/** Simulated buyers (scripts/simulate_market.py) are named "Sim buyer N". */
export const isSimulated = (name: string) => /^Sim buyer \d+$/.test(name)
