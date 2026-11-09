import { useCallback, useState } from 'react'
import { Link } from 'react-router'

import { InvoiceStatusBadge } from '../../components/invoice-status'
import { LedgerTable } from '../../components/ledger-table'
import { Button, ErrorNote, TextArea } from '../../components/ui'
import { deliverInvoice, downloadLedgerCsv, getLedger, listInvoices, type OwnerInvoice } from '../../lib/api/invoices'
import type { Shop } from '../../lib/api/shops'
import { formatUsd } from '../../lib/money'
import { useLoad } from '../../lib/use-load'

function DeliverForm({ shopId, invoice, onDone }: { shopId: string; invoice: OwnerInvoice; onDone: (i: OwnerInvoice) => void }) {
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function deliver() {
    setSaving(true)
    setError(null)
    try {
      onDone(await deliverInvoice(shopId, invoice.id, text.trim()))
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Not delivered.')
      setSaving(false)
    }
  }

  return (
    <div className="mt-3 space-y-2">
      {invoice.delivery === 'markdown' && (
        <TextArea placeholder="The written deliverable the buyer will see on their invoice" value={text} onChange={(e) => setText(e.target.value)} />
      )}
      {error && <ErrorNote>{error}</ErrorNote>}
      <Button disabled={saving || (invoice.delivery === 'markdown' && !text.trim())} onClick={deliver}>
        {saving ? 'Saving…' : invoice.delivery === 'markdown' ? 'Deliver' : 'Mark delivered'}
      </Button>
    </div>
  )
}

function Invoices({ shop }: { shop: Shop }) {
  const fetcher = useCallback(() => listInvoices(shop.id), [shop.id])
  const { state, reload, replace } = useLoad(fetcher)
  const [open, setOpen] = useState<string | null>(null)

  if (state.kind === 'loading') return <p className="text-sm text-muted">Loading invoices…</p>
  if (state.kind === 'failed') return <ErrorNote>{state.message}</ErrorNote>
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-medium">Invoices</h3>
        <Button variant="quiet" onClick={reload}>
          Refresh
        </Button>
      </div>
      {state.data.length === 0 && <p className="text-sm text-muted">No invoices yet. Share your shop page to get the first.</p>}
      <ul className="space-y-2">
        {state.data.map((invoice) => (
          <li key={invoice.id} className="rounded-xl border border-line p-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0 text-sm">
                <p>
                  <span className="font-mono text-xs text-muted">{invoice.number}</span> {invoice.title}
                  {invoice.quantity > 1 && ` × ${invoice.quantity}`} · {formatUsd(invoice.total_cents)}
                </p>
                <p className="truncate text-xs text-muted">
                  {invoice.buyer_name ?? invoice.buyer_email ?? invoice.buyer_kind} · {new Date(invoice.created_at).toLocaleString()}
                </p>
              </div>
              <InvoiceStatusBadge status={invoice.status} />
            </div>
            <div className="mt-2 flex flex-wrap gap-3 text-xs">
              <a className="text-accent underline" href={`/i/${invoice.public_token}`} target="_blank" rel="noreferrer">
                Buyer’s view
              </a>
              {invoice.status === 'paid' && invoice.delivery !== 'link' && (
                <button className="text-accent underline" onClick={() => setOpen(open === invoice.id ? null : invoice.id)}>
                  {open === invoice.id ? 'Close' : 'Deliver'}
                </button>
              )}
            </div>
            {open === invoice.id && (
              <DeliverForm
                shopId={shop.id}
                invoice={invoice}
                onDone={(done) => {
                  replace((list) => list.map((i) => (i.id === done.id ? done : i)))
                  setOpen(null)
                }}
              />
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Ledger({ shop }: { shop: Shop }) {
  const fetcher = useCallback(() => getLedger(shop.id), [shop.id])
  const { state, reload } = useLoad(fetcher)
  const [error, setError] = useState<string | null>(null)

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-medium">Ledger</h3>
        <div className="flex gap-2">
          <Button variant="quiet" onClick={reload}>
            Refresh
          </Button>
          <Button
            variant="quiet"
            onClick={() => downloadLedgerCsv(shop.id, shop.slug).catch((e: unknown) => setError(e instanceof Error ? e.message : 'Not downloaded.'))}
          >
            Download CSV
          </Button>
        </div>
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}
      {state.kind === 'loading' && <p className="text-sm text-muted">Loading the ledger…</p>}
      {state.kind === 'failed' && <ErrorNote>{state.message}</ErrorNote>}
      {state.kind === 'ready' && <LedgerTable lines={state.data} />}
    </div>
  )
}

/** Once live: what the shop sold, what it delivered, and where the money went. */
export function SalesPanel({ shop }: { shop: Shop }) {
  if (shop.status === 'draft') return null
  return (
    <section className="space-y-5 rounded-2xl border border-line bg-card p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-xl">Sales</h2>
        <div className="flex gap-3 text-sm">
          <Link className="text-accent underline" to={`/s/${shop.slug}`} target="_blank">
            Shop page
          </Link>
          <Link className="text-accent underline" to={`/s/${shop.slug}/ledger`} target="_blank">
            Public ledger
          </Link>
        </div>
      </div>
      <Invoices shop={shop} />
      <hr className="border-line" />
      <Ledger shop={shop} />
    </section>
  )
}
