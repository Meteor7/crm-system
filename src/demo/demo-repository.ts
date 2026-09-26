import { demoRequests, evaluations } from '@/api/mock-data'
import { isDemoEngineerOwner, isDemoSalesOwner } from '@/demo/identities'
import type { DemoRequestDto, DemoTrackingDto, EvaluationDto } from '@/types/crm'
import type { StoredDemoArtifact } from './binary-storage'
import type { DemoCommentDto } from '@/types/workspaces'
import { migrateLegacyUserId, migrateOptionalLegacyUserId } from './identity-migration'

const DATABASE_NAME = 'semiconductor-crm-demo'
const STORE_NAME = 'snapshots'
const SNAPSHOT_KEY = 'demo-workflow-v1'

export interface DemoSnapshot {
  version: 1 | 2 | 3 | 4 | 5 | 6 | 7
  demoRequests: DemoRequestDto[]
  evaluations: EvaluationDto[]
  artifacts: StoredDemoArtifact[]
  comments?: DemoCommentDto[]
}

/** The snapshot shape written by the current build; older shapes are migrated on load. */
export const DEMO_SNAPSHOT_VERSION = 7

export function migrateDemoSnapshot(snapshot: DemoSnapshot): DemoSnapshot {
  if (snapshot.version === 6 || snapshot.version === DEMO_SNAPSHOT_VERSION) {
    const migrated = cloneSnapshot(snapshot)
    migrated.comments ??= []
    migrateDemoTestRounds(migrated)
    migrated.version = DEMO_SNAPSHOT_VERSION
    return migrateDemoIdentityReferences(migrated)
  }
  return seedDemoSnapshot()
}

/**
 * v7 introduced test rounds. Snapshots written before then have no `testRound`
 * on Evaluations and no `round` on Test Runs or report artifacts; everything that
 * already existed belongs to round 1, exactly like the Frappe backfill patch.
 */
function migrateDemoTestRounds(snapshot: DemoSnapshot) {
  snapshot.evaluations.forEach((evaluation) => {
    evaluation.testRound ??= 1
    evaluation.customerReviews ??= []
    evaluation.runs.forEach((run) => { run.round ??= 1 })
  })
  snapshot.artifacts.forEach((artifact) => {
    if (artifact.type === 'Test Report' || artifact.type === 'Customer Report') artifact.round ??= 1
  })
}

function migrateDemoIdentityReferences(snapshot: DemoSnapshot): DemoSnapshot {
  snapshot.demoRequests.forEach((request) => {
    request.salesOwner = migrateLegacyUserId(request.salesOwner, 'demoRequest.salesOwner')
    request.createdBy = migrateLegacyUserId(request.createdBy, 'demoRequest.createdBy')
    request.engineerOwner = migrateLegacyUserId(request.engineerOwner, 'demoRequest.engineerOwner')
    request.preparedBy = migrateOptionalLegacyUserId(request.preparedBy, 'demoRequest.preparedBy')
    request.approvedBy = migrateOptionalLegacyUserId(request.approvedBy, 'demoRequest.approvedBy')
    request.tracking.lastProgressActor = migrateLegacyUserId(request.tracking.lastProgressActor, 'demoRequest.tracking.lastProgressActor')
    request.tracking.nextActionOwner = migrateOptionalLegacyUserId(request.tracking.nextActionOwner, 'demoRequest.tracking.nextActionOwner') ?? ''
    request.history.forEach((entry) => { entry.actor = migrateLegacyUserId(entry.actor, 'demoRequest.history.actor') })
    if (request.formData) {
      request.formData.salesContact = migrateLegacyUserId(request.formData.salesContact, 'demoRequest.formData.salesContact')
      request.formData.demoOwner = migrateLegacyUserId(request.formData.demoOwner, 'demoRequest.formData.demoOwner')
    }
  })
  snapshot.evaluations.forEach((evaluation) => { evaluation.owner = migrateLegacyUserId(evaluation.owner, 'evaluation.owner') })
  snapshot.artifacts.forEach((artifact) => { artifact.createdBy = migrateLegacyUserId(artifact.createdBy, 'artifact.createdBy') })
  snapshot.comments?.forEach((comment) => {
    comment.author = migrateLegacyUserId(comment.author, 'demoComment.author')
    comment.mentionedPersonId = migrateOptionalLegacyUserId(comment.mentionedPersonId, 'demoComment.mentionedPersonId')
    comment.mentionedPeople = comment.mentionedPeople?.map((person) => ({
      ...person,
      id: migrateOptionalLegacyUserId(person.id, 'demoComment.mentionedPeople.id') || person.id,
    }))
  })
  return snapshot
}

