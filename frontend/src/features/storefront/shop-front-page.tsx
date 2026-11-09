import { useCallback, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { AgentConnect } from '../../components/agent-connect'
import { Button, ErrorNote, Field, Input } from '../../components/ui'
import { getPublicShop, issueInvoice, type PublicOffer, type PublicShop } from '../../lib/api/public'
import { formatUsd } from '../../lib/money'
import { useLoad } from '../../lib/use-load'

function BuyForm({ shop, offer, onCancel }: { shop: PublicShop; offer: PublicOffer; onCancel: () => void }) {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [quantity, setQuantity] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const invoice = await issueInvoice(shop.slug, {
        offer_id: offer.id,
        quantity,
        buyer_email: email.trim(),
        buyer_name: name.trim() || undefined,
      })
      navigate(`/i/${invoice.public_token}`)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'The invoice could not be made.')
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="mt-4 space-y-3 rounded-xl bg-paper p-4">
      <div className="grid gap-3 sm:grid-cols-[1fr_1fr_6rem]">
        <Field label="Email" hint="Your invoice and receipt.">
          <Input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Name (optional)">
          <Input autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Quantity">
          <Input
            type="number"
            min={1}
            max={100}
            value={quantity}
            onChange={(e) => setQuantity(Math.max(1, Number(e.target.value) || 1))}
          />
        </Field>
      </div>
      <p className="text-sm text-muted">Total {formatUsd(offer.price_cents * quantity)}, paid in a dollar stablecoin from any chain.</p>
      {error && <ErrorNote>{error}</ErrorNote>}
      <div className="flex gap-2">
        <Button type="submit" disabled={saving}>
          {saving ? 'Making your invoice…' : 'Get invoice'}
        </Button>
        <Button type="button" variant="quiet" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

function OfferCard({ shop, offer }: { shop: PublicShop; offer: PublicOffer }) {
  const [buying, setBuying] = useState(false)
  return (
    <li className="rounded-2xl border border-line bg-card p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-display text-lg leading-snug">{offer.title}</h3>
          <p className="text-sm text-muted">{offer.kind === 'digital' ? 'Digital' : 'Service'}</p>
        </div>
        <p className="font-display text-xl">{formatUsd(offer.price_cents)}</p>
      </div>
      {offer.description && <p className="mt-2 text-sm leading-relaxed text-muted">{offer.description}</p>}
      {shop.selling && !buying && (
        <Button className="mt-4" onClick={() => setBuying(true)}>
          Buy
        </Button>
      )}
      {buying && <BuyForm shop={shop} offer={offer} onCancel={() => setBuying(false)} />}
    </li>
  )
}

/** A live shop's public page. Anyone can buy here; no account needed. */
export function ShopFrontPage() {
  const { slug = '' } = useParams()
  const fetcher = useCallback(() => getPublicShop(slug), [slug])
  const { state } = useLoad(fetcher)

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      {state.kind === 'loading' && <p className="text-muted">Loading the shop…</p>}
      {state.kind === 'failed' && <ErrorNote>{state.message}</ErrorNote>}
      {state.kind === 'ready' && (
        <div className="space-y-8">
          <header className="space-y-2">
            <p className="font-display text-sm text-accent">A shop on Thalace</p>
            <h1 className="font-display text-4xl">{state.data.name}</h1>
            {state.data.tagline && <p className="text-lg text-muted">{state.data.tagline}</p>}
            {state.data.description && <p className="leading-relaxed">{state.data.description}</p>}
            {!state.data.selling && <ErrorNote>This shop isn’t taking orders right now.</ErrorNote>}
          </header>
          {state.data.offers.length === 0 ? (
            <p className="text-muted">Nothing on sale yet.</p>
          ) : (
            <ul className="space-y-4">
              {state.data.offers.map((offer) => (
                <OfferCard key={offer.id} shop={state.data} offer={offer} />
              ))}
            </ul>
          )}
          {state.data.selling && <AgentConnect compact />}
          <footer className="flex flex-wrap gap-x-4 gap-y-1 border-t border-line pt-4 text-xs text-muted">
            <span>Payments settle to the shop’s own wallet on NEAR Intents.</span>
            <Link to={`/s/${state.data.slug}/ledger`} className="underline">
              Public ledger
            </Link>
            <Link to="/directory" className="underline">
              More shops
            </Link>
          </footer>
        </div>
      )}
    </main>
  )
}
