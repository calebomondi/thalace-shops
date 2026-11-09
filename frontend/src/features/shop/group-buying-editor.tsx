import { useCallback, useState } from 'react'

import { Button, ErrorNote, Input } from '../../components/ui'
import { getGroupBuying, setGroupBuying, type Tier } from '../../lib/api/group-orders'
import type { Offer } from '../../lib/api/offers'
import { formatUsd, parseUsdToCents } from '../../lib/money'
import { useLoad } from '../../lib/use-load'

type Step = { quantity: string; price: string }

/** The seller's terms for group orders on one offer: on or off, the longest
 * window, and the volume tiers (each lower, never below the floor). */
export function GroupBuyingEditor({ shopId, offer, onSaved }: { shopId: string; offer: Offer; onSaved: (enabled: boolean) => void }) {
  const fetcher = useCallback(() => getGroupBuying(shopId, offer.id), [shopId, offer.id])
  const { state } = useLoad(fetcher)
  const [steps, setSteps] = useState<Step[] | null>(null)
  const [hours, setHours] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  if (state.kind === 'loading') return <p className="mt-3 text-sm text-muted">Loading…</p>
  if (state.kind === 'failed') return <ErrorNote>{state.message}</ErrorNote>
  const current =
    steps ?? state.data.tiers.filter((t) => t.min_quantity > 1).map((t) => ({ quantity: String(t.min_quantity), price: String(t.unit_price_cents / 100) }))
  const window = hours ?? String(state.data.window_hours)

  async function save(enabled: boolean) {
    const tiers: Tier[] = []
    for (const s of current) {
      const cents = parseUsdToCents(s.price)
      const quantity = Number(s.quantity)
      if (!cents || !Number.isInteger(quantity) || quantity < 2) return setError('Each tier needs 2 or more units and a price.')
      tiers.push({ min_quantity: quantity, unit_price_cents: cents })
    }
    setSaving(true)
    setError(null)
    try {
      const saved = await setGroupBuying(shopId, offer.id, { enabled, window_hours: Number(window) || 72, tiers })
      onSaved(saved.enabled)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Not saved.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mt-3 space-y-3 rounded-xl bg-paper p-3">
      <p className="text-sm">
        Buyers pool orders until a deadline; everyone pays the tier the total reaches. From 1 unit it’s {formatUsd(offer.price_cents)};
        tiers can go down to your lowest price, {formatUsd(offer.floor_cents)}.
      </p>
      {current.map((step, i) => (
        <div key={i} className="flex items-center gap-2 text-sm">
          From
          <div className="w-20">
            <Input inputMode="numeric" value={step.quantity} onChange={(e) => setSteps(current.map((s, j) => (j === i ? { ...s, quantity: e.target.value } : s)))} />
          </div>
          units, $
          <div className="w-24">
            <Input inputMode="decimal" value={step.price} onChange={(e) => setSteps(current.map((s, j) => (j === i ? { ...s, price: e.target.value } : s)))} />
          </div>
          each
          <button className="text-muted underline" onClick={() => setSteps(current.filter((_, j) => j !== i))}>
            Remove
          </button>
        </div>
      ))}
      <Button variant="quiet" onClick={() => setSteps([...current, { quantity: '', price: '' }])}>
        Add tier
      </Button>
      <div className="flex items-center gap-2 text-sm">
        Longest window
        <div className="w-20">
          <Input inputMode="numeric" value={window} onChange={(e) => setHours(e.target.value)} />
        </div>
        hours
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}
      <div className="flex gap-2">
        <Button disabled={saving} onClick={() => save(true)}>
          {state.data.enabled ? 'Save' : 'Turn group buying on'}
        </Button>
        {state.data.enabled && (
          <Button variant="quiet" disabled={saving} onClick={() => save(false)}>
            Turn off
          </Button>
        )}
      </div>
    </div>
  )
}
