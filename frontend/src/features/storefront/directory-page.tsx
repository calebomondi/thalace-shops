import { useCallback, useState, type FormEvent } from 'react'
import { Link } from 'react-router'

import { AgentConnect } from '../../components/agent-connect'
import { Button, ErrorNote, Input } from '../../components/ui'
import { searchDirectory } from '../../lib/api/public'
import { formatUsd } from '../../lib/money'
import { useLoad } from '../../lib/use-load'

/** Every live shop and what it sells, for people and their agents. */
export function DirectoryPage() {
  const [query, setQuery] = useState('')
  const [submitted, setSubmitted] = useState('')
  const fetcher = useCallback(() => searchDirectory(submitted), [submitted])
  const { state } = useLoad(fetcher)

  function submit(event: FormEvent) {
    event.preventDefault()
    setSubmitted(query.trim())
  }

  return (
    <main className="mx-auto max-w-4xl space-y-8 px-4 py-10">
      <header className="space-y-2">
        <p className="font-display text-sm text-accent">Thalace Shops</p>
        <h1 className="font-display text-4xl">Shops run by their own agents</h1>
        <p className="text-muted">
          Real businesses, paid in dollar stablecoins from any chain, settled on NEAR.{' '}
          <Link to="/market" className="text-accent underline">
            See what people are buying together
          </Link>
        </p>
      </header>
      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <section className="min-w-0 space-y-4">
          <form onSubmit={submit} className="flex gap-2">
            <Input placeholder="Search: CAD design, engraving, 3D printing…" value={query} onChange={(e) => setQuery(e.target.value)} />
            <Button type="submit">Search</Button>
          </form>
          {state.kind === 'loading' && <p className="text-muted">Searching…</p>}
          {state.kind === 'failed' && <ErrorNote>{state.message}</ErrorNote>}
          {state.kind === 'ready' && state.data.length === 0 && <p className="text-muted">No live shops match that yet.</p>}
          {state.kind === 'ready' && (
            <ul className="space-y-4">
              {state.data.map((shop) => (
                <li key={shop.slug} className="rounded-2xl border border-line bg-card p-5 shadow-sm">
                  <Link to={`/s/${shop.slug}`} className="font-display text-xl hover:text-accent">
                    {shop.name}
                  </Link>
                  {shop.tagline && <p className="text-sm text-muted">{shop.tagline}</p>}
                  <ul className="mt-3 space-y-1 text-sm">
                    {shop.offers.slice(0, 5).map((offer) => (
                      <li key={offer.id} className="flex justify-between gap-3">
                        <span className="truncate">{offer.title}</span>
                        <span className="shrink-0 tabular-nums">{formatUsd(offer.price_cents)}</span>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </section>
        <aside className="lg:sticky lg:top-6 lg:self-start">
          <AgentConnect />
        </aside>
      </div>
    </main>
  )
}
