import { preferredPersonnelId } from '@/demo/personnel'
import { isIsoDate } from '@/domain/evaluations'
import { localeMessage, type LocaleMessage } from '@/i18n'
import type { ContactSummaryDto } from '@/types/crm'
import type { BookingDraft, StrategyOpportunityDto } from '@/types/workspaces'

type DraftSource = Pick<StrategyOpportunityDto, 'accountId' | 'title' | 'toolType' | 'amount' | 'currency' | 'poDate' | 'internalValidation' | 'liveBooking'>

/**
 * Booking fields for an Opportunity action. The latest internal validation request supplies its draft, the live
 * Booking the viewer can read overrides every detail it holds (contact and note included, since Sales can edit the
 * Pending Booking after the approval), and the Opportunity fills whatever is still missing.
 * A Sales user can only assign themselves, so `lockedOwner` replaces any other owner.
 */
export function opportunityBookingDraft(
  opportunity: DraftSource,
  contacts: readonly ContactSummaryDto[],
  defaultOwner: string,
  lockedOwner = '',
): BookingDraft {
  const requested: Partial<BookingDraft> = opportunity.internalValidation?.booking ?? {}
  const booking = opportunity.liveBooking
  const usableContact = (id?: string) => Boolean(id) && contacts.some((contact) =>
    contact.id === id && contact.accountId === opportunity.accountId && contact.status === 'Active')
  const primaryContactId = [booking?.primaryContactId, requested.primaryContactId].find(usableContact)
    ?? contacts.find((contact) => contact.accountId === opportunity.accountId && contact.status === 'Active')?.id ?? ''
  return {
    primaryContactId,
    equipment: booking?.equipment ?? requested.equipment ?? (opportunity.toolType || opportunity.title),
    quantity: booking?.quantity ?? requested.quantity ?? 1,
    ddl: booking?.ddl ?? requested.ddl ?? opportunity.poDate,
    amount: booking?.amount ?? requested.amount ?? opportunity.amount,
    currency: booking?.currency ?? requested.currency ?? opportunity.currency,
    owner: lockedOwner || preferredPersonnelId('Sales', booking?.owner ?? requested.owner ?? defaultOwner),
    note: booking?.note ?? requested.note ?? '',
  }
}

export type BookingDraftErrors = Partial<Record<keyof BookingDraft, LocaleMessage>>

/** Client-side checks that match the server's Booking draft rules, so a form error appears next to its field. */
export function validateBookingDraft(draft: BookingDraft): BookingDraftErrors {
  const errors: BookingDraftErrors = {}
  if (!draft.primaryContactId) errors.primaryContactId = localeMessage('Select a primary contact', '请选择主要联系人')
  if (!draft.equipment.trim()) errors.equipment = localeMessage('Enter the equipment need', '请填写设备需求')
  if (!Number.isInteger(draft.quantity) || draft.quantity < 1) errors.quantity = localeMessage('Enter a whole quantity of at least 1', '数量必须为不小于 1 的整数')
  if (!isIsoDate(draft.ddl)) errors.ddl = localeMessage('Enter a valid customer DDL', '请填写有效的客户 DDL')
  if (!/^\d+(?:\.\d{1,2})?$/.test(String(draft.amount).trim())) errors.amount = localeMessage('Enter an amount with at most two decimal places', '请填写最多两位小数的金额')
  if (!draft.currency) errors.currency = localeMessage('Select a currency', '请选择币种')
  if (!draft.owner) errors.owner = localeMessage('Select a Booking owner', '请选择 Booking 负责人')
  return errors
}

export function trimmedBookingDraft(draft: BookingDraft): BookingDraft {
  return {
    ...draft,
    equipment: draft.equipment.trim(),
    amount: String(draft.amount).trim(),
    owner: draft.owner.trim(),
    note: draft.note.trim(),
  }
}
