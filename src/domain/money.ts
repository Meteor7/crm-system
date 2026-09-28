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

export function moneyByCurrency<T extends { currency: string; amount: DecimalAmount }>(rows: T[]) {
  const buckets = new Map<string, DecimalAmount[]>()
  rows.forEach((row) => {
    const currency = row.currency.trim().toUpperCase()
    if (!currency) throw new Error('Currency is required')
    buckets.set(currency, [...(buckets.get(currency) ?? []), row.amount])
  })
  return [...buckets.entries()].sort(([left], [right]) => left.localeCompare(right))
    .map(([currency, amounts]) => ({ currency, amount: addMoney(amounts) }))
}

export function formatMoney(value: DecimalAmount, currency: string): string {
  const normalized = normalizeMoney(value)
  const [whole, fraction] = normalized.split('.')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${currency.toUpperCase()} ${grouped}.${fraction}`
}
