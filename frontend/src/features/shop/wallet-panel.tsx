import { useCallback, useState } from 'react'

import { Button, ErrorNote, Input } from '../../components/ui'
import { searchDirectory } from '../../lib/api/public'
import { listPayees, type Payee } from '../../lib/api/rules'
import type { Shop } from '../../lib/api/shops'
import { listSuppliers, pauseShop, requestFreeze, requestRulesChange, resumeShop } from '../../lib/api/wallet'
import { parsePercentToBps } from '../../lib/money'
import { useLoad } from '../../lib/use-load'
import { useOwnerSignature, type SignPhase } from './use-owner-signature'

type Row = { label: string; address: string; share: string }

function SignStatus({ phase, error }: { phase: SignPhase; error: string | null }) {
  if (phase === 'signing') return <p className="text-sm text-muted">Waiting for your passkey…</p>
  if (phase === 'waiting') return <p className="text-sm text-muted">Signed. Waiting for NEAR to confirm…</p>
  if (phase === 'done') return <p className="text-sm text-ok">Done: the wallet holds the new state.</p>
  return error ? <ErrorNote>{error}</ErrorNote> : null
}

/** New payees, cap and allowed suppliers, signed into the wallet's policy as one change. */
function RulesChange({ shop, onShop }: { shop: Shop; onShop: (s: Shop) => void }) {
  const fetcher = useCallback(
    () =>
      Promise.all([listPayees(shop.id), listSuppliers(shop.id), searchDirectory('')]).then(([payees, suppliers, shops]) => ({
        payees,
        suppliers,
        shops: shops.filter((s) => s.slug !== shop.slug),
      })),
    [shop.id, shop.slug],
  )
  const { state } = useLoad(fetcher)
  const { phase, error, sign, busy } = useOwnerSignature(shop.id, onShop)
  const [rows, setRows] = useState<Row[] | null>(null)
  const [cap, setCap] = useState(shop.daily_budget_usd)
  const [chosen, setChosen] = useState<Set<string> | null>(null)
  const [invalid, setInvalid] = useState<string | null>(null)

  if (state.kind === 'loading') return <p className="text-sm text-muted">Loading the current rules…</p>
  if (state.kind === 'failed') return <ErrorNote>{state.message}</ErrorNote>
  const current = rows ?? state.data.payees.map((p) => ({ label: p.label, address: p.address, share: String(p.share_bps / 100) }))
  const allowed = chosen ?? new Set(state.data.suppliers.map((s) => s.id))
  const update = (i: number, change: Partial<Row>) => setRows(current.map((r, j) => (j === i ? { ...r, ...change } : r)))

  async function submit() {
    const payees: Payee[] = []
    for (const r of current) {
      const bps = parsePercentToBps(r.share)
      if (!r.label.trim() || !r.address.trim() || bps === null) return setInvalid('Each payee needs a name, a NEAR account and a share.')
      payees.push({ label: r.label.trim(), route: 'transfer', chain: null, address: r.address.trim().toLowerCase(), memo: null, share_bps: bps })
    }
    setInvalid(null)
    await sign(() =>
      requestRulesChange(shop.id, { payees, daily_budget_usd: cap.replace(/[$,\s]/g, ''), supplier_shop_ids: [...allowed] }),
    )
  }

  return (
    <div className="space-y-3">
      {current.map((row, i) => (
        <div key={i} className="grid grid-cols-[1fr_1.4fr_5rem_auto] items-center gap-2">
          <Input aria-label="Name" placeholder="Name" value={row.label} onChange={(e) => update(i, { label: e.target.value })} />
          <Input aria-label="NEAR account" placeholder="you.near" value={row.address} onChange={(e) => update(i, { address: e.target.value })} />
          <Input aria-label="Share (%)" placeholder="%" value={row.share} onChange={(e) => update(i, { share: e.target.value })} />
          <button className="text-sm text-muted underline" onClick={() => setRows(current.filter((_, j) => j !== i))}>
            Remove
          </button>
        </div>
      ))}
      <Button variant="quiet" onClick={() => setRows([...current, { label: '', address: '', share: '' }])}>
        Add payee
      </Button>
      <div className="flex items-center gap-2 text-sm">
        Daily cap $<div className="w-28"><Input value={cap} onChange={(e) => setCap(e.target.value)} /></div>
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium">Allowed suppliers</p>
        <p className="text-xs text-muted">Your agent can pay these shops from the wallet, and no others.</p>
        {state.data.shops.length === 0 && <p className="text-xs text-muted">No other live shops yet.</p>}
        {state.data.shops.map((s) => (
          <label key={s.id} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={allowed.has(s.id)}
              onChange={(e) => {
                const next = new Set(allowed)
                if (e.target.checked) next.add(s.id)
                else next.delete(s.id)
                setChosen(next)
              }}
            />
            {s.name}
          </label>
        ))}
      </div>
      {invalid && <ErrorNote>{invalid}</ErrorNote>}
      <SignStatus phase={phase} error={error} />
      <Button disabled={busy} onClick={submit}>
        Sign the new rules
      </Button>
    </div>
  )
}

/** The kill switch and the rules of a live shop's wallet. */
export function WalletPanel({ shop, onShop }: { shop: Shop; onShop: (s: Shop) => void }) {
  const freeze = useOwnerSignature(shop.id, onShop)
  const [changing, setChanging] = useState(false)
  const [pausing, setPausing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (shop.status === 'draft') return null

  async function toggleSelling() {
    setPausing(true)
    setError(null)
    try {
      onShop(await (shop.status === 'live' ? pauseShop(shop.id) : resumeShop(shop.id)))
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Not changed.')
    } finally {
      setPausing(false)
    }
  }

  return (
    <section className="space-y-4 rounded-2xl border border-line bg-card p-5">
      <h2 className="font-display text-xl">Wallet controls</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2 rounded-xl border border-line p-4">
          <p className="font-medium">{shop.status === 'paused' ? 'Selling is paused' : 'Selling'}</p>
          <p className="text-xs text-muted">Pausing stops new invoices and payments at once. The wallet is untouched.</p>
          <Button variant="quiet" disabled={pausing} onClick={toggleSelling}>
            {shop.status === 'paused' ? 'Resume selling' : 'Pause selling'}
          </Button>
        </div>
        <div className="space-y-2 rounded-xl border border-line p-4">
          <p className="font-medium">{shop.frozen ? 'Wallet frozen' : 'Wallet active'}</p>
          <p className="text-xs text-muted">Freezing stops every money action, payouts and purchases included, until you unfreeze it.</p>
          <Button variant="quiet" disabled={freeze.busy} onClick={() => freeze.sign(() => requestFreeze(shop.id, !shop.frozen))}>
            {shop.frozen ? 'Unfreeze (sign)' : 'Freeze (sign)'}
          </Button>
          <SignStatus phase={freeze.phase} error={freeze.error} />
        </div>
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}
      <div className="space-y-2">
        <Button variant="quiet" onClick={() => setChanging((v) => !v)}>
          {changing ? 'Close' : 'Change payees, cap or suppliers'}
        </Button>
        {changing && <RulesChange shop={shop} onShop={onShop} />}
      </div>
    </section>
  )
}
