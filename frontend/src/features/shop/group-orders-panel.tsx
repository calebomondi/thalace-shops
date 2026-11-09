import { useCallback } from 'react'

import { GroupProgress } from '../../components/group-progress'
import { Button, ErrorNote } from '../../components/ui'
import { isSimulated, listShopGroupOrders } from '../../lib/api/group-orders'
import { useLoad } from '../../lib/use-load'

/** This shop's group orders: who joined, the price reached, and each member's invoice. */
export function GroupOrdersPanel({ shopId }: { shopId: string }) {
  const fetcher = useCallback(() => listShopGroupOrders(shopId), [shopId])
  const { state, reload } = useLoad(fetcher)

  if (state.kind === 'ready' && state.data.length === 0) return null
  return (
    <section className="space-y-3 rounded-2xl border border-line bg-card p-5">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-xl">Group orders</h2>
        <Button variant="quiet" onClick={reload}>
          Refresh
        </Button>
      </div>
      {state.kind === 'loading' && <p className="text-sm text-muted">Loading…</p>}
      {state.kind === 'failed' && <ErrorNote>{state.message}</ErrorNote>}
      {state.kind === 'ready' && (
        <ul className="space-y-4">
          {state.data.map((g) => (
            <li key={g.group_order_id} className="space-y-2 rounded-xl border border-line p-4">
              <p className="text-sm">
                <span className="font-medium">{g.offer_title}</span> · {g.status} · deadline {new Date(g.deadline).toLocaleString()}
              </p>
              <GroupProgress group={g} />
              <ul className="text-xs text-muted">
                {g.members.map((m, i) => (
                  <li key={i}>
                    {m.buyer_name} ({m.buyer_kind}
                    {isSimulated(m.buyer_name) && ', simulated'}) × {m.quantity}
                    {m.invoice_token && (
                      <>
                        {' · '}
                        <a className="text-accent underline" href={`/i/${m.invoice_token}`} target="_blank" rel="noreferrer">
                          invoice
                        </a>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
