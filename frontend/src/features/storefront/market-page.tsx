import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'

import { GroupProgress } from '../../components/group-progress'
import { Button, ErrorNote, Field, Input } from '../../components/ui'
import { getMarket, joinGroupOrder, type GroupOrder } from '../../lib/api/group-orders'
import { useLoad } from '../../lib/use-load'

// The market updates itself this often while open.
const REFRESH_MS = 10_000

function timeLeft(deadline: string, now: number): string {
  const left = new Date(deadline).getTime() - now
  if (left <= 0) return 'closing now'
  const h = Math.floor(left / 3_600_000)
  const m = Math.floor((left % 3_600_000) / 60_000)
  return h > 0 ? `${h}h ${m}m left` : `${m}m left`
}

function JoinForm({ group }: { group: GroupOrder }) {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [quantity, setQuantity] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const membership = await joinGroupOrder(group.group_order_id, { quantity, buyer_name: name.trim(), buyer_email: email.trim() })
      navigate(`/m/${membership.member_token}`)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Not joined.')
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="mt-3 grid gap-3 rounded-xl bg-paper p-4 sm:grid-cols-[1fr_1fr_5rem_auto] sm:items-end">
      <Field label="Name">
        <Input required value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Email">
        <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Field label="Qty">
        <Input type="number" min={1} max={100} value={quantity} onChange={(e) => setQuantity(Math.max(1, Number(e.target.value) || 1))} />
      </Field>
      <Button type="submit" disabled={saving}>
        {saving ? 'Joining…' : 'Join'}
      </Button>
      {error && (
        <div className="sm:col-span-4">
          <ErrorNote>{error}</ErrorNote>
        </div>
      )}
    </form>
  )
}

function GroupCard({ group, now }: { group: GroupOrder; now: number }) {
  const [joining, setJoining] = useState(false)
  const open = group.status === 'open'
  return (
    <li className="space-y-3 rounded-2xl border border-line bg-card p-5 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="font-display text-lg">{group.offer_title}</p>
          <Link to={`/s/${group.shop_slug}`} className="text-sm text-muted underline">
            {group.shop_name}
          </Link>
        </div>
        <p className="text-sm text-muted">
          {open ? timeLeft(group.deadline, now) : group.status === 'closed' ? `Closed at ${group.committed_quantity}` : 'Cancelled'}
        </p>
      </div>
      <GroupProgress group={group} />
      {open && !joining && <Button onClick={() => setJoining(true)}>Join this order</Button>}
      {open && joining && <JoinForm group={group} />}
    </li>
  )
}

/** Group orders across all shops: buyers pooling demand for a volume price (docs/RULES.md). */
export function MarketPage() {
  const fetcher = useCallback(() => getMarket(), [])
  const { state, replace } = useLoad(fetcher)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const timer = setInterval(() => {
      setNow(Date.now())
      getMarket().then((fresh) => replace(() => fresh), () => undefined)
    }, REFRESH_MS)
    return () => clearInterval(timer)
  }, [replace])

  const groups = state.kind === 'ready' ? state.data : []
  const open = groups.filter((g) => g.status === 'open')
  const closed = groups.filter((g) => g.status !== 'open')

  return (
    <main className="mx-auto max-w-3xl space-y-8 px-4 py-10">
      <header className="space-y-2">
        <Link to="/directory" className="text-sm text-muted underline">
          ← Directory
        </Link>
        <h1 className="font-display text-4xl">Buying together</h1>
        <p className="text-muted">
          Buyers (people, their agents and other shops) pool orders to reach a volume price. At the deadline the price
          locks at the tier reached and each buyer gets their own invoice. Nobody pays before then.
        </p>
      </header>
      {state.kind === 'loading' && <p className="text-muted">Loading the market…</p>}
      {state.kind === 'failed' && <ErrorNote>{state.message}</ErrorNote>}
      {state.kind === 'ready' && open.length === 0 && <p className="text-muted">No group orders open right now.</p>}
      <ul className="space-y-4">
        {open.map((g) => (
          <GroupCard key={g.group_order_id} group={g} now={now} />
        ))}
      </ul>
      {closed.length > 0 && (
        <section className="space-y-3">
          <h2 className="font-display text-xl">Recently closed</h2>
          <ul className="space-y-4">
            {closed.map((g) => (
              <GroupCard key={g.group_order_id} group={g} now={now} />
            ))}
          </ul>
        </section>
      )}
    </main>
  )
}
