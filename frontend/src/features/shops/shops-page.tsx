import { useState } from 'react'

import { Button, ErrorNote } from '../../components/ui'
import type { Shop, ShopStatus } from '../../lib/api/shops'
import { CreateShopForm } from './create-shop-form'
import { useShops } from './use-shops'

const statusLabel: Record<ShopStatus, { text: string; style: string }> = {
  draft: { text: 'Draft · not selling yet', style: 'bg-paper text-muted border-line' },
  live: { text: 'Live', style: 'bg-ok-soft text-ok border-ok/30' },
  paused: { text: 'Paused', style: 'bg-accent-soft text-accent border-accent/30' },
}

function ShopCard({ shop }: { shop: Shop }) {
  const status = statusLabel[shop.status]
  return (
    <li className="flex flex-col gap-3 rounded-2xl border border-line bg-card p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-display text-lg leading-snug">{shop.name}</h3>
        <span className={`shrink-0 rounded-full border px-2.5 py-0.5 text-xs ${status.style}`}>{status.text}</span>
      </div>
      {shop.tagline && <p className="text-sm text-muted">{shop.tagline}</p>}
      <p className="mt-auto font-mono text-xs text-muted">/s/{shop.slug}</p>
    </li>
  )
}

export function ShopsPage() {
  const { state, reload, add } = useShops()
  const [creating, setCreating] = useState(false)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl">Your shops</h1>
          <p className="mt-1 text-muted">Each shop has its own agent, wallet and rules.</p>
        </div>
        {!creating && <Button onClick={() => setCreating(true)}>New shop</Button>}
      </div>

      {creating && (
        <CreateShopForm
          onCancel={() => setCreating(false)}
          onCreate={async (body) => {
            await add(body)
            setCreating(false)
          }}
        />
      )}

      {state.kind === 'loading' && <p className="text-muted">Loading your shops…</p>}
      {state.kind === 'failed' && (
        <div className="space-y-3">
          <ErrorNote>{state.message}</ErrorNote>
          <Button variant="quiet" onClick={reload}>
            Try again
          </Button>
        </div>
      )}
      {state.kind === 'ready' && state.shops.length === 0 && !creating && (
        <div className="rounded-2xl border border-dashed border-line p-10 text-center">
          <p className="font-medium">No shops yet</p>
          <p className="mt-1 text-sm text-muted">Start with one: you can run several, one for each line of business.</p>
        </div>
      )}
      {state.kind === 'ready' && state.shops.length > 0 && (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {state.shops.map((shop) => (
            <ShopCard key={shop.id} shop={shop} />
          ))}
        </ul>
      )}
    </div>
  )
}
