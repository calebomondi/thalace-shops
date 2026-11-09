import { useCallback, useState, type FormEvent } from 'react'

import { Button, ErrorNote, Field, Input, TextArea } from '../../components/ui'
import { createOffer, listOffers, updateOffer, type Offer, type OfferKind, type OfferStatus } from '../../lib/api/offers'
import { formatUsd, parseUsdToCents } from '../../lib/money'
import { useLoad } from '../../lib/use-load'
import { GroupBuyingEditor } from './group-buying-editor'

const statusStyle: Record<OfferStatus, string> = {
  draft: 'border-line bg-paper text-muted',
  active: 'border-ok/30 bg-ok-soft text-ok',
  archived: 'border-line bg-paper text-muted line-through',
}
const statusText: Record<OfferStatus, string> = { draft: 'Draft', active: 'On sale', archived: 'Archived' }

function PriceEditor({ offer, onSave }: { offer: Offer; onSave: (price: number, floor: number) => Promise<void> }) {
  const [price, setPrice] = useState((offer.price_cents / 100).toString())
  const [floor, setFloor] = useState((offer.floor_cents / 100).toString())
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    const p = parseUsdToCents(price)
    const f = parseUsdToCents(floor)
    if (p === null || f === null) return setError('Enter both prices in dollars, e.g. 15 or 15.50.')
    if (f > p) return setError('The lowest price can’t be above the list price.')
    setSaving(true)
    try {
      await onSave(p, f)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Not saved.')
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="mt-3 space-y-3 rounded-xl bg-paper p-3">
      <div className="grid grid-cols-2 gap-3">
        <Field label="List price ($)">
          <Input inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} />
        </Field>
        <Field label="Lowest price ($)" hint="Your agent never agrees below this.">
          <Input inputMode="decimal" value={floor} onChange={(e) => setFloor(e.target.value)} />
        </Field>
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}
      <Button type="submit" disabled={saving}>
        {saving ? 'Saving…' : 'Save prices'}
      </Button>
    </form>
  )
}

