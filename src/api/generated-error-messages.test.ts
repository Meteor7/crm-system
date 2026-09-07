import { expect, it } from 'vitest'
import { CrmApiError } from './contracts'
import { mapRequestError, requestErrorMessage } from './request-state'
import { resolveLocaleMessage, setLocale } from '@/i18n'

it.each([
  ['INVALID_TRANSITION', 'RFQ can only be created when the Opportunity is in 设备规格确认.', 'Equipment specification'],
  ['INVALID_TRANSITION', 'Demo Request can only be created for an Opportunity in 需求发现 or Wafer Demo确认.', 'Discovery or Wafer demo confirmed'],
  ['INVALID_TRANSITION', 'Opportunity cannot move from 需求发现 to 采购流程.', 'Discovery to Procurement'],
  ['INVALID_TRANSITION', 'Opportunity must be in Wafer Demo确认 before workflow completion can move it to 预算审批.', 'Wafer demo confirmed'],
  ['CONFLICT', 'Cancel the active Demo Request before rolling the Opportunity back to 需求发现.', 'Discovery'],
])('localizes known %s feedback while retaining raw diagnostic metadata', (code, message, english) => {
  const error = new CrmApiError(code, message, 'req_original', false, { field: '原始字段错误' })
  const mapped = mapRequestError(error)
  setLocale('en-US')
  expect(resolveLocaleMessage(mapped.localizedMessage!)).toContain(english)
  expect(resolveLocaleMessage(requestErrorMessage(error))).not.toMatch(/\p{Script=Han}/u)
  expect(mapped.message).toBe(message)
  expect(mapped.requestId).toBe('req_original')
  expect(error.fieldErrors).toEqual({ field: '原始字段错误' })
})

it('preserves arbitrary server errors and unrecognized stage diagnostics', () => {
  for (const message of ['RFQ 自定义错误', 'Opportunity cannot move from 客户备注 to 预算审批.']) {
    const error = new CrmApiError('INVALID_TRANSITION', message, 'req_server', false)
    setLocale('en-US')
    expect(mapRequestError(error).localizedMessage).toBeUndefined()
    expect(requestErrorMessage(error)).toBe(message)
  }
})
