import { useMemo } from 'react'

import { Button, ErrorNote } from '../../components/ui'
import type { Shop } from '../../lib/api/shops'
import { useAuth } from '../../lib/auth-context'
import { SIGNATURE_LABEL, useGoLive } from './use-go-live'

/** The owner's last step: sign the shop live with their passkey. */
export function GoLivePanel({ shop, onShop }: { shop: Shop; onShop: (shop: Shop) => void }) {
  const { session } = useAuth()
  const who = useMemo(() => {
    const email = session?.user.email ?? 'owner'
    const name = (session?.user.user_metadata?.full_name as string | undefined) ?? email
    return { email, name }
  }, [session])
  const { phase, step, summary, error, start } = useGoLive(shop, who, onShop)
  const busy = phase === 'passkey' || phase === 'signing' || phase === 'waiting'

  if (shop.status === 'live') {
    return (
      <section className="space-y-2 rounded-2xl border border-ok/30 bg-ok-soft p-5">
        <h2 className="font-display text-xl text-ok">Live</h2>
        <p className="text-sm">
          The shop has its own wallet on NEAR Intents, holding the rules you signed. Its agent acts inside them.
        </p>
        {shop.wallet_account_id && (
          <p className="break-all font-mono text-xs text-muted">Wallet: {shop.wallet_account_id}</p>
        )}
      </section>
    )
  }

  return (
    <section className="space-y-3 rounded-2xl border border-accent/30 bg-accent-soft p-5">
      <h2 className="font-display text-xl">Go live</h2>
      <p className="text-sm">
        You sign twice with a passkey on this device: once to open the shop’s wallet under the rules above, once to let
        its agent act inside them. Your passkey signs for all your shops on this site.
      </p>
      <p className="text-xs text-muted">
        Keep this passkey: if it’s lost, nobody (not you, not Thalace) can change this shop’s rules or move its money
        again.
      </p>
      {shop.wallet_open && <p className="text-sm">The wallet is open. One more signature and the shop is live.</p>}
      {busy && (
        <p className="text-sm">
          {phase === 'passkey' && 'Making your passkey…'}
          {phase !== 'passkey' && step && SIGNATURE_LABEL[step]}
          {phase === 'waiting' && ' — waiting for NEAR…'}
          {summary && phase === 'signing' && <span className="block text-xs text-muted">{summary}</span>}
        </p>
      )}
      {error && <ErrorNote>{error}</ErrorNote>}
      <Button onClick={start} disabled={busy}>
        {busy ? 'Working…' : shop.wallet_open ? 'Finish going live' : 'Sign and go live'}
      </Button>
    </section>
  )
}
