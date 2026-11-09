/** Money as the console shows it. Amounts travel as integer cents or basis
 * points; these only format and parse them. */

export function formatUsd(cents: number): string {
  return `$${(cents / 100).toLocaleString('en-US', { minimumFractionDigits: cents % 100 ? 2 : 0, maximumFractionDigits: 2 })}`
}

/** "15", "15.5", "$1,250.50" -> cents; null when it isn't a positive amount. */
export function parseUsdToCents(input: string): number | null {
  const cleaned = input.replace(/[$,\s]/g, '')
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null
  const cents = Math.round(Number(cleaned) * 100)
  return cents > 0 ? cents : null
}

export function percent(bps: number): string {
  return `${(bps / 100).toLocaleString('en-US', { maximumFractionDigits: 2 })}%`
}

/** "12.5" (percent) -> basis points; null when out of range. */
export function parsePercentToBps(input: string): number | null {
  const value = Number(input.replace('%', '').trim())
  if (!Number.isFinite(value) || value <= 0 || value > 100) return null
  return Math.round(value * 100)
}
