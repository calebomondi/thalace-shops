import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'

import { Button, ErrorNote } from '../../components/ui'
import { getConversation, sendMessage, type ChatMessage } from '../../lib/api/chat'
import { useLoad } from '../../lib/use-load'

// What each of the agent's tools did, as the owner reads it.
const actionText: Record<string, string> = {
  shop_overview: 'Checked the shop',
  list_offers: 'Looked at the offers',
  read_website: 'Read a web page',
  draft_offer: 'Drafted an offer',
  update_draft_offer: 'Rewrote a draft',
  sales_summary: 'Checked sales',
  find_suppliers: 'Looked for suppliers',
  buy_from_supplier: 'Bought from a supplier',
  list_group_orders: 'Looked at group orders',
  join_group_order: 'Joined a group order',
}

function Actions({ actions }: { actions: string[] }) {
  const counted = new Map<string, number>()
  for (const a of actions) counted.set(a, (counted.get(a) ?? 0) + 1)
  if (counted.size === 0) return null
  return (
    <div className="mb-2 flex flex-wrap gap-1.5">
      {[...counted].map(([name, n]) => (
        <span key={name} className="rounded-full bg-accent-soft px-2 py-0.5 text-xs text-accent">
          {actionText[name] ?? name}
          {n > 1 && ` ×${n}`}
        </span>
      ))}
    </div>
  )
}

function Bubble({ message }: { message: ChatMessage }) {
  if (message.role === 'user') {
    return <div className="ml-8 self-end rounded-2xl rounded-br-sm bg-accent px-4 py-2.5 text-sm text-accent-ink">{message.content}</div>
  }
  return (
    <div className="mr-8 self-start rounded-2xl rounded-bl-sm border border-line bg-paper px-4 py-3 text-sm">
      <Actions actions={message.actions} />
      <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
    </div>
  )
}

const STARTERS = ['Read my website and draft offers for buyers paying online', 'What does my shop need before it can go live?']

/** The owner's conversation with the shop's agent. `onTurn` runs after each
 * answer, so the page can refresh what the agent may have changed. */
export function AgentChat({ shopId, onTurn }: { shopId: string; onTurn: () => void }) {
  const fetcher = useCallback(() => getConversation(shopId), [shopId])
  const { state, replace } = useLoad(fetcher)
  const [text, setText] = useState('')
  const [pending, setPending] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const end = useRef<HTMLDivElement>(null)

  const count = state.kind === 'ready' ? state.data.length : 0
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [count, pending])

  async function send(message: string) {
    if (!message.trim() || pending) return
    setPending(message.trim())
    setText('')
    setError(null)
    try {
      const turn = await sendMessage(shopId, message.trim())
      replace((messages) => [...messages, ...turn])
      onTurn()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Your agent didn’t answer.')
      setText(message)
    } finally {
      setPending(null)
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    void send(text)
  }

  return (
    <section className="flex h-[70svh] min-h-96 flex-col rounded-2xl border border-line bg-card">
      <header className="border-b border-line px-5 py-3">
        <h2 className="font-display text-xl">Your shop’s agent</h2>
        <p className="text-xs text-muted">It drafts offers; you decide what goes on sale.</p>
      </header>
      <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-5 py-4">
        {state.kind === 'loading' && <p className="text-sm text-muted">Loading the conversation…</p>}
        {state.kind === 'failed' && <ErrorNote>{state.message}</ErrorNote>}
        {state.kind === 'ready' && state.data.length === 0 && !pending && (
          <div className="m-auto space-y-2 text-center">
            <p className="text-sm text-muted">Ask your agent to get the shop ready.</p>
            {STARTERS.map((s) => (
              <button key={s} className="block w-full rounded-lg border border-line px-3 py-2 text-sm hover:bg-paper" onClick={() => send(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        {state.kind === 'ready' && state.data.map((m) => <Bubble key={m.id} message={m} />)}
        {pending && (
          <>
            <div className="ml-8 self-end rounded-2xl rounded-br-sm bg-accent px-4 py-2.5 text-sm text-accent-ink">{pending}</div>
            <p className="self-start text-sm text-muted">Your agent is working on it… this can take a minute.</p>
          </>
        )}
        <div ref={end} />
      </div>
      {error && (
        <div className="px-5 pb-2">
          <ErrorNote>{error}</ErrorNote>
        </div>
      )}
      <form onSubmit={submit} className="flex gap-2 border-t border-line p-3">
        <input
          className="min-w-0 flex-1 rounded-lg border border-line bg-paper px-3 py-2.5 text-sm outline-none focus:border-accent"
          placeholder="Ask your agent…"
          maxLength={4000}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <Button type="submit" disabled={!text.trim() || Boolean(pending)}>
          Send
        </Button>
      </form>
    </section>
  )
}
