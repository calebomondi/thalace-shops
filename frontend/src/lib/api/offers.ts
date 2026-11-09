import { apiFetch } from './client'

export type OfferKind = 'digital' | 'service'
export type OfferDelivery = 'link' | 'markdown' | 'service'
export type OfferStatus = 'draft' | 'active' | 'archived'

/** Mirrors the backend's OfferOut. */
export type Offer = {
  id: string
  title: string
  description: string
  kind: OfferKind
  price_cents: number
  floor_cents: number
  delivery: OfferDelivery
  delivery_url: string | null
  delivery_note: string
  status: OfferStatus
  drafted_by_agent: boolean
  created_at: string
}

export type OfferCreate = {
  title: string
  description?: string
  kind: OfferKind
  price_cents: number
  floor_cents?: number
  delivery: OfferDelivery
  delivery_url?: string
  delivery_note?: string
}

export type OfferUpdate = Partial<Omit<OfferCreate, 'floor_cents'>> & { floor_cents?: number; status?: OfferStatus }

export const listOffers = (shopId: string) => apiFetch<Offer[]>(`/shops/${shopId}/offers`)

export const createOffer = (shopId: string, body: OfferCreate) =>
  apiFetch<Offer>(`/shops/${shopId}/offers`, { method: 'POST', body: JSON.stringify(body) })

export const updateOffer = (shopId: string, offerId: string, body: OfferUpdate) =>
  apiFetch<Offer>(`/shops/${shopId}/offers/${offerId}`, { method: 'PATCH', body: JSON.stringify(body) })
