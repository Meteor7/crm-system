import { describe, expect, it } from 'vitest'
import {
  createDemoRepository,
  createMemoryDemoStorage,
  migrateDemoSnapshot,
  seedDemoSnapshot,
  validateDemoSnapshot,
} from './demo-repository'

describe('demo repository', () => {
  it('shares one persisted snapshot across repository clients', async () => {
    const storage = createMemoryDemoStorage()
    const first = createDemoRepository(storage, seedDemoSnapshot)

    await first.transact((draft) => {
      draft.demoRequests[0].customerExpectedDate = '2026-08-20'
    })

    const second = createDemoRepository(storage, seedDemoSnapshot)
    expect((await second.read()).demoRequests[0].customerExpectedDate).toBe('2026-08-20')
  })

  it('persists artifact Blobs', async () => {
    const storage = createMemoryDemoStorage()
    const repository = createDemoRepository(storage, seedDemoSnapshot)

    await repository.transact((draft) => {
      draft.artifacts.push({
        id: 'ART-001', demoRequestId: 'DR-105', evaluationId: 'EVAL-101',
        type: 'Test Report', fileName: 'report.pdf', mimeType: 'application/pdf',
        blob: new Blob(['pdf']), version: 1, createdBy: 'person029@crm.example.invalid', createdAt: '2026-07-22T10:30:00+08:00',
        visibility: 'Customer Review',
      })
    })

    expect((await repository.read()).artifacts[0].blob.size).toBe(3)
  })

  it('seeds exactly ten linked Demo records with balanced real owners', () => {
    const snapshot = seedDemoSnapshot()

    expect(snapshot.version).toBe(6)
    expect(snapshot.demoRequests.map((item) => item.id)).toEqual([
      'DR-101', 'DR-102', 'DR-103', 'DR-104', 'DR-105',
      'DR-106', 'DR-107', 'DR-108', 'DR-109', 'DR-110',
    ])
    expect(snapshot.evaluations.map((item) => item.id)).toEqual([
      'EVAL-101', 'EVAL-102', 'EVAL-103', 'EVAL-104', 'EVAL-105', 'EVAL-106',
    ])
    expect(snapshot.artifacts).toEqual([])
    expect(snapshot.demoRequests.filter((item) => item.engineerOwner === 'person077@crm.example.invalid')).toHaveLength(5)
    expect(snapshot.demoRequests.filter((item) => item.engineerOwner === 'person053@crm.example.invalid')).toHaveLength(5)
    expect(snapshot.demoRequests.filter((item) => item.salesOwner === 'person002@crm.example.invalid')).toHaveLength(5)
    expect(snapshot.demoRequests.filter((item) => item.salesOwner === 'person005@crm.example.invalid')).toHaveLength(5)
    expect(snapshot.evaluations.filter((item) => ['Accepted', 'Rejected'].includes(item.status))).toHaveLength(2)
    expect(snapshot.comments?.filter((item) => item.demoRequestId === 'DR-105').length).toBeGreaterThanOrEqual(2)
    expect(snapshot.evaluations.some((item) => item.status === 'On Hold' as never)).toBe(false)
    expect(snapshot.demoRequests.some((item) => 'questions' in item)).toBe(false)
  })

  it('keeps each Evaluation linked one-to-one with the same engineer owner', () => {
    const snapshot = seedDemoSnapshot()

    for (const evaluation of snapshot.evaluations) {
      const request = snapshot.demoRequests.find((item) => item.id === evaluation.demoRequestId)
      expect(request?.evaluationId).toBe(evaluation.id)
      expect(request?.engineerOwner).toBe(evaluation.owner)
    }
    for (const requestId of ['DR-101', 'DR-102', 'DR-103', 'DR-104']) {
      const request = snapshot.demoRequests.find((item) => item.id === requestId)
      expect(request?.evaluationId).toBeUndefined()
      expect(snapshot.evaluations.some((item) => item.demoRequestId === requestId)).toBe(false)
    }
  })

  it('replaces every pre-v6 Demo snapshot instead of retaining legacy cases', () => {
    const legacy = seedDemoSnapshot()
    ;(legacy as { version: number }).version = 5
    legacy.demoRequests[0].id = 'DR-LEGACY'
    legacy.demoRequests[0].engineerOwner = 'FAE Mia'
    legacy.artifacts.push({
      id: 'ART-LEGACY', demoRequestId: 'DR-LEGACY',
      type: 'Demo Request DOCX', fileName: 'legacy.docx',
      mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      blob: new Blob(['legacy']), version: 1, createdBy: 'Legacy User',
      createdAt: '2026-07-01T10:00:00+08:00', visibility: 'Internal',
    })

    const migrated = migrateDemoSnapshot(legacy)

    expect(migrated.version).toBe(6)
    expect(migrated.demoRequests).toHaveLength(10)
    expect(migrated.demoRequests.some((item) => item.id === 'DR-LEGACY')).toBe(false)
    expect(migrated.demoRequests.some((item) => item.engineerOwner === 'FAE Mia')).toBe(false)
    expect(migrated.artifacts).toEqual([])
  })

  it('keeps existing v6 snapshots readable when comment storage is missing', () => {
    const existing = seedDemoSnapshot()
    delete existing.comments

    expect(migrateDemoSnapshot(existing).comments).toEqual([])
  })

  it('rejects malformed v6 snapshots before they are persisted', () => {
    const invalid = seedDemoSnapshot()
    invalid.demoRequests[0].engineerOwner = 'FAE Team'

    expect(() => validateDemoSnapshot(invalid)).toThrow('Invalid Demo snapshot')
  })

  it('serializes writes from one repository client', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    const order: string[] = []

    await Promise.all([
      repository.transact(async (draft) => {
        await Promise.resolve()
        draft.demoRequests[0].managerComment = 'first'
        order.push('first')
      }),
      repository.transact((draft) => {
        draft.demoRequests[0].managerComment += ' second'
        order.push('second')
      }),
    ])

    expect(order).toEqual(['first', 'second'])
    expect((await repository.read()).demoRequests[0].managerComment).toBe('first second')
  })

  it('serializes writes across repository wrappers sharing one storage', async () => {
    const storage = createMemoryDemoStorage()
    const first = createDemoRepository(storage, seedDemoSnapshot)
    const second = createDemoRepository(storage, seedDemoSnapshot)
    let releaseFirst!: () => void
    let markStarted!: () => void
    const firstStarted = new Promise<void>((resolve) => { markStarted = resolve })
    const firstGate = new Promise<void>((resolve) => { releaseFirst = resolve })

    const firstWrite = first.transact(async (draft) => {
      draft.demoRequests[0].managerComment = 'first'
      markStarted()
      await firstGate
    })
    await firstStarted
    const secondWrite = second.transact((draft) => {
      draft.demoRequests[0].managerComment += ' second'
    })
    await Promise.resolve()
    releaseFirst()
    await Promise.all([firstWrite, secondWrite])

    expect((await first.read()).demoRequests[0].managerComment).toBe('first second')
  })

  it('continues persisting transactions after one transaction throws', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    const original = (await repository.read()).demoRequests[0].managerComment

    await expect(repository.transact((draft) => {
      draft.demoRequests[0].managerComment = 'must roll back'
      throw new Error('failed change')
    })).rejects.toThrow('failed change')

    expect((await repository.read()).demoRequests[0].managerComment).toBe(original)

    await repository.transact((draft) => {
      draft.demoRequests[0].managerComment = 'persisted after failure'
    })

    expect((await repository.read()).demoRequests[0].managerComment).toBe('persisted after failure')
  })
})
