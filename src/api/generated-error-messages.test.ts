import { afterEach, expect, it } from 'vitest'
import { CrmApiError } from './contracts'
import { mapRequestError, requestErrorMessage } from './request-state'
import { resolveLocaleMessage, setLocale } from '@/i18n'

afterEach(() => setLocale('zh-CN'))

it.each([
  ['INVALID_TRANSITION', 'RFQ can only be created when the Opportunity is at customer_budget_approved.', 'Customer budget approved', '客户预算批准阶段'],
  ['INVALID_TRANSITION', 'Demo Request can only be created for an Opportunity in qualified_opportunity or demo_done.', 'Qualified opportunity or Demo done', '合格商机或 Demo 完成'],
  ['INVALID_TRANSITION', 'New Opportunity must start at qualified_opportunity.', 'Qualified opportunity', '合格商机阶段'],
  ['INVALID_TRANSITION', 'Opportunity stages change only through their workflow actions.', 'workflow actions', '流程操作'],
  ['INVALID_TRANSITION', 'The probability level is frozen once the PO is received or the Opportunity is lost.', 'success probability is frozen', '成功概率不能再修改'],
  ['INVALID_TRANSITION', 'Internal validation is only available for equipment Opportunities.', 'equipment Opportunities', '设备类商机'],
  ['INVALID_TRANSITION', 'The internal validation was already decided or cancelled.', 'already decided', '已审批或已撤销'],
  ['INVALID_TRANSITION', 'Rollback target must be an earlier stage.', 'earlier stage', '早于当前阶段'],
  ['INVALID_TRANSITION', 'internal_validation requires the Booking created by an approved internal validation.', 'Internal validation requires', '已批准的内部生产审批'],
  ['INVALID_TRANSITION', 'A lost Opportunity cannot be advanced by workflow completion.', 'cannot be advanced', '不能由流程完成自动推进'],
  ['INVALID_TRANSITION', 'Budget approval is not available at qualified_opportunity.', 'Budget approval is not available at Qualified opportunity.', '当前阶段为合格商机，不能确认客户预算。'],
  ['INVALID_TRANSITION', 'Internal validation is not available at demo_done.', 'Internal validation is not available at Demo done.', '不能申请内部生产审批'],
  ['INVALID_TRANSITION', 'Internal validation review is not available at internal_validation.', 'Internal validation review is not available at Internal validation.', '不能审批内部生产申请'],
  ['INVALID_TRANSITION', 'PO confirmation is not available at rfq_validated.', 'PO confirmation is not available at RFQ validated.', '当前阶段为RFQ 通过，不能确认收到 PO。'],
  ['INVALID_TRANSITION', 'Marking the Opportunity lost is not available at po_received.', 'Marking the Opportunity lost is not available at PO received.', '不能标记丢单'],
  ['INVALID_TRANSITION', 'A lost Opportunity can only reopen at or below quotation_sent.', 'reopen at Quotation sent or an earlier stage', '重新打开到报价已发或更早的阶段'],
  ['INVALID_TRANSITION', 'The currency of a confirmed order cannot change through an ordinary edit.', 'currency of a confirmed order cannot change', '已确认订单的币种不能通过普通编辑修改'],
  ['BOOKING_SOURCE_INVALID', 'Source Opportunity must belong to the Account.', 'must belong to the Account', '来源商机必须属于该客户'],
  ['BOOKING_SOURCE_INVALID', 'Opportunity Bookings are created by confirming the PO or approving an internal validation.', 'confirming the PO', '确认收到 PO'],
  ['BOOKING_SOURCE_INVALID', 'Account, source, Opportunity and type of an Opportunity Booking cannot change.', 'cannot change', '不能修改'],
  ['BOOKING_SOURCE_INVALID', "A Booking's source cannot change.", 'source cannot change', '来源不能修改'],
  ['BOOKING_STATUS_INVALID', 'An Opportunity Booking can only be changed to Cancelled.', 'changed to Cancelled', '只能改为已取消'],
  ['VALIDATION_ERROR', 'Lost Reason is required for a lost Opportunity.', 'lost reason is required', '丢单原因'],
  ['VALIDATION_ERROR', 'probabilityLevel cannot be cleared once the demo is done.', 'cannot be cleared', '不能清空成功概率'],
  ['VALIDATION_ERROR', 'Confirm the customer need and the budget owner before creating the Opportunity.', 'budget owner', '客户需求与预算负责人'],
  ['VALIDATION_ERROR', 'Set the probability level before this step.', 'Set the success probability', '请先设置成功概率'],
  ['VALIDATION_ERROR', 'approvedOn is required.', 'budget approval date', '预算批准日期'],
  ['VALIDATION_ERROR', 'approvedOn cannot be in the future.', 'cannot be in the future', '不能晚于今天'],
  ['VALIDATION_ERROR', 'expectedPoDate is required.', 'expected PO date', '预计 PO 日期'],
  ['VALIDATION_ERROR', 'A comment is required to reject an internal validation.', 'comment is required', '必须填写审批意见'],
  ['VALIDATION_ERROR', 'booking is required.', 'Booking details', 'Booking 信息'],
  ['VALIDATION_ERROR', 'singleSalesObjective is too long.', 'single sales objective is too long', '本单目标过长'],
  ['VALIDATION_ERROR', 'opportunityAmount must be blank or a non-negative amount with at most two decimal places.', 'can be left blank', '金额可以留空'],
  ['VALIDATION_ERROR', 'amount must be positive with at most two decimal places.', 'amount is not valid', '金额无效'],
  ['VALIDATION_ERROR', 'originalAmount must be positive with at most two decimal places.', 'original amount is not valid', '原始金额无效'],
  ['VALIDATION_ERROR', 'region must be an English region name.', 'custom region in English', '自定义区域请用英文填写'],
  ['VALIDATION_ERROR', 'subRegion is not a known region.', 'account regions', '已有的客户区域'],
  ['VALIDATION_ERROR', 'Confirmed order currency is fixed', 'currency of a confirmed order is fixed', '已确认订单的币种不可修改'],
  ['BOOKING_SOURCE_REQUIRED', 'Opportunity Booking requires a source Opportunity.', 'requires a source Opportunity', '必须关联来源商机'],
  ['CONFLICT', 'Account and sale type cannot change while the Opportunity has a live Booking.', 'sale type cannot change', '不能修改客户或销售类型'],
  ['CONFLICT', 'The Opportunity already has a pending internal validation.', 'pending internal validation', '待审批的内部生产审批'],
  ['CONFLICT', 'No other active Manager can review this internal validation.', 'No other active Manager', '没有其他在职 Manager'],
  ['CONFLICT', 'The Opportunity already has a live Booking.', 'already has a live Booking', '已有未取消的 Booking'],
  ['BOOKING_ALREADY_EXISTS', 'The Opportunity already has a live Booking.', 'already has a live Booking', '已有未取消的 Booking'],
  ['CONFLICT', 'Cancel the Booking before marking the Opportunity lost.', 'before marking the Opportunity lost', '再标记丢单'],
  ['CONFLICT', 'A completed Booking blocks stage rollback.', 'blocks stage rollback', '不能回退商机阶段'],
  ['CONFLICT', 'Cancel the Booking before rolling the Opportunity back.', 'before rolling the Opportunity back', '再回退商机阶段'],
  ['CONFLICT', 'Opportunity must be at customer_budget_approved before workflow completion can move it to rfq_validated.', 'at Customer budget approved before workflow completion can move it to RFQ validated', '商机必须处于客户预算批准阶段，才能在流程完成后推进至RFQ 通过。'],
  ['PERMISSION_DENIED', 'Only the Opportunity owner can set the probability level.', 'Only the Opportunity owner can set the success probability.', '只有商机负责人可以设置成功概率。'],
  ['PERMISSION_DENIED', 'Managers cannot review their own internal validation.', 'their own internal validation', '不能审批自己提交的'],
  ['INTERNAL_VALIDATION_NOT_FOUND', 'Internal validation was not found.', 'Internal validation was not found.', '未找到该内部生产审批申请'],
])('localizes known %s feedback "%s" while retaining raw diagnostic metadata', (code, message, english, chinese) => {
  const error = new CrmApiError(code, message, 'req_original', false, { field: '原始字段错误' })
  const mapped = mapRequestError(error)
  setLocale('en-US')
  expect(resolveLocaleMessage(mapped.localizedMessage!)).toContain(english)
  expect(resolveLocaleMessage(requestErrorMessage(error))).not.toMatch(/\p{Script=Han}/u)
  setLocale('zh-CN')
  expect(resolveLocaleMessage(mapped.localizedMessage!)).toContain(chinese)
  expect(mapped.message).toBe(message)
  expect(mapped.requestId).toBe('req_original')
  expect(error.fieldErrors).toEqual({ field: '原始字段错误' })
})

