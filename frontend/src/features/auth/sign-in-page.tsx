import { useState, type FormEvent } from 'react'

import { Button, ErrorNote, Field, Input } from '../../components/ui'
import { useAuth } from '../../lib/auth-context'

type Stage = { kind: 'idle' } | { kind: 'sending' } | { kind: 'sent'; email: string } | { kind: 'failed'; message: string }

export function SignInPage() {
  const { sendMagicLink, signInWithGoogle } = useAuth()
  const [email, setEmail] = useState('')
  const [stage, setStage] = useState<Stage>({ kind: 'idle' })

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setStage({ kind: 'sending' })
    try {
      await sendMagicLink(email.trim())
      setStage({ kind: 'sent', email: email.trim() })
    } catch (error) {
      setStage({ kind: 'failed', message: error instanceof Error ? error.message : 'The link could not be sent.' })
    }
  }

  async function onGoogle() {
    try {
      await signInWithGoogle()
    } catch (error) {
      setStage({ kind: 'failed', message: error instanceof Error ? error.message : 'Google sign-in failed.' })
    }
  }

  return (
    <main className="mx-auto flex min-h-svh max-w-md flex-col justify-center px-4 py-12">
      <p className="font-display text-sm tracking-wide text-accent">Thalace Shops</p>
      <h1 className="mt-2 font-display text-3xl leading-tight">Run your shops with an agent that sells for you.</h1>
      <p className="mt-3 text-muted">
        Each shop gets its own agent and its own wallet, inside rules only you can change.
      </p>

      <div className="mt-8 space-y-5 rounded-2xl border border-line bg-card p-6 shadow-sm">
        {stage.kind === 'sent' ? (
          <div className="space-y-2">
            <h2 className="font-medium">Check your email</h2>
            <p className="text-sm text-muted">
              We sent a sign-in link to <span className="text-ink">{stage.email}</span>. Open it on this device.
            </p>
            <button className="text-sm text-accent underline" onClick={() => setStage({ kind: 'idle' })}>
              Use another email
            </button>
          </div>
        ) : (
          <>
            <Button variant="quiet" className="w-full" onClick={onGoogle}>
              Continue with Google
            </Button>
            <div className="flex items-center gap-3 text-xs text-muted">
              <span className="h-px flex-1 bg-line" /> or <span className="h-px flex-1 bg-line" />
            </div>
            <form className="space-y-4" onSubmit={onSubmit}>
              <Field label="Email">
                <Input
                  type="email"
                  required
                  autoComplete="email"
                  placeholder="you@business.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </Field>
              <Button type="submit" className="w-full" disabled={stage.kind === 'sending'}>
                {stage.kind === 'sending' ? 'Sending…' : 'Email me a sign-in link'}
              </Button>
            </form>
          </>
        )}
        {stage.kind === 'failed' && <ErrorNote>{stage.message}</ErrorNote>}
      </div>
    </main>
  )
}
