import type { Session } from '@supabase/supabase-js'
import { useEffect, useMemo, useState, type ReactNode } from 'react'

import { AuthContext, type AuthState } from './auth-context'
import { supabase } from './supabase'

// Where Supabase sends people back after the email link or Google.
const redirectTo = () => `${window.location.origin}/`

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next))
    return () => data.subscription.unsubscribe()
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      session,
      loading,
      sendMagicLink: async (email) => {
        const { error } = await supabase.auth.signInWithOtp({ email, options: { emailRedirectTo: redirectTo() } })
        if (error) throw error
      },
      signInWithGoogle: async () => {
        const { error } = await supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: redirectTo() } })
        if (error) throw error
      },
      signOut: async () => {
        await supabase.auth.signOut()
      },
    }),
    [session, loading],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
