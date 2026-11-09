import { accessToken } from '../supabase'
import { apiFetch } from './client'
import type { OfferDelivery } from './offers'
import type { InvoiceStatus, LedgerLine } from './public'

/** Mirrors the backend's OwnerInvoiceOut. */
export type OwnerInvoice = {
  id: string
  number: string
  public_token: string
  title: string
  quantity: number
  total_cents: number
  fee_bps: number
  status: InvoiceStatus
  buyer_kind: 'person' | 'agent' | 'shop'
  buyer_email: string | null
  buyer_name: string | null
  delivery: OfferDelivery
  deliverable: string | null
  created_at: string
  paid_at: string | null
  delivered_at: string | null
}

export const listInvoices = (shopId: string) => apiFetch<OwnerInvoice[]>(`/shops/${shopId}/invoices`)

export const deliverInvoice = (shopId: string, invoiceId: string, deliverable: string) =>
  apiFetch<OwnerInvoice>(`/shops/${shopId}/invoices/${invoiceId}/deliver`, {
    method: 'POST',
    body: JSON.stringify({ deliverable: deliverable || null }),
  })

export const getLedger = (shopId: string) => apiFetch<LedgerLine[]>(`/shops/${shopId}/ledger`)

/** The CSV needs the owner's token, so it's fetched and saved, not linked. */
export async function downloadLedgerCsv(shopId: string, slug: string): Promise<void> {
  const token = await accessToken()
  const response = await fetch(`/api/v1/shops/${shopId}/ledger.csv`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) throw new Error('The ledger could not be downloaded.')
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = `${slug}-ledger.csv`
  link.click()
  URL.revokeObjectURL(url)
}
