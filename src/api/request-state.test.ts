import { describe, expect, it } from 'vitest'
import { CrmApiError } from './contracts'
import { mapRequestError, readRequestMeta } from './request-state'

describe('request state mapping', () => {
  it('marks expired or warned responses as partial/stale', () => {
    const state = readRequestMeta({
      data: [], warnings: ['上游只返回部分结果'],
      meta: { requestId: 'req_meta_1', staleAt: '2026-07-17T09:00:00+08:00' },
    }, new Date('2026-07-17T10:00:00+08:00'))

    expect(state.stale).toBe(true)
    expect(state.requestId).toBe('req_meta_1')
    expect(state.message).toContain('部分结果')
  })

  it('maps permission failures without losing the request ID', () => {
    const state = mapRequestError(new CrmApiError('PERMISSION_DENIED', '无权查看团队客户', 'req_denied_1', false))

    expect(state.denied).toBe(true)
    expect(state.requestId).toBe('req_denied_1')
    expect(state.retryable).toBe(false)
  })

  it('maps record-scope failures to the denied state', () => {
    const state = mapRequestError(new CrmApiError('SCOPE_DENIED', '无权访问该客户范围', 'req_scope_1', false))

    expect(state).toMatchObject({ denied: true, requestId: 'req_scope_1', retryable: false })
  })
})
