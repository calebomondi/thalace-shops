import { useCallback, useEffect, useState } from 'react'

import { createShop, listShops, type Shop, type ShopCreate } from '../../lib/api/shops'

type ShopsState =
  | { kind: 'loading' }
  | { kind: 'failed'; message: string }
  | { kind: 'ready'; shops: Shop[] }

function failed(error: unknown): ShopsState {
  return { kind: 'failed', message: error instanceof Error ? error.message : 'Shops could not be loaded.' }
}

export function useShops() {
  const [state, setState] = useState<ShopsState>({ kind: 'loading' })

  // The state starts as loading, so the first load only fills it in. A reply
  // that lands after the page is gone is dropped.
  useEffect(() => {
    let current = true
    listShops().then(
      (shops) => current && setState({ kind: 'ready', shops }),
      (error: unknown) => current && setState(failed(error)),
    )
    return () => {
      current = false
    }
  }, [])

  const reload = useCallback(async () => {
    setState({ kind: 'loading' })
    try {
      setState({ kind: 'ready', shops: await listShops() })
    } catch (error) {
      setState(failed(error))
    }
  }, [])

  const add = useCallback(async (body: ShopCreate) => {
    const shop = await createShop(body)
    setState((current) => (current.kind === 'ready' ? { kind: 'ready', shops: [...current.shops, shop] } : current))
    return shop
  }, [])

  return { state, reload, add }
}
