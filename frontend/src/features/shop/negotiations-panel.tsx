import { useCallback } from 'react'

import { Button, ErrorNote } from '../../components/ui'
import { listNegotiations, type Negotiation, type NegotiationStatus } from '../../lib/api/negotiations'
import { formatUsd } from '../../lib/money'
import { useLoad } from '../../lib/use-load'

const STATUS: Record<NegotiationStatus, string> = {
  open: 'Open',
  agreed: 'Agreed',
  walked_away: 'No deal',
  invoiced: 'Invoiced',
}

function MoveLine({ move }: { move: Negotiation['moves'][number] }) {
  const who = move.side === 'buyer' ? 'Buyer' : 'Your agent'
  const what = { offer: 'offered', counter: 'countered', accept: 'accepted', walk_away: 'walked away' }[move.move]
  return (
    <li className={`rounded-lg px-3 py-2 text-sm ${move.side === 'seller' ? 'bg-accent-soft' : 'bg-paper'}`}>
      <span className="font-medium">
        {who} {what}
        {move.unit_price_cents !== null && ` ${formatUsd(move.unit_price_cents)}`}
      </span>
      {move.message && <span className="text-muted"> — “{move.message}”</span>}
    </li>
  )
}

/** Every negotiation over this shop's offers, with each move and the reason given. */
export function NegotiationsPanel({ shopId }: { shopId: string }) {
  const fetcher = useCallback(() => listNegotiations(shopId), [shopId])
  const { state, reload } = useLoad(fetcher)

  return (
    <section className="space-y-3 rounded-2xl border border-line bg-card p-5">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-xl">Negotiations</h2>
        <Button variant="quiet" onClick={reload}>
          Refresh
        </Button>
      </div>
      {state.kind === 'loading' && <p className="text-sm text-muted">Loading…</p>}
      {state.kind === 'failed' && <ErrorNote>{state.message}</ErrorNote>}
      {state.kind === 'ready' && state.data.length === 0 && (
        <p className="text-sm text-muted">No one has bargained yet. Agents negotiate through the MCP address on your shop page.</p>
      )}
      {state.kind === 'ready' && (
        <ul className="space-y-4">
          {state.data.map((n) => (
            <li key={n.id} className="space-y-2">
              <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
                <p>
                  <span className="font-medium">{n.buyer_name}</span> · {n.offer_title} × {n.quantity}
                </p>
                <p className="text-muted">
                  {STATUS[n.status]}
                  {n.agreed_unit_cents !== null && ` at ${formatUsd(n.agreed_unit_cents)}`} · list {formatUsd(n.list_price_cents)}, lowest{' '}
                  {formatUsd(n.floor_cents)}
                </p>
              </div>
              <ul className="space-y-1">
                {n.moves.map((m, i) => (
                  <MoveLine key={i} move={m} />
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