export interface DemoStorage {
  load(): Promise<DemoSnapshot | null>
  save(snapshot: DemoSnapshot): Promise<void>
}

export interface DemoRepository {
  read(): Promise<DemoSnapshot>
  transact<T>(change: (draft: DemoSnapshot) => T | Promise<T>): Promise<T>
}

const storageQueues = new WeakMap<DemoStorage, Promise<void>>()

function cloneSnapshot(snapshot: DemoSnapshot): DemoSnapshot {
  const cloned = structuredClone(snapshot)
  cloned.artifacts = snapshot.artifacts.map((artifact, index) => ({
    ...cloned.artifacts[index],
    blob: artifact.blob,
  }))
  return cloned
}

function invalidSnapshot(message: string): never {
  throw new Error(`Invalid Demo snapshot: ${message}`)
}

export function validateDemoSnapshot(snapshot: DemoSnapshot) {
  if (snapshot.version !== DEMO_SNAPSHOT_VERSION) invalidSnapshot(`version must be ${DEMO_SNAPSHOT_VERSION}`)
  if (snapshot.demoRequests.length !== 10) invalidSnapshot('expected 10 Demo Requests')
  if (snapshot.evaluations.length !== 6) invalidSnapshot('expected 6 Evaluations')
  if (snapshot.artifacts.length) invalidSnapshot('new seed must not contain artifacts')

  const requestIds = new Set(snapshot.demoRequests.map((request) => request.id))
  const evaluationIds = new Set(snapshot.evaluations.map((evaluation) => evaluation.id))
  if (requestIds.size !== snapshot.demoRequests.length) invalidSnapshot('duplicate Request ID')
  if (evaluationIds.size !== snapshot.evaluations.length) invalidSnapshot('duplicate Evaluation ID')

  for (const request of snapshot.demoRequests) {
    if (!isDemoSalesOwner(request.salesOwner)) invalidSnapshot(`invalid Sales Owner on ${request.id}`)
    if (!isDemoEngineerOwner(request.engineerOwner)) invalidSnapshot(`invalid Engineer Owner on ${request.id}`)
    const linked = snapshot.evaluations.filter((evaluation) => evaluation.demoRequestId === request.id)
    if (request.status === 'Converted') {
      if (linked.length !== 1 || request.evaluationId !== linked[0].id) {
        invalidSnapshot(`invalid Evaluation link on ${request.id}`)
      }
    } else if (linked.length || request.evaluationId) {
      invalidSnapshot(`Request-stage record ${request.id} must not have an Evaluation`)
    }
  }

  for (const evaluation of snapshot.evaluations) {
    const request = snapshot.demoRequests.find((item) => item.id === evaluation.demoRequestId)
    if (!request || request.evaluationId !== evaluation.id) invalidSnapshot(`orphan Evaluation ${evaluation.id}`)
    if (request.engineerOwner !== evaluation.owner) invalidSnapshot(`owner mismatch on ${evaluation.id}`)
  }

  const countRequests = (field: 'salesOwner' | 'engineerOwner', value: string) =>
    snapshot.demoRequests.filter((request) => request[field] === value).length
  if (countRequests('engineerOwner', 'person077@crm.example.invalid') !== 5 || countRequests('engineerOwner', 'person053@crm.example.invalid') !== 5) {
    invalidSnapshot('engineer distribution must be 5/5')
  }
  if (countRequests('salesOwner', 'person002@crm.example.invalid') !== 5 || countRequests('salesOwner', 'person005@crm.example.invalid') !== 5) {
    invalidSnapshot('sales distribution must be 5/5')
  }
  if (snapshot.evaluations.filter((evaluation) => ['Accepted', 'Rejected'].includes(evaluation.status)).length !== 2) {
    invalidSnapshot('expected 2 archived Evaluations')
  }
}

function trackingDefaults(request: DemoRequestDto): DemoTrackingDto {
  const latest = [...request.history].sort((left, right) => right.at.localeCompare(left.at))[0]
  return {
    lastProgressAt: latest?.at || request.updatedAt || request.createdAt,
    lastProgressSummary: latest?.comment || '创建 Demo Request',
    lastProgressActor: latest?.actor || request.createdBy,
    nextAction: '',
    nextActionOwner: '',
    nextActionDue: '',
  }
}

