import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { ErrorNote } from '../../components/ui'
import { HOME_PATH, safeNextPath, takeOAuthNext } from '../../lib/next-path'
import { supabase } from '../../lib/supabase'

// A code can be exchanged once. React runs this page's effect twice in
// development, so both runs share one exchange per code.
const exchanges = new Map<string, Promise<string | null>>()

function exchange(code: string): Promise<string | null> {
  let pending = exchanges.get(code)
  if (!pending) {
    pending = supabase.auth.exchangeCodeForSession(code).then(({ error }) => error?.message ?? null)
    exchanges.set(code, pending)
  }
  return pending
}

/** Where Google and the email link return: swap ?code= for a session, then
 * go where the user was headed. */
export function AuthCallbackPage() {
  const navigate = useNavigate()
  const [failure, setFailure] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      const url = new URL(window.location.href)
      const code = url.searchParams.get('code')
      // Supabase reports a refused sign-in (an expired link, a cancelled
      // Google screen) in the URL rather than with a code.
      const refused = url.searchParams.get('error_description') ?? new URLSearchParams(url.hash.slice(1)).get('error_description')
      const exchangeError = code ? await exchange(code) : null
      const { data } = await supabase.auth.getSession()
      if (cancelled) return
      if (!data.session) {
        setFailure(refused ?? exchangeError ?? 'That sign-in link has expired or was already used.')
        return
      }
      const next = safeNextPath(url.searchParams.get('next')) ?? takeOAuthNext() ?? HOME_PATH
      navigate(next, { replace: true })
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [navigate])

  if (failure) {
    return (
      <main className="mx-auto flex min-h-svh max-w-md flex-col justify-center gap-4 px-4">
        <h1 className="font-display text-2xl">You're not signed in</h1>
        <ErrorNote>{failure}</ErrorNote>
        <Link to="/auth/sign-in" className="text-sm text-accent underline">
          Back to sign in
        </Link>
      </main>
    )
  }

  return <p className="flex min-h-svh items-center justify-center text-sm text-muted">Signing you in…</p>
}
