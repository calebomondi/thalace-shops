import {
  startAuthentication,
  startRegistration,
  type PublicKeyCredentialRequestOptionsJSON,
} from '@simplewebauthn/browser'

import type { PasskeyOwner, PendingSignature } from '../../lib/api/signing'

/** ES256: the only key type a shop's wallet accepts. */
const ES256 = -7

function randomBase64Url(bytes: number): string {
  const raw = crypto.getRandomValues(new Uint8Array(bytes))
  return btoa(String.fromCharCode(...raw)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** Make the founder's passkey on this device, for this site. Nothing is
 * verified here: the passkey proves itself later, when NEAR Intents checks
 * each signature against the public key returned now. */
export async function createOwnerPasskey(who: { email: string; name: string }): Promise<PasskeyOwner> {
  const created = await startRegistration({
    optionsJSON: {
      challenge: randomBase64Url(32),
      rp: { id: window.location.hostname, name: 'Thalace Shops' },
      user: { id: randomBase64Url(16), name: who.email, displayName: `${who.name}, Thalace Shops owner` },
      pubKeyCredParams: [{ type: 'public-key', alg: ES256 }],
      authenticatorSelection: { residentKey: 'preferred', userVerification: 'required' },
      attestation: 'none',
    },
  })
  const publicKey = created.response.publicKey
  if (!publicKey || created.response.publicKeyAlgorithm !== ES256) {
    throw new Error('This browser can’t make the kind of passkey a shop needs. Try a recent Chrome, Safari or Edge.')
  }
  return { credential_id: created.id, public_key: publicKey, rp_id: window.location.hostname, origin: window.location.origin }
}

/** Sign one of the shop's requests with the founder's passkey. The request is
 * passed to the device exactly as NEAR Intents made it. */
export async function signWithPasskey(request: PendingSignature): Promise<Record<string, unknown>> {
  if (request.intent.standard !== 'webauthn') {
    throw new Error(`Shops sign with a passkey, but NEAR Intents asked for a ${request.intent.standard} signature.`)
  }
  const credential = await startAuthentication({ optionsJSON: request.intent.payload as PublicKeyCredentialRequestOptionsJSON })
  return { ...request.intent, credential }
}

/** What went wrong with a passkey prompt, in words for the founder. */
export function passkeyError(error: unknown): string {
  if (error instanceof Error && error.name === 'NotAllowedError') return 'The passkey prompt was closed or timed out. Try again.'
  return error instanceof Error ? error.message : String(error)
}
