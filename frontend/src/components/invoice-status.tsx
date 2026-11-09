import type { InvoiceStatus } from '../lib/api/public'

const LABEL: Record<InvoiceStatus, { text: string; style: string }> = {
  open: { text: 'Unpaid', style: 'border-line bg-paper text-muted' },
  awaiting_payment: { text: 'Waiting for payment', style: 'border-accent/30 bg-accent-soft text-accent' },
  paid: { text: 'Paid', style: 'border-ok/30 bg-ok-soft text-ok' },
  delivered: { text: 'Paid · delivered', style: 'border-ok/30 bg-ok-soft text-ok' },
  expired: { text: 'Quote expired', style: 'border-line bg-paper text-muted' },
  refunded: { text: 'Refunded to shop', style: 'border-danger/30 bg-danger/5 text-danger' },
  failed: { text: 'Not paid', style: 'border-danger/30 bg-danger/5 text-danger' },
}

export function InvoiceStatusBadge({ status }: { status: InvoiceStatus }) {
  const { text, style } = LABEL[status]
  return <span className={`shrink-0 rounded-full border px-2.5 py-0.5 text-xs ${style}`}>{text}</span>
}
