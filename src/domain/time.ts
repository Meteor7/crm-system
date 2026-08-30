const SHANGHAI_TIME_ZONE = 'Asia/Shanghai'

function dateTimeParts(now: Date) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: SHANGHAI_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(now)
  return Object.fromEntries(parts.map((part) => [part.type, part.value]))
}

export function shanghaiDate(now = new Date()) {
  const parts = dateTimeParts(now)
  return `${parts.year}-${parts.month}-${parts.day}`
}

export function shanghaiTimestamp(now = new Date()) {
  const parts = dateTimeParts(now)
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}+08:00`
}

export function addIsoDateDays(date: string, amount: number) {
  const [year, month, day] = date.split('-').map(Number)
  const value = new Date(Date.UTC(year, month - 1, day + amount))
  return `${value.getUTCFullYear()}-${String(value.getUTCMonth() + 1).padStart(2, '0')}-${String(value.getUTCDate()).padStart(2, '0')}`
}

export function formatDisplayDate(value?: string | null, now = new Date()) {
  const text = String(value ?? '').trim()
  if (!text) return '—'

  const today = shanghaiDate(now)
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text
  if (/^(?:刚刚|当前待办|今天(?:\s+\d{1,2}:\d{2})?)$/.test(text)) return today
  if (/^昨天(?:\s+\d{1,2}:\d{2})?$/.test(text)) return addIsoDateDays(today, -1)

  const daysAgo = text.match(/^(\d+)\s*天前$/)
  if (daysAgo) return addIsoDateDays(today, -Number(daysAgo[1]))

  const monthDay = text.match(/^(\d{1,2})月(\d{1,2})日$/)
  if (monthDay) return `${today.slice(0, 4)}-${monthDay[1].padStart(2, '0')}-${monthDay[2].padStart(2, '0')}`

  const shortDate = text.match(/^(\d{1,2})-(\d{1,2})$/)
  if (shortDate) return `${today.slice(0, 4)}-${shortDate[1].padStart(2, '0')}-${shortDate[2].padStart(2, '0')}`

  const dateTime = text.match(/^(\d{4}-\d{2}-\d{2})[ T]\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?$/)
  if (dateTime) return dateTime[1]

  const parsed = new Date(text)
  if (!Number.isNaN(parsed.getTime())) return shanghaiDate(parsed)
  return text
}
