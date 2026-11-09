import QRCode from 'qrcode'
import { useEffect, useState } from 'react'

import { Button } from '../../components/ui'
import type { PublicInvoice } from '../../lib/api/public'

type Payment = NonNullable<PublicInvoice['payment']>

function Copyable({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="space-y-1">
      <p className="text-xs text-muted">{label}</p>
      <div className="flex items-center gap-2">
        <code className="min-w-0 flex-1 break-all rounded-lg border border-line bg-paper px-3 py-2 text-sm">{value}</code>
        <Button
          variant="quiet"
          onClick={async () => {
            await navigator.clipboard.writeText(value)
            setCopied(true)
          }}
        >
          {copied ? 'Copied' : 'Copy'}
        </Button>
      </div>
    </div>
  )
}

function useCountdown(until: string | null): string | null {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  if (!until) return null
  const left = Math.max(0, new Date(until).getTime() - now)
  const hours = Math.floor(left / 3_600_000)
  const minutes = Math.floor((left % 3_600_000) / 60_000)
  return left === 0 ? 'expired' : `${hours}h ${minutes}m`
}

/** Where to send the money: the exact amount, the one-time address, its QR
 * and how long the quote lasts. */
export function PaymentBox({ payment }: { payment: Payment }) {
  const [qr, setQr] = useState<string | null>(null)
  const left = useCountdown(payment.expires_at)

  useEffect(() => {
    if (!payment.address) return
    let current = true
    QRCode.toDataURL(payment.address, { margin: 1, width: 192 }).then((url) => current && setQr(url))
    return () => {
      current = false
    }
  }, [payment.address])

  if (!payment.address) return null
  return (
    <div className="space-y-4 rounded-2xl border border-accent/30 bg-card p-5">
      <p className="text-sm">
        Send exactly{' '}
        <strong>
          {payment.amount} {payment.symbol ?? ''}
        </strong>{' '}
        on <strong className="capitalize">{payment.chain ?? 'the chosen chain'}</strong> to this address. Any other
        amount, coin or chain is refunded to the shop, not to you.
      </p>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        {qr && <img src={qr} alt="QR code of the payment address" className="size-40 shrink-0 rounded-lg border border-line bg-white p-1" />}
        <div className="min-w-0 flex-1 space-y-3">
          <Copyable label="Amount" value={payment.amount} />
          <Copyable label="Address" value={payment.address} />
          {payment.memo && <Copyable label="Memo (required)" value={payment.memo} />}
        </div>
      </div>
      {left && <p className="text-xs text-muted">This quote is valid for {left}. The page updates by itself when your payment lands.</p>}
    </div>
  )
}
