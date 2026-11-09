import { apiFetch } from './client'
import type { OfferDelivery, OfferKind } from './offers'

/** Mirrors the backend's public schemas: what anyone can see without signing in. */

export type PublicOffer = {
  id: string
  title: string
  description: string
  kind: OfferKind
  price_cents: number
  delivery: OfferDelivery
}

export type PayOption = { asset_id: string; symbol: string; chain: string }

export type PublicShop = {
  slug: string
  name: string
  tagline: string
  description: string
  website: string | null
  selling: boolean
  wallet_account_id: string | null
  offers: PublicOffer[]
  pay_options: PayOption[]
}

export type InvoiceStatus = 'open' | 'awaiting_payment' | 'paid' | 'delivered' | 'expired' | 'refunded' | 'failed'

export type PublicInvoice = {
  number: string
  public_token: string
  shop_slug: string
  shop_name: string
  title: string
  quantity: number
  unit_price_cents: number
  total_cents: number
  status: InvoiceStatus
  buyer_name: string | null
  payment: {
    asset_id: string
    symbol: string | null
    chain: string | null
    amount: string
    address: string | null
    memo: string | null
    expires_at: string | null
  } | null
  payment_tx_url: string | null
  refund_tx_hash: string | null
  failure_code: string | null
  delivery: { url: string | null; note: string; deliverable: string | null } | null
  created_at: string
  paid_at: string | null
  delivered_at: string | null
}

export type LedgerKind = 'sale' | 'fee' | 'payout' | 'refund'

export type LedgerLine = {
  kind: LedgerKind
  status: 'pending' | 'done' | 'failed'
  amount_usd: string | null
  counterparty: string | null
  invoice_number: string | null
  tx_url: string | null
  failure_code: string | null
  created_at: string
  settled_at: string | null
}

export const getPublicShop = (slug: string) => apiFetch<PublicShop>(`/public/shops/${slug}`)

export const issueInvoice = (slug: string, body: { offer_id: string; quantity: number; buyer_email: string; buyer_name?: string }) =>
  apiFetch<PublicInvoice>(`/public/shops/${slug}/invoices`, { method: 'POST', body: JSON.stringify(body) })

export const getInvoice = (token: string) => apiFetch<PublicInvoice>(`/public/invoices/${token}`)

export const payInvoice = (token: string, payAsset: string) =>
  apiFetch<PublicInvoice>(`/public/invoices/${token}/pay`, { method: 'POST', body: JSON.stringify({ pay_asset: payAsset }) })

export const getPublicLedger = (slug: string) => apiFetch<LedgerLine[]>(`/public/shops/${slug}/ledger`)
