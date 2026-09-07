import type { Locale } from '@/i18n'
import type { BookingDto } from '@/types/crm'

export function systemValueLabel(value: string | undefined | null, locale: Locale) {
  const text = value ?? ''
  const english: Record<string, string> = { '待确认': 'To be confirmed', '尚未开始': 'Not started', '无': 'None', '待建立覆盖': 'Coverage not established' }
  return locale === 'en-US' ? english[text] ?? text : text
}

export function bookingTitle(booking: Pick<BookingDto, 'equipment' | 'quantity' | 'title' | 'bookingType'>, locale: Locale) {
  if (locale === 'zh-CN') return booking.title
  const unit = booking.bookingType === 'Service' ? 'item' : 'unit'
  return `${booking.equipment} · ${booking.quantity} ${unit}${booking.quantity === 1 ? '' : 's'}`
}

// Contact timelines expose only the generated booking title, not its source fields.
export function bookingTimelineTitle(title: string, locale: Locale) {
  if (locale === 'zh-CN') return title
  return title.replace(/ · (\d+) (台|项)$/, (_match, quantity: string, unit: string) =>
    ` · ${quantity} ${unit === '项' ? 'item' : 'unit'}${quantity === '1' ? '' : 's'}`)
}
