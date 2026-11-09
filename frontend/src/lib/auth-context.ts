import type { Session } from '@supabase/supabase-js'
import { createContext, useContext } from 'react'

export type AuthState = {
  session: Session | null
  /** Email a sign-in link that returns to `next` (a path in this app). */
  sendMagicLink: (email: string, next: string | null) => Promise<void>
  /** Leave for Google; the callback page brings the user back to `next`. */
  signInWithGoogle: (next: string | null) => Promise<void>
  signOut: () => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth must be used inside <AuthProvider>')
  return auth
}
