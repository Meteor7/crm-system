import { describe, expect, it, vi } from 'vitest'
import { createMockApi } from './mock-adapter'
import { createMemorySalesRepository } from '@/demo/sales-repository'

function setup() {
  const salesRepository = createMemorySalesRepository()
  const stored = salesRepository.snapshot.opportunities.find(row => row.id === 'OPP-001')!
  stored.probabilityLevel = 'committed'
  stored.probabilityHistory = []
  const options = { latency: 0, salesRepository, today: '2026-09-22' }
  const owner = createMockApi({ ...options, role: 'Sales', userName: 'Demo Staff 01' })
  const manager = createMockApi({ ...options, role: 'Manager' })
  const current = async () => (await owner.getStrategyOpportunity(stored.id)).data
  const lower = async () => (await owner.updateStrategyOpportunity(stored.id, {
    probabilityLevel: 'upside', probabilityReason: 'Budget delayed', probabilityActionPlan: 'Meet procurement',
  }, (await current()).modified)).data
  return { owner, manager, current, lower, salesRepository, stored, options }
}

describe('probability recovery plans', () => {
  it('preserves the old plan and audit when local persistence fails', async () => {
    const { owner, lower, current, salesRepository } = setup()
    const opportunity = await lower(), event = opportunity.probabilityHistory[0]!
    vi.spyOn(salesRepository, 'save').mockImplementationOnce(() => { throw new Error('storage full') })
    await expect(owner.saveProbabilityRecovery(opportunity.id, event.id, { plan: 'Lost draft', recoveryModified: event.recovery!.modified }, opportunity.modified!)).rejects.toThrow('storage full')
    expect((await current()).probabilityHistory[0]!.recovery).toEqual(event.recovery)
    expect((await owner.saveProbabilityRecovery(opportunity.id, event.id, { plan: 'Retry', recoveryModified: event.recovery!.modified }, opportunity.modified!)).data.plan).toBe('Retry')
  })
  it('rolls back an action or plan when local persistence fails, allowing a retry', async () => {
    const { owner, lower, current, salesRepository } = setup()
    const opportunity = await lower(), event = opportunity.probabilityHistory[0]!
    const save = vi.spyOn(salesRepository, 'save')
    save.mockImplementationOnce(() => { throw new Error('storage full') })
    await expect(owner.saveProbabilityRecovery(opportunity.id, event.id, { plan: 'New plan', recoveryModified: event.recovery!.modified }, opportunity.modified!)).rejects.toThrow('storage full')
    expect((await current()).probabilityHistory[0]!.recovery).toEqual(event.recovery)
    const input = { actionTaken: 'Met buyer', recoveryModified: event.recovery!.modified }
    save.mockImplementationOnce(() => { throw new Error('storage full') })
    await expect(owner.recordProbabilityRecoveryAction(opportunity.id, event.id, input, opportunity.modified!)).rejects.toThrow('storage full')
    expect((await current()).probabilityHistory[0]!.recovery).toEqual(event.recovery)
    expect((await owner.recordProbabilityRecoveryAction(opportunity.id, event.id, input, opportunity.modified!)).data.state).toBe('handled')
  })
  it('only lets the current owner record an action and keeps separate pending downgrades', async () => {
    const { owner, manager, lower, current } = setup()
    const opportunity = await lower(), event = opportunity.probabilityHistory[0]!
    const payload = { actionTaken: 'Met the buyer', recoveryModified: event.recovery!.modified }
    await expect(manager.recordProbabilityRecoveryAction(opportunity.id, event.id, payload, opportunity.modified!))
      .rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
    await expect(owner.recordProbabilityRecoveryAction(opportunity.id, event.id, { ...payload, actionTaken: ' ' }, opportunity.modified!))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    const acted = (await owner.recordProbabilityRecoveryAction(opportunity.id, event.id, payload, opportunity.modified!)).data
    expect(acted).toMatchObject({ state: 'handled', actedBy: opportunity.owner, actionTaken: 'Met the buyer', history: [
      { kind: 'ActionRecorded', actionTaken: 'Met the buyer', plan: 'Meet procurement' }, { kind: 'Created' },
    ] })
    await expect(owner.recordProbabilityRecoveryAction(opportunity.id, event.id, payload, opportunity.modified!))
      .rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
    await expect(owner.recordProbabilityRecoveryAction(opportunity.id, event.id, { ...payload, recoveryModified: acted.modified }, opportunity.modified!))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION' })
    const updated = (await manager.saveProbabilityRecovery(opportunity.id, event.id, { plan: 'Clarified plan', recoveryModified: acted.modified }, opportunity.modified!)).data
    expect(updated).toMatchObject({ state: 'handled', actedAt: acted.actedAt, actionTaken: acted.actionTaken })
    await owner.updateStrategyOpportunity(opportunity.id, { probabilityLevel: 'pipeline', probabilityReason: 'Delayed again', probabilityActionPlan: 'Escalate' }, opportunity.modified)
    expect((await current()).probabilityHistory.map(row => row.recovery!.state)).toEqual(['pending', 'handled'])
  })

  it('does not clear a warning using a plan version changed by another browser', async () => {
    const { owner, options, lower, current } = setup()
    const opportunity = await lower(), event = opportunity.probabilityHistory[0]!
    const other = createMockApi({ ...options, role: 'Sales', userName: 'Demo Staff 01' })
    await other.saveProbabilityRecovery(opportunity.id, event.id, { plan: 'Other plan', recoveryModified: event.recovery!.modified }, opportunity.modified!)
    await expect(owner.recordProbabilityRecoveryAction(opportunity.id, event.id, { actionTaken: 'Acted on old plan', recoveryModified: event.recovery!.modified }, opportunity.modified!))
      .rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
    expect((await current()).probabilityHistory[0]!.recovery!.state).toBe('pending')
  })

  it('requires a plan atomically and leaves no event or version change on validation failure', async () => {
    const { owner, current } = setup()
    const before = await current()
    for (const probabilityActionPlan of ['', '  ', 'a'.repeat(4001), [] as unknown as string]) {
      await expect(owner.updateStrategyOpportunity(before.id, {
        probabilityLevel: 'upside', probabilityReason: 'Budget delayed', probabilityActionPlan,
      }, before.modified)).rejects.toMatchObject({ code: 'VALIDATION_ERROR', fieldErrors: { probabilityActionPlan: expect.any(String) } })
      expect(await current()).toEqual(before)
    }
  })

  it('records an initial plan, then manager revisions without rewriting the reason or creating downgrade events', async () => {
    const { lower, manager, current } = setup()
    const lowered = await lower()
    const event = lowered.probabilityHistory[0]!
    expect(event.recovery).toMatchObject({ plan: 'Meet procurement', history: [{ kind: 'Created', actor: lowered.owner }] })
    const edited = (await manager.saveProbabilityRecovery(lowered.id, event.id, {
      plan: '  Meet procurement and technical buyer  ', recoveryModified: event.recovery!.modified,
    }, lowered.modified!)).data
    expect(edited.plan).toBe('Meet procurement and technical buyer')
    expect(edited.history.map(row => row.plan)).toEqual(['Meet procurement and technical buyer', 'Meet procurement'])
    expect(edited.history[0]!.actor).toBe('person029@crm.example.invalid')
    expect(edited.modified).not.toBe(event.recovery!.modified)
    const final = await current()
    expect(final.probabilityHistory).toHaveLength(1)
    expect(final.probabilityHistory[0]).toMatchObject({ reason: event.reason, actor: event.actor, at: event.at })
  })

  it('rejects a repeated downgrade save and never creates a second event', async () => {
    const { owner, lower, current } = setup()
    const old = await current()
    await lower()
    await expect(owner.updateStrategyOpportunity(old.id, {
      probabilityLevel: 'upside', probabilityReason: 'Budget delayed', probabilityActionPlan: 'Meet procurement',
    }, old.modified)).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
    expect((await current()).probabilityHistory).toHaveLength(1)
  })

  it('rejects stale plans across separate API clients, even with same-tick writes', async () => {
    const { lower, owner, options, current } = setup()
    const lowered = await lower(), event = lowered.probabilityHistory[0]!
    const otherClient = createMockApi({ ...options, role: 'Sales', userName: 'Demo Staff 01' })
    const first = (await otherClient.saveProbabilityRecovery(lowered.id, event.id, { plan: 'New plan', recoveryModified: event.recovery!.modified }, lowered.modified!)).data
    await expect(owner.saveProbabilityRecovery(lowered.id, event.id, { plan: 'Stale plan', recoveryModified: event.recovery!.modified }, lowered.modified!))
      .rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
    const unchanged = (await owner.saveProbabilityRecovery(lowered.id, event.id, { plan: ' New plan ', recoveryModified: first.modified }, lowered.modified!)).data
    expect(unchanged).toEqual(first)
    expect((await current()).probabilityHistory[0]!.recovery!.history).toHaveLength(2)
  })

  it('lets only one racing legacy-plan creation succeed', async () => {
    const { lower, owner, manager, stored, current } = setup()
    const lowered = await lower(), event = lowered.probabilityHistory[0]!
    stored.probabilityHistory[0]!.recovery = null
    const results = await Promise.allSettled([owner, manager].map(api => api.saveProbabilityRecovery(lowered.id, event.id, {
      plan: 'Recorded at review', recoveryModified: null,
    }, lowered.modified!)))
    expect(results.map(row => row.status).sort()).toEqual(['fulfilled', 'rejected'])
    expect((await current()).probabilityHistory[0]!.recovery!.history).toHaveLength(1)
  })

  it('does not create plans on initial assignment, unchanged levels or upgrades', async () => {
    const { owner, stored, current } = setup()
    stored.probabilityLevel = ''
    for (const probabilityLevel of ['pipeline', 'pipeline', 'upside'] as const) {
      await owner.updateStrategyOpportunity(stored.id, { probabilityLevel }, (await current()).modified)
    }
    const result = await current()
    expect(result.probabilityHistory).toHaveLength(2)
    expect(result.probabilityHistory.every(event => !event.recovery)).toBe(true)
    await expect(owner.saveProbabilityRecovery(result.id, result.probabilityHistory[0]!.id, { plan: 'Invalid', recoveryModified: null }, result.modified!))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION' })
  })

  it('keeps separate plans for successive downgrades', async () => {
    const { owner, lower } = setup()
    const first = await lower()
    const second = (await owner.updateStrategyOpportunity(first.id, {
      probabilityLevel: 'pipeline', probabilityReason: 'Budget reduced again', probabilityActionPlan: 'Agree a phased delivery',
    }, first.modified)).data
    expect(second.probabilityHistory.map(event => event.recovery!.plan)).toEqual(['Agree a phased delivery', 'Meet procurement'])
  })

  it('refuses unrelated users, cross-parent event ids and missing parent versions', async () => {
    const { owner, lower, options } = setup()
    const opportunity = await lower(), event = opportunity.probabilityHistory[0]!
    const input = { plan: 'New plan', recoveryModified: event.recovery!.modified }
    const other = createMockApi({ ...options, role: 'Sales', userName: 'Demo Staff 02' })
    const engineer = createMockApi({ ...options, role: 'Engineer' })
    await expect(other.saveProbabilityRecovery(opportunity.id, event.id, input, opportunity.modified!)).rejects.toMatchObject({ code: 'SCOPE_DENIED' })
    await expect(engineer.saveProbabilityRecovery(opportunity.id, event.id, input, opportunity.modified!)).rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
    await expect(owner.saveProbabilityRecovery(opportunity.id, 'not-this-event', input, opportunity.modified!)).rejects.toMatchObject({ code: 'NOT_FOUND' })
    await expect(owner.saveProbabilityRecovery(opportunity.id, event.id, input, '')).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
  })
})
