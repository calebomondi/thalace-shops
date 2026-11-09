import { useCallback, useState } from 'react'

import {
  addPasskey,
  getPasskeyStatus,
  getSignature,
  requestSignature,
  submitSignature,
  type ShopSignatureType,
  type SignatureState,
} from '../../lib/api/signing'
import type { Shop } from '../../lib/api/shops'
import { createOwnerPasskey, passkeyError, signWithPasskey } from './passkey'

/** Where going live stands, for the button and the line under it. */
export type GoLivePhase = 'idle' | 'passkey' | 'signing' | 'waiting' | 'live' | 'failed'

export const SIGNATURE_LABEL: Record<ShopSignatureType, string> = {
  agent_create: 'Opening the shop’s wallet under your rules',
  grant_issue: 'Letting your shop’s agent act inside those rules',
  policy_update: 'Changing the rules',
  agent_freeze: 'Freezing the wallet',
  agent_unfreeze: 'Unfreezing the wallet',
}

// A submitted request usually settles in seconds; NEAR can take longer.
const POLL_EVERY_MS = 3_000
const POLL_FOR_MS = 120_000

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

async function settled(shopId: string, first: SignatureState): Promise<SignatureState> {
  let current = first
  const deadline = Date.now() + POLL_FOR_MS
  while (current.status === 'submitted' && Date.now() < deadline) {
    await wait(POLL_EVERY_MS)
    current = await getSignature(shopId, current.correlation_id)
  }
  return current
}

/** Take a shop live: make the founder's passkey for this site if there isn't
 * one, then sign each request NEAR Intents needs (opening the wallet, then
 * letting the agent act) and wait for it to settle. */
export function useGoLive(shop: Shop, who: { email: string; name: string }, onShop: (shop: Shop) => void) {
  const [phase, setPhase] = useState<GoLivePhase>(shop.status === 'live' ? 'live' : 'idle')
  const [step, setStep] = useState<ShopSignatureType | null>(null)
  const [summary, setSummary] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const start = useCallback(async () => {
    setError(null)
    try {
      if (!(await getPasskeyStatus()).has_passkey) {
        setPhase('passkey')
        await addPasskey(await createOwnerPasskey(who))
      }
      let current = shop
      while (current.status !== 'live') {
        setPhase('signing')
        const request = await requestSignature(shop.id)
        setStep(request.type)
        setSummary(request.preview.summary ?? null)
        const signed = await signWithPasskey(request)
        setPhase('waiting')
        const done = await settled(shop.id, await submitSignature(shop.id, request.correlation_id, signed))
        if (done.status === 'submitted') throw new Error('NEAR is taking longer than usual. Check back in a few minutes.')
        if (done.status !== 'succeeded') throw new Error(`NEAR Intents didn’t accept it (${done.failure_code ?? done.status}).`)
        current = done.shop
        onShop(current)
      }
      setPhase('live')
      setStep(null)
      setSummary(null)
    } catch (failure) {
      setError(passkeyError(failure))
      setPhase('failed')
    }
  }, [shop, who, onShop])

  return { phase, step, summary, error, start }
}
