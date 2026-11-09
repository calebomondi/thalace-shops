import { useCallback, useState } from 'react'

import { getSignature, submitSignature, type PendingSignature, type SignatureState } from '../../lib/api/signing'
import type { Shop } from '../../lib/api/shops'
import { passkeyError, signWithPasskey } from './passkey'

// A submitted change usually settles in seconds; NEAR can take longer.
const POLL_EVERY_MS = 3_000
const POLL_FOR_MS = 120_000

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

export type SignPhase = 'idle' | 'signing' | 'waiting' | 'done' | 'failed'

/** Sign one change to a live wallet (freeze, unfreeze, new rules) with the
 * founder's passkey, then wait for NEAR Intents to confirm it. */
export function useOwnerSignature(shopId: string, onShop: (shop: Shop) => void) {
  const [phase, setPhase] = useState<SignPhase>('idle')
  const [error, setError] = useState<string | null>(null)

  const sign = useCallback(
    async (request: () => Promise<PendingSignature>) => {
      setError(null)
      try {
        setPhase('signing')
        const pending = await request()
        const signed = await signWithPasskey(pending)
        setPhase('waiting')
        let state: SignatureState = await submitSignature(shopId, pending.correlation_id, signed)
        const deadline = Date.now() + POLL_FOR_MS
        while (state.status === 'submitted' && Date.now() < deadline) {
          await wait(POLL_EVERY_MS)
          state = await getSignature(shopId, pending.correlation_id)
        }
        if (state.status === 'submitted') throw new Error('NEAR is taking longer than usual. Check back in a few minutes.')
        if (state.status !== 'succeeded') throw new Error(`NEAR Intents didn’t accept it (${state.failure_code ?? state.status}).`)
        onShop(state.shop)
        setPhase('done')
      } catch (failure) {
        setError(passkeyError(failure))
        setPhase('failed')
      }
    },
    [shopId, onShop],
  )

  return { phase, error, sign, busy: phase === 'signing' || phase === 'waiting' }
}
