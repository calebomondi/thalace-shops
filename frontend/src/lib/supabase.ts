import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

if (!url || !anonKey) {
  throw new Error('VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY must be set (frontend/.env.local).')
}

// PKCE: magic links and Google both come back with ?code=, which the client
// exchanges for a session on its own when the page loads.
export const supabase = createClient(url, anonKey, {
  auth: { flowType: 'pkce', detectSessionInUrl: true, persistSession: true },
})

/** The signed-in user's current access token, refreshed by the client as needed. */
export async function accessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
}
