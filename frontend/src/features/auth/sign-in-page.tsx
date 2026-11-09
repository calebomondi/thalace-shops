import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router'

import { Button, ErrorNote, Field, Input } from '../../components/ui'
import { useAuth } from '../../lib/auth-context'

type Stage =
  | { kind: 'idle' }
  | { kind: 'sending' }
  | { kind: 'sent'; email: string }
  | { kind: 'failed'; message: string }

function GoogleMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="size-4">
      <path
        fill="#4285F4"
        d="M23.52 12.27c0-.85-.08-1.67-.22-2.45H12v4.64h6.46a5.52 5.52 0 0 1-2.4 3.62v3h3.88c2.27-2.09 3.58-5.17 3.58-8.81Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.96-1.07 7.94-2.91l-3.88-3.01c-1.07.72-2.45 1.15-4.06 1.15-3.13 0-5.78-2.11-6.72-4.95H1.27v3.11A12 12 0 0 0 12 24Z"
      />
      <path fill="#FBBC05" d="M5.28 14.28a7.2 7.2 0 0 1 0-4.56V6.61H1.27a12 12 0 0 0 0 10.78l4.01-3.11Z" />
      <path
        fill="#EA4335"
        d="M12 4.77c1.76 0 3.34.6 4.59 1.8l3.44-3.44A11.52 11.52 0 0 0 12 0 12 12 0 0 0 1.27 6.61l4.01 3.11C6.22 6.88 8.87 4.77 12 4.77Z"
      />
    </svg>
  )
}

export function SignInPage() {
  const { sendMagicLink, signInWithGoogle } = useAuth()
  const [searchParams] = useSearchParams()
  const next = searchParams.get('next')
  const [email, setEmail] = useState('')
  const [stage, setStage] = useState<Stage>({ kind: 'idle' })

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setStage({ kind: 'sending' })
    try {
      await sendMagicLink(email.trim(), next)
      setStage({ kind: 'sent', email: email.trim() })
    } catch (error) {
      setStage({ kind: 'failed', message: error instanceof Error ? error.message : 'The link could not be sent.' })
    }
  }

  async function onGoogle() {
    try {
      await signInWithGoogle(next)
    } catch (error) {
      setStage({ kind: 'failed', message: error instanceof Error ? error.message : 'Google sign-in failed.' })
    }
  }

  return (
    <main className="mx-auto flex min-h-svh max-w-md flex-col justify-center px-4 py-12">
      <p className="font-display text-sm tracking-wide text-accent">Thalace Shops</p>
      <h1 className="mt-2 font-display text-3xl leading-tight">Run your shops with an agent that sells for you.</h1>
      <p className="mt-3 text-muted">Each shop gets its own agent and its own wallet, inside rules only you can change.</p>

      <div className="mt-8 space-y-5 rounded-2xl border border-line bg-card p-6 shadow-sm">
        {stage.kind === 'sent' ? (
          <div className="space-y-2">
            <h2 className="font-medium">Check your email</h2>
            <p className="text-sm text-muted">
              We sent a sign-in link to <span className="text-ink">{stage.email}</span>. It works once and expires in an
              hour.
            </p>
            <button className="text-sm text-accent underline" onClick={() => setStage({ kind: 'idle' })}>
              Use another email
            </button>
          </div>
        ) : (
          <>
            <Button variant="quiet" className="w-full" onClick={onGoogle}>
              <GoogleMark />
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
