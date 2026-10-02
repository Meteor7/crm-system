import { describe, expect, it, vi } from 'vitest'
import { createFrappeApi } from './frappe-adapter'

const expectedModified = '2026-09-28T11:00:00.000000Z'

function frappeResponse(message: unknown, status = 200) {
  return new Response(JSON.stringify({ message }), { status, headers: { 'Content-Type': 'application/json' } })
}

// Allowed stages, the required reason, history, the untouched Opportunity and rollback are
// exercised by test_evaluation_api against real Frappe. These tests pin its HTTP boundary.
describe('Frappe Demo Test termination contract', () => {
  it('posts the reason and the Evaluation version and returns the terminated Demo Test', async () => {
    const returned = {
      id: 'EVAL-103', status: 'Rejected', acceptance: 'Pending',
      terminationReason: 'Customer paused the project', modified: '2026-09-28T11:00:01.000000Z',
    }
    const fetchImpl = vi.fn().mockResolvedValue(frappeResponse({ data: returned, meta: { requestId: 'terminate' }, warnings: [] }))

    const result = await createFrappeApi({ fetchImpl }).terminateEvaluation('EVAL-103', 'Customer paused the project', expectedModified)

    expect(result.data).toEqual(returned)
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/method/rayher_crm.api.v1.evaluations.terminate_evaluation')
    expect(init.method).toBe('POST')
    expect(Object.fromEntries(new URLSearchParams(init.body as string))).toEqual({
      id: 'EVAL-103', reason: 'Customer paused the project', expectedModified,
    })
  })

  it.each(['VERSION_CONFLICT', 'INVALID_TRANSITION'])('surfaces %s without retrying the write', async (code) => {
    const fetchImpl = vi.fn().mockResolvedValue(frappeResponse({
      error: { code, message: 'Refused', retryable: false }, meta: { requestId: 'terminate-refused' },
    }, 409))

    await expect(createFrappeApi({ fetchImpl }).terminateEvaluation('EVAL-103', 'Stop', expectedModified))
      .rejects.toMatchObject({ code, requestId: 'terminate-refused' })
    expect(fetchImpl).toHaveBeenCalledTimes(1)
  })
})
