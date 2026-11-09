import { useCallback } from 'react'
import { Link, useParams } from 'react-router'

import { GroupProgress } from '../../components/group-progress'
import { ErrorNote } from '../../components/ui'
import { getMembership } from '../../lib/api/group-orders'
import { useLoad } from '../../lib/use-load'

/** A buyer's own place in a group order: the progress, then their invoice once it closes. */
export function MembershipPage() {
  const { token = '' } = useParams()
  const fetcher = useCallback(() => getMembership(token), [token])
  const { state } = useLoad(fetcher)

  if (state.kind === 'loading') return <p className="p-8 text-muted">Loading…</p>
  if (state.kind === 'failed') {
    return (
      <main className="mx-auto max-w-xl px-4 py-10">
        <ErrorNote>{state.message}</ErrorNote>
      </main>
    )
  }
  const { group_order: group, invoice_token: invoice } = state.data
  return (
    <main className="mx-auto max-w-xl space-y-6 px-4 py-10">
      <div>
        <p className="text-xs uppercase tracking-wide text-muted">Your group order</p>
        <h1 className="font-display text-3xl">{group.offer_title}</h1>
        <Link to={`/s/${group.shop_slug}`} className="text-sm text-muted underline">
          {group.shop_name}
        </Link>
      </div>
      <section className="rounded-2xl border border-line bg-card p-5">
        <GroupProgress group={group} />
      </section>
      {group.status === 'open' && (
        <p className="text-sm text-muted">
          You’re in. At {new Date(group.deadline).toLocaleString()} the price locks and your invoice appears here. Keep this
          page’s link.
        </p>
      )}
      {group.status === 'closed' && invoice && (
        <Link to={`/i/${invoice}`} className="inline-block rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-accent-ink">
          Pay your invoice
        </Link>
      )}
      {group.status === 'cancelled' && <ErrorNote>This group order was cancelled. Nobody was charged.</ErrorNote>}
    </main>
  )
}
