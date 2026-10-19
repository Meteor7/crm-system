import type { DemoHealthDto } from '@/types/crm'
import type { Locale } from '@/i18n'

// Translate only the system-generated health messages; keep unknown server text intact.
export function demoHealthReason(health: DemoHealthDto | undefined, locale: Locale): string {
  const reason = health?.reason || '正常推进'
  if (locale === 'zh-CN') return reason
  const fixed: Record<string, string> = {
    '客户预期为今天': 'Customer expected date is today',
    '今天有进展': 'Progress made today',
    '正常推进': 'Progressing normally',
  }
  if (fixed[reason]) return fixed[reason]
  const patterns: Array<[RegExp, (days: string) => string]> = [
    [/^客户预期已逾期 (\d+) 天$/, (days) => `Customer expected date is overdue by ${days} ${days === '1' ? 'day' : 'days'}`],
    [/^距客户预期仅 (\d+) 天$/, (days) => `Only ${days} ${days === '1' ? 'day' : 'days'} until the customer expected date`],
    [/^Test Run DDL 已逾期 (\d+) 天$/, (days) => `Test run deadline is overdue by ${days} ${days === '1' ? 'day' : 'days'}`],
    [/^已连续 (\d+) 天无有效进展$/, (days) => `No meaningful progress for ${days} ${days === '1' ? 'day' : 'days'}`],
    [/^(\d+) 天内有进展$/, (days) => `Progress within the last ${days} ${days === '1' ? 'day' : 'days'}`],
  ]
  for (const [pattern, translate] of patterns) {
    const match = pattern.exec(reason)
    if (match) return translate(match[1])
  }
  return reason
}