export function seedDemoSnapshot(): DemoSnapshot {
  const requests = demoRequests.map((request) => ({
    ...structuredClone(request),
    customerExpectedDate: request.targetDate,
    tracking: { ...trackingDefaults(request), ...request.tracking },
    history: request.status !== 'Draft' && !request.history.some((item) => item.to === 'Engineer Review')
      ? [...request.history, { at: request.createdAt, actor: request.createdBy, from: 'Draft' as const, to: 'Engineer Review' as const, comment: '提交工程评估' }]
      : structuredClone(request.history),
  }))
  const snapshot: DemoSnapshot = {
    version: DEMO_SNAPSHOT_VERSION,
    demoRequests: requests,
    evaluations: evaluations.map((evaluation) => ({
      ...structuredClone(evaluation),
      demoRequestId: evaluation.demoRequestId ?? requests.find((request) =>
        request.accountId === evaluation.accountId && request.requirementId === evaluation.requirementId,
      )?.id,
      testRunDeadline: evaluation.plannedEnd,
      reportStatus: 'Not Ready',
      reportVersion: 0,
    })),
    artifacts: [],
    comments: [
      {
        id: 'CMT-001',
        demoRequestId: 'DR-105',
        author: 'Demo Staff 01',
        role: 'Sales',
        body: '客户希望本周五前确认测试窗口，请评估样片风险。',
        createdAt: '2026-07-28T10:18:00+08:00',
      },
      {
        id: 'CMT-002',
        demoRequestId: 'DR-105',
        author: '演示员工14',
        role: 'Engineer',
        body: 'Patterned wafer 已确认，建议先完成 Wafer Preparation 再进入内部评审。',
        createdAt: '2026-07-28T10:26:00+08:00',
      },
      {
        id: 'CMT-003',
        demoRequestId: 'DR-105',
        author: '演示员工24',
        role: 'Manager',
        body: '内部结论确认后再对客户发布，避免提前承诺。',
        createdAt: '2026-07-28T10:34:00+08:00',
      },
    ],
  }
  const migrated = migrateDemoIdentityReferences(snapshot)
  validateDemoSnapshot(migrated)
  return migrated
}

export function createMemoryDemoStorage(): DemoStorage {
  let snapshot: DemoSnapshot | null = null
  return {
    async load() {
      return snapshot ? cloneSnapshot(snapshot) : null
    },
    async save(nextSnapshot) {
      snapshot = cloneSnapshot(nextSnapshot)
    },
  }
}

export function createDemoRepository(storage: DemoStorage, seed: () => DemoSnapshot): DemoRepository {
  const ensure = async () => {
    const existing = await storage.load()
    if (existing) {
      const migrated = migrateDemoSnapshot(existing)
      if (existing.version !== migrated.version) await storage.save(migrated)
      return migrated
    }
    const initial = cloneSnapshot(seed())
    validateDemoSnapshot(initial)
    await storage.save(initial)
    return initial
  }

  return {
    read: async () => cloneSnapshot(await ensure()),
    transact: async (change) => {
      const queue = storageQueues.get(storage) ?? Promise.resolve()
      const operation = queue.then(async () => {
        const draft = await ensure()
        const result = await change(draft)
        await storage.save(draft)
        return result
      })
      storageQueues.set(storage, operation.then(() => undefined, () => undefined))
      return operation
    },
  }
}

function openDemoDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, 1)
    request.onerror = () => reject(request.error)
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) {
        request.result.createObjectStore(STORE_NAME)
      }
    }
    request.onsuccess = () => resolve(request.result)
  })
}

function readRequest<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onerror = () => reject(request.error)
    request.onsuccess = () => resolve(request.result)
  })
}

function completeTransaction(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.onerror = () => reject(transaction.error)
    transaction.onabort = () => reject(transaction.error)
    transaction.oncomplete = () => resolve()
  })
}

function createIndexedDbDemoStorage(): DemoStorage {
  let database: Promise<IDBDatabase> | null = null
  const getDatabase = () => {
    database ??= openDemoDatabase()
    return database
  }
  return {
    async load() {
      const db = await getDatabase()
      const transaction = db.transaction(STORE_NAME, 'readonly')
      const result = await readRequest(transaction.objectStore(STORE_NAME).get(SNAPSHOT_KEY))
      await completeTransaction(transaction)
      return result ? cloneSnapshot(result as DemoSnapshot) : null
    },
    async save(snapshot) {
      const db = await getDatabase()
      const transaction = db.transaction(STORE_NAME, 'readwrite')
      transaction.objectStore(STORE_NAME).put(cloneSnapshot(snapshot), SNAPSHOT_KEY)
      await completeTransaction(transaction)
    },
  }
}

let sharedRepository: DemoRepository | null = null

export function getSharedDemoRepository(): DemoRepository {
  sharedRepository ??= createDemoRepository(createIndexedDbDemoStorage(), seedDemoSnapshot)
  return sharedRepository
}
