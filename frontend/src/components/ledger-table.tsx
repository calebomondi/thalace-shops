import type { LedgerKind, LedgerLine } from '../lib/api/public'

const KIND: Record<LedgerKind, string> = { sale: 'Sale', fee: 'Platform fee', payout: 'Payout', refund: 'Refund' }

function amount(line: LedgerLine): string {
  if (line.amount_usd === null) return ''
  const value = Number(line.amount_usd)
  const outgoing = line.kind !== 'sale'
  return `${outgoing ? '−' : '+'}$${value.toFixed(2)}`
}

/** A shop's ledger: every sale, fee and payout, with links to NEAR. */
export function LedgerTable({ lines }: { lines: LedgerLine[] }) {
  if (lines.length === 0) return <p className="text-sm text-muted">Nothing on the ledger yet.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[34rem] text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs text-muted">
            <th className="py-2 font-medium">When</th>
            <th className="py-2 font-medium">What</th>
            <th className="py-2 font-medium">Invoice</th>
            <th className="py-2 font-medium">To / from</th>
            <th className="py-2 text-right font-medium">Amount</th>
            <th className="py-2 pl-3 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line, i) => (
            <tr key={i} className="border-b border-line/60 align-top">
              <td className="py-2 whitespace-nowrap text-muted">{new Date(line.created_at).toLocaleDateString()}</td>
              <td className="py-2">{KIND[line.kind]}</td>
              <td className="py-2 font-mono text-xs">{line.invoice_number ?? ''}</td>
              <td className="max-w-40 truncate py-2 text-muted">{line.counterparty ?? ''}</td>
              <td className={`py-2 text-right tabular-nums ${line.kind === 'sale' ? 'text-ok' : ''}`}>{amount(line)}</td>
              <td className="py-2 pl-3">
                {line.tx_url ? (
                  <a className="text-accent underline" href={line.tx_url} target="_blank" rel="noreferrer">
                    {line.status}
                  </a>
                ) : (
                  <span className={line.status === 'failed' ? 'text-danger' : 'text-muted'}>
                    {line.status}
                    {line.failure_code && ` (${line.failure_code})`}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
