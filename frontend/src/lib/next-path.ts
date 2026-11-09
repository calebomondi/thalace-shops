/** Where to go after signing in: always a path inside this app. */

export const HOME_PATH = '/'

/** A same-site path to return to after sign-in, or null. Rejects absolute and
 * protocol-relative URLs ("//evil.com") so `?next=` can't be an open redirect. */
export function safeNextPath(raw: string | null): string | null {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//') || raw.startsWith('/\\')) return null
  if (raw.startsWith('/auth/')) return null
  return raw
}

// Google sign-in leaves the app and comes back in the same tab, so `next`
// waits in sessionStorage. (The email link may open in a new tab, so it
// carries `next` in its own URL instead.)
const OAUTH_NEXT_KEY = 'thalace-shops.oauth-next'

export function rememberOAuthNext(raw: string | null): void {
  try {
    const next = safeNextPath(raw)
    if (next) sessionStorage.setItem(OAUTH_NEXT_KEY, next)
    else sessionStorage.removeItem(OAUTH_NEXT_KEY)
  } catch {
    // Storage blocked: the user lands on the home page instead.
  }
}

export function takeOAuthNext(): string | null {
  try {
    const next = sessionStorage.getItem(OAUTH_NEXT_KEY)
    sessionStorage.removeItem(OAUTH_NEXT_KEY)
    return safeNextPath(next)
  } catch {
    return null
  }
}

/** The page Supabase sends people back to, carrying `next` when there is one. */
export function callbackUrl(next: string | null): string {
  const url = new URL('/auth/callback', window.location.origin)
  const safe = safeNextPath(next)
  if (safe) url.searchParams.set('next', safe)
  return url.toString()
}
