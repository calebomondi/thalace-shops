import { useState } from 'react'

/** How another agent buys here: the MCP address and a client config. */
export function AgentConnect({ compact = false }: { compact?: boolean }) {
  const url = `${window.location.origin}/mcp`
  const config = JSON.stringify({ mcpServers: { 'thalace-shops': { type: 'http', url } } }, null, 2)
  const [copied, setCopied] = useState(false)

  return (
    <div className="space-y-2 rounded-2xl border border-line bg-card p-5">
      <p className="font-medium">{compact ? 'Buy with your agent' : 'Connect your agent'}</p>
      <p className="text-sm text-muted">
        Any MCP client (Claude, Cursor, your own script) can search these shops, negotiate within each shop’s rules,
        and get an invoice to pay. No account needed.
      </p>
      <code className="block break-all rounded-lg bg-paper px-3 py-2 text-sm">{url}</code>
      {!compact && <pre className="overflow-x-auto rounded-lg bg-paper p-3 text-xs">{config}</pre>}
      <button
        className="text-sm text-accent underline"
        onClick={async () => {
          await navigator.clipboard.writeText(compact ? url : config)
          setCopied(true)
        }}
      >
        {copied ? 'Copied' : compact ? 'Copy the address' : 'Copy the config'}
      </button>
    </div>
  )
}
