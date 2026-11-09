import type { Session } from '@supabase/supabase-js'
import { useEffect, useMemo, useState, type ReactNode } from 'react'

import { AuthContext, type AuthState } from './auth-context'
import { callbackUrl, rememberOAuthNext } from './next-path'
import { supabase } from './supabase'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    void supabase.auth.getSession().then(({ data }) => {
      if (cancelled) return
      setSession(data.session)
      setLoading(false)
    })
    const { data } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next)
      setLoading(false)
    })
    return () => {
      cancelled = true
      data.subscription.unsubscribe()
    }
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      session,
      sendMagicLink: async (email, next) => {
        const { error } = await supabase.auth.signInWithOtp({
          email,
          options: { emailRedirectTo: callbackUrl(next) },
        })
        if (error) throw error
      },
      signInWithGoogle: async (next) => {
        rememberOAuthNext(next)
        const { error } = await supabase.auth.signInWithOAuth({
          provider: 'google',
          options: { redirectTo: callbackUrl(null) },
        })
        if (error) throw error
      },
      signOut: async () => {
        await supabase.auth.signOut()
      },
    }),
    [session],
  )

  // Nothing renders until the stored session is read: pages would otherwise
  // call the API before the token exists and show a sign-in error.
  if (loading) {
    return <p className="flex min-h-svh items-center justify-center text-sm text-muted">Loading…</p>
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
