import { apiFetch } from './client'

export type NegotiationStatus = 'open' | 'agreed' | 'walked_away' | 'invoiced'

/** Mirrors the backend's NegotiationOut: the owner's view, floor included. */
export type Negotiation = {
  id: string
  offer_title: string
  list_price_cents: number
  floor_cents: number
  buyer_kind: 'person' | 'agent' | 'shop'
  buyer_name: string
  quantity: number
  status: NegotiationStatus
  agreed_unit_cents: number | null
  moves: {
    side: 'buyer' | 'seller'
    move: 'offer' | 'counter' | 'accept' | 'walk_away'
    unit_price_cents: number | null
    message: string
    created_at: string
  }[]
  created_at: string
}

export const listNegotiations = (shopId: string) => apiFetch<Negotiation[]>(`/shops/${shopId}/negotiations`)
