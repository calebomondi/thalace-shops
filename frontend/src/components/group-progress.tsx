import type { GroupOrder } from '../lib/api/group-orders'
import { isSimulated } from '../lib/api/group-orders'
import { formatUsd } from '../lib/money'

/** How far a group order has come: the price now, the tiers, and what's needed for the next. */
export function GroupProgress({ group }: { group: GroupOrder }) {
  const top = group.tiers[group.tiers.length - 1]
  const goal = Math.max(top.min_quantity, group.committed_quantity)
  const simulated = group.members.filter((m) => isSimulated(m.buyer_name)).length
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-display text-2xl">
          {formatUsd(group.unit_price_cents)}
          <span className="text-sm text-muted"> each now · list {formatUsd(group.list_price_cents)}</span>
        </p>
        <p className="text-sm text-muted">
          {group.committed_quantity} committed by {group.members.length} buyers
          {simulated > 0 && ` (${simulated} simulated)`}
        </p>
      </div>
      <div className="relative h-2 rounded-full bg-paper">
        <div className="h-2 rounded-full bg-accent" style={{ width: `${Math.min(100, (group.committed_quantity / goal) * 100)}%` }} />
        {group.tiers.slice(1).map((t) => (
          <span key={t.min_quantity} className="absolute top-[-3px] h-3.5 w-0.5 bg-ink/40" style={{ left: `${(t.min_quantity / goal) * 100}%` }} />
        ))}
      </div>
      <div className="flex flex-wrap gap-2 text-xs">
        {group.tiers.map((t) => (
          <span
            key={t.min_quantity}
            className={`rounded-full border px-2 py-0.5 ${group.committed_quantity >= t.min_quantity ? 'border-ok/30 bg-ok-soft text-ok' : 'border-line text-muted'}`}
          >
            {t.min_quantity}+ at {formatUsd(t.unit_price_cents)}
          </span>
        ))}
      </div>
      {group.next_tier && (
        <p className="text-sm">
          {group.next_tier.min_quantity - group.committed_quantity} more and everyone pays {formatUsd(group.next_tier.unit_price_cents)}.
        </p>
      )}
    </div>
  )
}
