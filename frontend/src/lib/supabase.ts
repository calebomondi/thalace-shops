import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

if (!url || !anonKey) {
  throw new Error('VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY must be set (frontend/.env.local).')
}

// PKCE: Google and the email link both return to /auth/callback with ?code=,
// which that page exchanges for a session itself. detectSessionInUrl is off so
// the code is never exchanged twice (the second attempt would fail).
export const supabase = createClient(url, anonKey, {
  auth: { flowType: 'pkce', detectSessionInUrl: false, persistSession: true, autoRefreshToken: true },
})

/** Refresh a token this close to expiry before using it: a tab that slept can hold one already past it. */
const EXPIRY_MARGIN_MS = 60_000

/** The signed-in user's access token, refreshed first when it is about to expire; null when signed out. */
export async function accessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession()
  const session = data.session
  if (!session) return null
  const expiresAt = (session.expires_at ?? 0) * 1000
  if (expiresAt - Date.now() < EXPIRY_MARGIN_MS) return refreshAccessToken()
  return session.access_token
}

/** A new access token from the session's refresh token; null when the session can't be renewed. */
export async function refreshAccessToken(): Promise<string | null> {
  const { data, error } = await supabase.auth.refreshSession()
  return error ? null : (data.session?.access_token ?? null)
}
