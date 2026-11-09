import { Link, Outlet } from 'react-router'

import { useAuth } from '../lib/auth-context'

export function AppShell() {
  const { session, signOut } = useAuth()
  return (
    <div className="min-h-svh">
      <header className="border-b border-line bg-card/70 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
          <Link to="/" className="font-display text-lg">
            Thalace <span className="text-accent">Shops</span>
          </Link>
          <div className="flex min-w-0 items-center gap-3 text-sm">
            <span className="truncate text-muted">{session?.user.email}</span>
            <button className="shrink-0 text-muted underline hover:text-ink" onClick={signOut}>
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
