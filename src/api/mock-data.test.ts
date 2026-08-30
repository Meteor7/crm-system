import { describe, expect, it } from 'vitest'
import { demoRequests, evaluations, requirements } from './mock-data'

describe('delivery fixture integrity', () => {
  it('keeps request sources inside the same customer account', () => {
    for (const request of demoRequests) {
      if (!request.requirementId) continue
      const requirement = requirements.find((item) => item.id === request.requirementId)
      expect(requirement, `${request.id} requirement exists`).toBeTruthy()
      expect(requirement?.accountId, `${request.id} requirement account`).toBe(request.accountId)
    }
  })

  it('only links evaluations to reciprocally converted requests', () => {
    for (const evaluation of evaluations) {
      if (!evaluation.demoRequestId) continue
      const request = demoRequests.find((item) => item.id === evaluation.demoRequestId)
      expect(request, `${evaluation.id} request exists`).toBeTruthy()
      expect(request?.accountId, `${evaluation.id} request account`).toBe(evaluation.accountId)
      expect(request?.status, `${evaluation.id} request status`).toBe('Converted')
      expect(request?.evaluationId, `${evaluation.id} reciprocal link`).toBe(evaluation.id)
    }
  })
})
