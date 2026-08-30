import { describe, expect, it } from 'vitest'
import { CrmApiError, normalizeCrmApiErrorCode, type CrmApiErrorCode } from './contracts'

describe('canonical CRM error contract', () => {
  it('contains the supported public codes', () => {
    const codes: CrmApiErrorCode[] = [
      'UNAUTHENTICATED', 'PERMISSION_DENIED', 'SCOPE_DENIED', 'NOT_FOUND',
      'VALIDATION_ERROR', 'CONFLICT', 'RFQ_APPROVAL_REQUIRED', 'INVALID_TRANSITION', 'VERSION_CONFLICT',
      'REPORT_NOT_READY', 'BACKEND_NOT_CONNECTED', 'NETWORK_ERROR', 'INTERNAL_ERROR',
    ]
    expect(new Set(codes).size).toBe(13)
  })

  it.each([
    ['ACCOUNT_NOT_FOUND', 'NOT_FOUND'],
    ['INVALID_OWNER', 'VALIDATION_ERROR'],
    ['BOOKING_ALREADY_EXISTS', 'CONFLICT'],
    ['BOOKING_NOT_CONFIRMED', 'INVALID_TRANSITION'],
    ['EVALUATION_EXISTS', 'REPORT_NOT_READY'],
    ['INSTALLED_TOOL_SCOPE_DENIED', 'SCOPE_DENIED'],
    ['UPSTREAM_TIMEOUT', 'NETWORK_ERROR'],
  ])('normalizes %s to %s', (legacy, canonical) => {
    expect(normalizeCrmApiErrorCode(legacy)).toBe(canonical)
    expect(new CrmApiError(legacy, 'safe', 'req_test').code).toBe(canonical)
  })
})