it('localizes the owner-only success probability denial in Chinese and keeps it a denied error', () => {
  const error = new CrmApiError('PERMISSION_DENIED', 'Only the Opportunity owner can set the probability level.', 'req_level_owner', false)
  setLocale('zh-CN')
  const mapped = mapRequestError(error)
  expect(resolveLocaleMessage(mapped.localizedMessage!)).toBe('只有商机负责人可以设置成功概率。')
  expect(resolveLocaleMessage(requestErrorMessage(error))).toBe('只有商机负责人可以设置成功概率。')
  expect(mapped).toMatchObject({ message: 'Only the Opportunity owner can set the probability level.', denied: true })
})

it('preserves arbitrary server errors, unrecognized stages and retired stage messages', () => {
  for (const [code, message] of [
    ['INVALID_TRANSITION', 'RFQ 自定义错误'],
    ['INVALID_TRANSITION', 'Budget approval is not available at 客户备注.'],
    ['INVALID_TRANSITION', 'Unknown action is not available at demo_done.'],
    ['INVALID_TRANSITION', 'Opportunity cannot move from 需求发现 to 采购流程.'],
    ['CONFLICT', 'Opportunity must be at 客户备注 before workflow completion can move it to demo_done.'],
  ] as const) {
    const error = new CrmApiError(code, message, 'req_server', false)
    setLocale('en-US')
    expect(mapRequestError(error).localizedMessage).toBeUndefined()
    expect(requestErrorMessage(error)).toBe(message)
  }
})
