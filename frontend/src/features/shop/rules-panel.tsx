import { useCallback, useState } from 'react'

import { Button, ErrorNote, Input } from '../../components/ui'
import { getPlatformTerms, listPayees, replacePayees, setDailyBudget, type Payee, type PlatformTerms } from '../../lib/api/rules'
import type { Shop } from '../../lib/api/shops'
import { parsePercentToBps, percent } from '../../lib/money'
import { useLoad } from '../../lib/use-load'

type Row = { label: string; address: string; share: string }

const FULL_BPS = 10_000

function toRows(payees: Payee[]): Row[] {
  return payees.map((p) => ({ label: p.label, address: p.address, share: (p.share_bps / 100).toString() }))
}

/** The revenue split as the owner edits it: NEAR accounts and percentages of
 * what's left after the platform fee. Withdraw payees (other chains) come later. */
function PayeesEditor({ shopId, initial, editable, terms }: {
  shopId: string
  initial: Payee[]
  editable: boolean
  terms: PlatformTerms
}) {
  const [rows, setRows] = useState<Row[]>(toRows(initial))
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  const shares = rows.map((r) => parsePercentToBps(r.share) ?? 0)
  const total = shares.reduce((a, b) => a + b, 0)
  const kept = Math.max(FULL_BPS - total, 0)

  const update = (i: number, change: Partial<Row>) => {
    setSaved(false)
    setRows((current) => current.map((r, j) => (j === i ? { ...r, ...change } : r)))
  }

  async function save() {
    const payees: Payee[] = []
    for (const r of rows) {
      const bps = parsePercentToBps(r.share)
      if (!r.label.trim() || !r.address.trim() || bps === null) {
        return setError('Each payee needs a name, a NEAR account and a share between 0 and 100%.')
      }
      payees.push({ label: r.label.trim(), route: 'transfer', chain: null, address: r.address.trim().toLowerCase(), memo: null, share_bps: bps })
    }
    setSaving(true)
    setError(null)
    try {
      setRows(toRows(await replacePayees(shopId, payees)))
      setSaved(true)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Not saved.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">
        From each sale, Thalace takes {percent(terms.fee_bps)} (never more than {percent(terms.max_fee_bps)}), paid to{' '}
        <span className="font-mono text-ink">{terms.fee_account}</span>. The payees below split the rest; what nobody
        takes stays in the shop’s wallet.
      </p>
      {rows.length === 0 && <p className="text-sm text-muted">No payees yet: everything stays in the shop’s wallet.</p>}
      {rows.map((row, i) => (
        <div key={i} className="grid grid-cols-[1fr_1.4fr_5rem_auto] items-center gap-2">
          <Input aria-label="Name" placeholder="Name" disabled={!editable} value={row.label} onChange={(e) => update(i, { label: e.target.value })} />
          <Input aria-label="NEAR account" placeholder="you.near" disabled={!editable} value={row.address} onChange={(e) => update(i, { address: e.target.value })} />
          <Input aria-label="Share (%)" inputMode="decimal" placeholder="%" disabled={!editable} value={row.share} onChange={(e) => update(i, { share: e.target.value })} />
          {editable && (
            <button className="text-sm text-muted underline" onClick={() => setRows((c) => c.filter((_, j) => j !== i))}>
              Remove
            </button>
          )}
        </div>
      ))}
      <p className={`text-sm ${total > FULL_BPS ? 'text-danger' : 'text-muted'}`}>
        Payees {percent(total)} · stays in the shop {percent(kept)}
      </p>
      {error && <ErrorNote>{error}</ErrorNote>}
      {editable && (
        <div className="flex flex-wrap gap-2">
          <Button variant="quiet" onClick={() => setRows((c) => [...c, { label: '', address: '', share: '' }])}>
            Add payee
          </Button>
          <Button disabled={saving || total > FULL_BPS} onClick={save}>
            {saving ? 'Saving…' : saved ? 'Saved' : 'Save payees'}
          </Button>
        </div>
      )}
    </div>
  )
}

function BudgetEditor({ shop, editable, onSaved }: { shop: Shop; editable: boolean; onSaved: (s: Shop) => void }) {
  const [value, setValue] = useState(shop.daily_budget_usd)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function save() {
    setSaving(true)
    setError(null)
    try {
      onSaved(await setDailyBudget(shop.id, value.replace(/[$,\s]/g, '')))
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Not saved.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-2">
      <p className="text-sm text-muted">
        The most the shop may send out in a day: payee shares, the fee and anything it buys. The wallet itself refuses
        more.
      </p>
      <div className="flex items-center gap-2">
        <span className="text-muted">$</span>
        <div className="w-32">
          <Input inputMode="decimal" disabled={!editable} value={value} onChange={(e) => setValue(e.target.value)} />
        </div>
        {editable && (
          <Button variant="quiet" disabled={saving || value === shop.daily_budget_usd} onClick={save}>
            {saving ? 'Saving…' : 'Save cap'}
          </Button>
        )}
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}
    </div>
  )
}

export function RulesPanel({ shop, onShopChange }: { shop: Shop; onShopChange: (s: Shop) => void }) {
  const fetcher = useCallback(
    () => Promise.all([listPayees(shop.id), getPlatformTerms()]).then(([payees, terms]) => ({ payees, terms })),
    [shop.id],
  )
  const { state } = useLoad(fetcher)
  const editable = shop.status === 'draft'

  return (
    <section className="space-y-4 rounded-2xl border border-line bg-card p-5">
      <div>
        <h2 className="font-display text-xl">Money rules</h2>
        <p className="mt-1 text-sm text-muted">
          {editable
            ? 'You sign these when the shop goes live. After that your agent can’t change them, and neither can we.'
            : 'These are in the shop’s signed wallet policy. Changing them needs your signature again.'}
        </p>
      </div>
      <BudgetEditor shop={shop} editable={editable} onSaved={onShopChange} />
      <hr className="border-line" />
      {state.kind === 'loading' && <p className="text-sm text-muted">Loading payees…</p>}
      {state.kind === 'failed' && <ErrorNote>{state.message}</ErrorNote>}
      {state.kind === 'ready' && (
        <PayeesEditor shopId={shop.id} initial={state.data.payees} editable={editable} terms={state.data.terms} />
      )}
    </section>
  )
}