function OfferRow({ shopId, offer, onChange }: { shopId: string; offer: Offer; onChange: (o: Offer) => void }) {
  const [editing, setEditing] = useState(false)
  const [grouping, setGrouping] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function setStatus(status: OfferStatus) {
    setBusy(true)
    setError(null)
    try {
      onChange(await updateOffer(shopId, offer.id, { status }))
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Not changed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className="rounded-xl border border-line bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium">{offer.title}</p>
          <p className="text-sm text-muted">
            {formatUsd(offer.price_cents)}
            {offer.floor_cents < offer.price_cents && <> · lowest {formatUsd(offer.floor_cents)}</>} · {offer.kind}
            {offer.drafted_by_agent && <> · drafted by your agent</>}
          </p>
        </div>
        <span className={`rounded-full border px-2.5 py-0.5 text-xs ${statusStyle[offer.status]}`}>
          {statusText[offer.status]}
        </span>
      </div>
      {offer.description && <p className="mt-2 text-sm text-muted">{offer.description}</p>}
      <div className="mt-3 flex flex-wrap gap-2">
        {offer.status === 'draft' && (
          <Button disabled={busy} onClick={() => setStatus('active')}>
            Put on sale
          </Button>
        )}
        {offer.status === 'active' && (
          <Button variant="quiet" disabled={busy} onClick={() => setStatus('draft')}>
            Take off sale
          </Button>
        )}
        {offer.status !== 'archived' && (
          <>
            <Button variant="quiet" onClick={() => setEditing((v) => !v)}>
              {editing ? 'Close' : 'Edit prices'}
            </Button>
            <Button variant="quiet" onClick={() => setGrouping((v) => !v)}>
              {grouping ? 'Close' : offer.group_buy_enabled ? 'Group buying: on' : 'Group buying'}
            </Button>
            <Button variant="quiet" disabled={busy} onClick={() => setStatus('archived')}>
              Archive
            </Button>
          </>
        )}
      </div>
      {grouping && (
        <GroupBuyingEditor
          shopId={shopId}
          offer={offer}
          onSaved={(enabled) => {
            onChange({ ...offer, group_buy_enabled: enabled })
            setGrouping(false)
          }}
        />
      )}
      {editing && (
        <PriceEditor
          offer={offer}
          onSave={async (price_cents, floor_cents) => {
            onChange(await updateOffer(shopId, offer.id, { price_cents, floor_cents }))
            setEditing(false)
          }}
        />
      )}
      {error && (
        <div className="mt-3">
          <ErrorNote>{error}</ErrorNote>
        </div>
      )}
    </li>
  )
}

function AddOfferForm({ shopId, onAdded }: { shopId: string; onAdded: (o: Offer) => void }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [kind, setKind] = useState<OfferKind>('service')
  const [price, setPrice] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    const cents = parseUsdToCents(price)
    if (cents === null) return setError('Enter the price in dollars, e.g. 15 or 15.50.')
    setSaving(true)
    setError(null)
    try {
      // Owner-written offers are delivered by the team or as a written
      // deliverable; link offers need the private link, set when editing.
      onAdded(
        await createOffer(shopId, {
          title: title.trim(),
          description: description.trim(),
          kind,
          price_cents: cents,
          delivery: kind === 'digital' ? 'markdown' : 'service',
        }),
      )
      setTitle('')
      setDescription('')
      setPrice('')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Not added.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-xl border border-dashed border-line p-4">
      <p className="text-sm font-medium">Add an offer yourself</p>
      <Field label="Title">
        <Input required minLength={2} value={title} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <Field label="Description">
        <TextArea value={description} onChange={(e) => setDescription(e.target.value)} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Kind">
          <select
            className="w-full rounded-lg border border-line bg-card px-3 py-2.5 text-sm"
            value={kind}
            onChange={(e) => setKind(e.target.value as OfferKind)}
          >
            <option value="service">Service</option>
            <option value="digital">Digital</option>
          </select>
        </Field>
        <Field label="Price ($)">
          <Input required inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} />
        </Field>
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}
      <Button type="submit" disabled={saving}>
        {saving ? 'Adding…' : 'Add as draft'}
      </Button>
    </form>
  )
}

export function OffersPanel({ shopId }: { shopId: string }) {
  const fetcher = useCallback(() => listOffers(shopId), [shopId])
  const { state, reload, replace } = useLoad(fetcher)
  const [adding, setAdding] = useState(false)

  const upsert = (offer: Offer) =>
    replace((offers) => {
      if (offer.status === 'archived') return offers.filter((o) => o.id !== offer.id)
      if (offers.some((o) => o.id === offer.id)) return offers.map((o) => (o.id === offer.id ? offer : o))
      return [...offers, offer]
    })

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-display text-xl">Offers</h2>
        <div className="flex gap-2">
          <Button variant="quiet" onClick={reload}>
            Refresh
          </Button>
          <Button variant="quiet" onClick={() => setAdding((v) => !v)}>
            {adding ? 'Close' : 'Add offer'}
          </Button>
        </div>
      </div>
      {adding && <AddOfferForm shopId={shopId} onAdded={(o) => upsert(o)} />}
      {state.kind === 'loading' && <p className="text-sm text-muted">Loading offers…</p>}
      {state.kind === 'failed' && <ErrorNote>{state.message}</ErrorNote>}
      {state.kind === 'ready' && state.data.length === 0 && (
        <p className="rounded-xl border border-dashed border-line p-6 text-center text-sm text-muted">
          No offers yet. Ask your agent to draft some from your website, or add one yourself.
        </p>
      )}
      {state.kind === 'ready' && state.data.length > 0 && (
        <ul className="space-y-3">
          {state.data.map((offer) => (
            <OfferRow key={offer.id} shopId={shopId} offer={offer} onChange={upsert} />
          ))}
        </ul>
      )}
    </section>
  )
}
