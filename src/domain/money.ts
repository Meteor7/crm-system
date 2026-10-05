export type DecimalAmount = string

const DECIMAL_20_2 = /^(?:0|[1-9]\d{0,17})(?:\.\d{1,2})?$/

function cents(value: DecimalAmount): bigint {
  if (!DECIMAL_20_2.test(value)) throw new Error('Money must satisfy DECIMAL(20,2)')
  const [whole, fraction = ''] = value.split('.')
  return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'))
}

function fromCents(value: bigint): DecimalAmount {
  if (value < 0n) throw new Error('Money must be non-negative')
  if (value > 99999999999999999999n) throw new Error('Money must satisfy DECIMAL(20,2)')
  return `${value / 100n}.${String(value % 100n).padStart(2, '0')}`
}

export function normalizeMoney(value: DecimalAmount): DecimalAmount {
  return fromCents(cents(value))
}

export function addMoney(values: DecimalAmount[]): DecimalAmount {
  return fromCents(values.reduce((total, value) => total + cents(value), 0n))
}

/**
 * Totals per currency of the known amounts. An Opportunity amount nobody has entered yet is '' (allowed at
 * Qualified opportunity) and adds nothing, not even its currency: count it with unknownAmountCount.
 */
export function moneyByCurrency<T extends { currency: string; amount: DecimalAmount | '' }>(rows: T[]) {
  const buckets = new Map<string, DecimalAmount[]>()
  rows.forEach((row) => {
    if (!row.amount) return
    const currency = row.currency.trim().toUpperCase()
    if (!currency) throw new Error('Currency is required')
    buckets.set(currency, [...(buckets.get(currency) ?? []), row.amount])
  })
  return [...buckets.entries()].sort(([left], [right]) => left.localeCompare(right))
    .map(([currency, amounts]) => ({ currency, amount: addMoney(amounts) }))
}

/** How many rows moneyByCurrency leaves out because their amount is not entered yet. */
export function unknownAmountCount(rows: ReadonlyArray<{ amount: DecimalAmount | '' }>) {
  return rows.filter((row) => !row.amount).length
}

/**
 * The known totals per currency, followed by how many amounts are not entered yet, so a partial total never
 * reads as complete: "CNY 100.00 · 1 条未填金额".
 */
export function formatKnownTotals<T extends { currency: string; amount: DecimalAmount | '' }>(rows: T[], unknownLabel: (count: number) => string) {
  return formatSummedTotals(moneyByCurrency(rows), unknownAmountCount(rows), unknownLabel)
}

/** formatKnownTotals for totals that are already added up, as the server's stage summary carries them. */
export function formatSummedTotals(
  totals: ReadonlyArray<{ currency: string; amount: DecimalAmount }>,
  unknown: number,
  unknownLabel: (count: number) => string,
) {
  const known = [...totals].sort((left, right) => left.currency.localeCompare(right.currency))
  return [...known.map((item) => formatTotal(item.amount, item.currency)), ...(unknown ? [unknownLabel(unknown)] : [])].join(' · ')
}

/**
 * formatMoney for a total. A total over every matching record can be larger than any single amount may
 * be, so it is not held to DECIMAL(20,2): it is grouped as it stands and never throws while rendering.
 */
function formatTotal(value: DecimalAmount, currency: string): string {
  const [whole, fraction = ''] = value.split('.')
  return `${currency.toUpperCase()} ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction.padEnd(2, '0')}`
}

/** An amount not entered yet ('') shows as a dash, never as 0 or an error; pages usually say so in words instead. */
export function formatMoney(value: DecimalAmount | '', currency: string): string {
  if (!value) return '—'
  const normalized = normalizeMoney(value)
  const [whole, fraction] = normalized.split('.')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${currency.toUpperCase()} ${grouped}.${fraction}`
}
