import { useCallback } from 'react'
import { Link, useParams } from 'react-router'

import { LedgerTable } from '../../components/ledger-table'
import { ErrorNote } from '../../components/ui'
import { getPublicLedger } from '../../lib/api/public'
import { useLoad } from '../../lib/use-load'

/** Every sale, fee and payout of a shop, for anyone to check. Buyers aren't named. */
export function PublicLedgerPage() {
  const { slug = '' } = useParams()
  const fetcher = useCallback(() => getPublicLedger(slug), [slug])
  const { state } = useLoad(fetcher)

  return (
    <main className="mx-auto max-w-3xl space-y-6 px-4 py-10">
      <div>
        <Link to={`/s/${slug}`} className="text-sm text-muted underline">
          ← Back to the shop
        </Link>
        <h1 className="mt-2 font-display text-3xl">Public ledger</h1>
        <p className="mt-1 text-muted">Every sale, platform fee and payout, as it happened on NEAR.</p>
      </div>
      {state.kind === 'loading' && <p className="text-muted">Loading the ledger…</p>}
      {state.kind === 'failed' && <ErrorNote>{state.message}</ErrorNote>}
      {state.kind === 'ready' && <LedgerTable lines={state.data} />}
    </main>
  )
}
