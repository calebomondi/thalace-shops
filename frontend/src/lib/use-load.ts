import { useCallback, useEffect, useState } from 'react'

export type Load<T> = { kind: 'loading' } | { kind: 'failed'; message: string } | { kind: 'ready'; data: T }

function failed<T>(error: unknown): Load<T> {
  return { kind: 'failed', message: error instanceof Error ? error.message : 'This could not be loaded.' }
}

/** Server data for one view. `fetcher` must be stable (useCallback): it
 * loads once, then again on reload(); replace() applies a local change after
 * a save. A reply that lands after the view is gone is dropped. */
export function useLoad<T>(fetcher: () => Promise<T>) {
  const [state, setState] = useState<Load<T>>({ kind: 'loading' })

  useEffect(() => {
    let current = true
    fetcher().then(
      (data) => current && setState({ kind: 'ready', data }),
      (error: unknown) => current && setState(failed<T>(error)),
    )
    return () => {
      current = false
    }
  }, [fetcher])

  const reload = useCallback(async () => {
    setState({ kind: 'loading' })
    try {
      setState({ kind: 'ready', data: await fetcher() })
    } catch (error) {
      setState(failed<T>(error))
    }
  }, [fetcher])

  const replace = useCallback((update: (data: T) => T) => {
    setState((current) => (current.kind === 'ready' ? { kind: 'ready', data: update(current.data) } : current))
  }, [])

  return { state, reload, replace }
}
