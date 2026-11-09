import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'

import { InvoiceStatusBadge } from '../../components/invoice-status'
import { Button, ErrorNote } from '../../components/ui'
import { getInvoice, getPublicShop, payInvoice, type PayOption, type PublicInvoice } from '../../lib/api/public'
import { formatUsd } from '../../lib/money'
import { useLoad } from '../../lib/use-load'
import { PaymentBox } from './payment-box'

// While a payment is awaited the page asks again this often.
const POLL_MS = 5_000
const PAYABLE = new Set(['open', 'expired', 'failed'])

function CoinPicker({ invoice, onQuoted }: { invoice: PublicInvoice; onQuoted: (i: PublicInvoice) => void }) {
  const fetcher = useCallback(() => getPublicShop(invoice.shop_slug), [invoice.shop_slug])
  const { state } = useLoad(fetcher)
  const [choice, setChoice] = useState<PayOption | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function pay() {
    if (!choice) return
    setBusy(true)
    setError(null)
    try {
      onQuoted(await payInvoice(invoice.public_token, choice.asset_id))
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'The payment address could not be made.')
    } finally {
      setBusy(false)
    }
  }

  if (state.kind === 'loading') return <p className="text-sm text-muted">Loading the coins this shop takes…</p>
  if (state.kind === 'failed') return <ErrorNote>{state.message}</ErrorNote>
  return (
    <div className="space-y-3">
      <p className="text-sm font-medium">Pay with</p>
      <div className="flex flex-wrap gap-2">
        {state.data.pay_options.map((option) => (
          <button
            key={option.asset_id}
            onClick={() => setChoice(option)}
            className={`rounded-lg border px-3 py-2 text-sm ${choice?.asset_id === option.asset_id ? 'border-accent bg-accent-soft text-accent' : 'border-line bg-card hover:bg-paper'}`}
          >
            {option.symbol} · <span className="capitalize">{option.chain}</span>
          </button>
        ))}
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}
      <Button disabled={!choice || busy} onClick={pay}>
        {busy ? 'Getting the address…' : choice ? `Pay ${formatUsd(invoice.total_cents)} in ${choice.symbol}` : 'Choose a coin'}
      </Button>
    </div>
  )
}

function Delivery({ invoice }: { invoice: PublicInvoice }) {
  const delivery = invoice.delivery
  if (!delivery) return null
  return (
    <section className="space-y-3 rounded-2xl border border-ok/30 bg-ok-soft p-5">
      <h2 className="font-display text-xl text-ok">{invoice.status === 'delivered' ? 'Here’s what you bought' : 'Payment received'}</h2>
      {delivery.url && (
        <a className="block break-all text-accent underline" href={delivery.url} target="_blank" rel="noreferrer">
          {delivery.url}
        </a>
      )}
      {delivery.deliverable && <div className="whitespace-pre-wrap rounded-xl bg-card p-4 text-sm leading-relaxed">{delivery.deliverable}</div>}
      {invoice.status === 'paid' && !delivery.url && (
        <p className="text-sm">{delivery.note || `${invoice.shop_name} will deliver this shortly. Keep this page: it updates when they do.`}</p>
      )}
      {invoice.payment_tx_url && (
        <a className="text-xs text-muted underline" href={invoice.payment_tx_url} target="_blank" rel="noreferrer">
          See the payment on NEAR
        </a>
      )}
    </section>
  )
}

/** An invoice, by its unguessable link: what was bought, how to pay, and what
 * happened. The buyer needs no account. */
export function InvoicePage() {
  const { token = '' } = useParams()
  const fetcher = useCallback(() => getInvoice(token), [token])
  const { state, replace } = useLoad(fetcher)
  const status = state.kind === 'ready' ? state.data.status : null

  useEffect(() => {
    if (status !== 'awaiting_payment') return
    const timer = setInterval(() => {
      getInvoice(token).then((fresh) => replace(() => fresh), () => undefined)
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [status, token, replace])

  if (state.kind === 'loading') return <p className="p-8 text-muted">Loading the invoice…</p>
  if (state.kind === 'failed') {
    return (
      <main className="mx-auto max-w-xl px-4 py-10">
        <ErrorNote>{state.message}</ErrorNote>
      </main>
    )
  }
  const invoice = state.data
  return (
    <main className="mx-auto max-w-xl space-y-6 px-4 py-10">
      <section className="space-y-4 rounded-2xl border border-line bg-card p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted">Invoice {invoice.number}</p>
            <Link to={`/s/${invoice.shop_slug}`} className="font-display text-2xl">
              {invoice.shop_name}
            </Link>
          </div>
          <InvoiceStatusBadge status={invoice.status} />
        </div>
        <table className="w-full text-sm">
          <tbody>
            <tr className="border-b border-line">
              <td className="py-2">
                {invoice.title}
                {invoice.quantity > 1 && <span className="text-muted"> × {invoice.quantity}</span>}
              </td>
              <td className="py-2 text-right">{formatUsd(invoice.unit_price_cents * invoice.quantity)}</td>
            </tr>
            <tr>
              <td className="py-2 font-medium">Total</td>
              <td className="py-2 text-right font-display text-lg">{formatUsd(invoice.total_cents)}</td>
            </tr>
          </tbody>
        </table>
        <p className="text-xs text-muted">
          Issued {new Date(invoice.created_at).toLocaleString()}
          {invoice.buyer_name && ` to ${invoice.buyer_name}`}
          {invoice.paid_at && ` · paid ${new Date(invoice.paid_at).toLocaleString()}`}
        </p>
      </section>

      {invoice.status === 'awaiting_payment' && invoice.payment && <PaymentBox payment={invoice.payment} />}
      {PAYABLE.has(invoice.status) && (
        <section className="space-y-3 rounded-2xl border border-line bg-card p-5">
          {invoice.status === 'expired' && <p className="text-sm text-muted">The last quote ran out before a payment arrived. Get a new one below.</p>}
          {invoice.status === 'failed' && <p className="text-sm text-muted">The payment address couldn’t be made. Try again, or pick another coin.</p>}
          <CoinPicker invoice={invoice} onQuoted={(fresh) => replace(() => fresh)} />
        </section>
      )}
      {invoice.status === 'refunded' && (
        <ErrorNote>
          A payment arrived but couldn’t be credited as sent (a different amount, coin or a late payment). NEAR Intents
          returned it to {invoice.shop_name}’s wallet. Write to the shop and they can settle it with you.
        </ErrorNote>
      )}
      <Delivery invoice={invoice} />
    </main>
  )
}
