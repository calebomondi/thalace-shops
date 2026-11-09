import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router'

import { ErrorNote } from '../../components/ui'
import { getShop, type Shop } from '../../lib/api/shops'
import { useLoad } from '../../lib/use-load'
import { AgentChat } from './agent-chat'
import { GoLivePanel } from './go-live-panel'
import { OffersPanel } from './offers-panel'
import { RulesPanel } from './rules-panel'

function ShopView({ shop, onShopChange }: { shop: Shop; onShopChange: (s: Shop) => void }) {
  // Bumped after each agent turn: the offers panel reloads what the agent drafted.
  const [offersVersion, setOffersVersion] = useState(0)

  return (
    <div className="space-y-6">
      <div>
        <Link to="/" className="text-sm text-muted underline">
          ← Your shops
        </Link>
        <div className="mt-2 flex flex-wrap items-baseline gap-3">
          <h1 className="font-display text-3xl">{shop.name}</h1>
          <span className="rounded-full border border-line px-2.5 py-0.5 text-xs text-muted">
            {shop.status === 'draft' ? 'Draft · not selling yet' : shop.status}
          </span>
        </div>
        <p className="mt-1 font-mono text-xs text-muted">/s/{shop.slug}</p>
        {shop.tagline && <p className="mt-2 text-muted">{shop.tagline}</p>}
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_26rem]">
        <div className="min-w-0 space-y-6">
          <OffersPanel key={offersVersion} shopId={shop.id} />
          <RulesPanel shop={shop} onShopChange={onShopChange} />
          <GoLivePanel shop={shop} onShop={onShopChange} />
        </div>
        <div className="lg:sticky lg:top-6 lg:self-start">
          <AgentChat shopId={shop.id} onTurn={() => setOffersVersion((v) => v + 1)} />
        </div>
      </div>
    </div>
  )
}

export function ShopPage() {
  const { shopId = '' } = useParams()
  const fetcher = useCallback(() => getShop(shopId), [shopId])
  const { state, replace } = useLoad(fetcher)

  if (state.kind === 'loading') return <p className="text-muted">Loading the shop…</p>
  if (state.kind === 'failed') {
    return (
      <div className="space-y-3">
        <ErrorNote>{state.message}</ErrorNote>
        <Link to="/" className="text-sm text-accent underline">
          Back to your shops
        </Link>
      </div>
    )
  }
  return <ShopView shop={state.data} onShopChange={(s) => replace(() => s)} />
}
