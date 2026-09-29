import { describe, expect, it, vi } from 'vitest'
import { createFrappeApi } from './frappe-adapter'

const planned = { date: '2026-08-05', lot: 'JC-CHIPLET-072', wafers: 5, capture: null, falsePositive: null, wph: null, summary: '' }
const expectedModified = '2026-09-28T11:00:00.000000Z'

function success(data: unknown) {
  return new Response(JSON.stringify({ message: { data, meta: { requestId: 'run-update' }, warnings: [] } }), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  })
}

// State transitions, scope, rollback and concurrent versions are exercised by
// test_evaluation_api against real Frappe. These tests pin its HTTP boundary.
describe('Frappe Planned Test Run contract', () => {
  it.each([
    ['reschedule', planned, 'Planned'],
    ['complete', { ...planned, capture: 95, falsePositive: 2, wph: 40, summary: 'Repeatable' }, 'Completed'],
  ] as const)('posts %s to the existing run with the Evaluation version', async (_label, fields, status) => {
    const returned = { id: 'EVAL-103', modified: '2026-09-28T11:00:01.000000Z', runs: [{ id: 'CUSTOMER04-R02', ...fields, status }] }
    const fetchImpl = vi.fn().mockResolvedValue(success(returned))
    const api = createFrappeApi({ fetchImpl })
    const input = { ...fields, expectedModified }
    expect((await api.updateEvaluationRun('EVAL-103', 'CUSTOMER04-R02', input)).data).toEqual(returned)
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/method/rayher_crm.api.v1.evaluations.update_evaluation_run')
    expect(init.method).toBe('POST')
    expect(Object.fromEntries(new URLSearchParams(init.body as string))).toEqual({ id: 'EVAL-103', runId: 'CUSTOMER04-R02', input: JSON.stringify(input) })
  })

  it('posts cancellation reason and version without synthesizing local state', async () => {
    const returned = { id: 'EVAL-103', wafers: 5, runs: [{ id: 'CUSTOMER04-R02', status: 'Cancelled', summary: 'Late wafers' }] }
    const fetchImpl = vi.fn().mockResolvedValue(success(returned))
    const input = { reason: 'Late wafers', expectedModified }
    expect((await createFrappeApi({ fetchImpl }).cancelEvaluationRun('EVAL-103', 'CUSTOMER04-R02', input)).data).toEqual(returned)
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/method/rayher_crm.api.v1.evaluations.cancel_evaluation_run')
    expect(init.method).toBe('POST')
    expect(Object.fromEntries(new URLSearchParams(init.body as string))).toEqual({ id: 'EVAL-103', runId: 'CUSTOMER04-R02', input: JSON.stringify(input) })
  })

  it.each(['update', 'cancel'] as const)('surfaces a server version conflict on %s without retrying a write', async (method) => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({ message: {
      error: { code: 'VERSION_CONFLICT', message: 'Reload this Evaluation.', retryable: false },
      meta: { requestId: 'stale-run' },
    } }), { status: 409, headers: { 'Content-Type': 'application/json' } }))
    const api = createFrappeApi({ fetchImpl })
    const pending = method === 'update'
      ? api.updateEvaluationRun('EVAL-103', 'CUSTOMER04-R02', { ...planned, expectedModified })
      : api.cancelEvaluationRun('EVAL-103', 'CUSTOMER04-R02', { reason: 'Late wafers', expectedModified })
    await expect(pending).rejects.toMatchObject({ code: 'VERSION_CONFLICT', requestId: 'stale-run' })
    expect(fetchImpl).toHaveBeenCalledTimes(1)
  })
})
