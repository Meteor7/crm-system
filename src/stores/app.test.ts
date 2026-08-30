import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { useAppStore } from './app'
import { useNotificationStore } from './notifications'

describe('app demo identity session', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('switches the active mock session atomically', async () => {
    const store = useAppStore()
    await store.switchDemoIdentity('sales-user')

    expect(store.identityId).toBe('sales-user')
    expect(store.identityRevision).toBe(1)
    expect(store.bootstrap?.user.name).toBe('Demo Staff 01')
    expect(store.bootstrap?.user.role).toBe('Sales')
    expect(store.bootstrap?.capabilities).not.toContain('procedure:view')
    const accounts = await store.activeApi.listAccounts({ page: 1, pageSize: 20 })
    expect(accounts.data.items).toHaveLength(3)
    expect(accounts.data.items).toContainEqual(expect.objectContaining({ owner: 'person002@crm.example.invalid' }))
    expect(accounts.data.items).not.toContainEqual(expect.objectContaining({ owner: 'person005@crm.example.invalid' }))
  })

  it('ignores a stale bootstrap response after a newer identity switch', async () => {
    const store = useAppStore()
    const baseApi = createMockApi({ latency: 0, role: 'Manager' })
    const staleBootstrap = await baseApi.getBootstrap()
    let resolveBootstrap!: (value: typeof staleBootstrap) => void
    const staleApi = {
      ...baseApi,
      getBootstrap: vi.fn(() => new Promise<typeof staleBootstrap>((resolve) => { resolveBootstrap = resolve })),
    }

    const pendingBootstrap = store.loadBootstrap(staleApi)
    await Promise.resolve()
    await store.switchDemoIdentity('fae')
    resolveBootstrap(staleBootstrap)
    await pendingBootstrap

    expect(store.bootstrap?.user.role).toBe('Engineer')
    expect(store.identityId).toBe('fae')
    expect(store.loading).toBe(false)
  })
  it('does not let a stale Sales API replace the active Engineer session', async () => {
    const store = useAppStore()
    await store.switchDemoIdentity('fae')
    const staleSalesApi = createMockApi({
      latency: 0,
      role: 'Sales',
      userId: 'person002@crm.example.invalid',
      userName: 'Demo Staff 01',
    })

    await store.loadBootstrap(staleSalesApi)

    expect(store.bootstrap?.user.role).toBe('Engineer')
    await expect(store.activeApi.listVisits({ page: 1, pageSize: 20 })).rejects.toThrow()
  })
  it('uses the administrator as the safe default identity', async () => {
    const store = useAppStore()
    await store.switchDemoIdentity('not-found')

    expect(store.identityId).toBe('administrator')
    expect(store.bootstrap?.user.role).toBe('Manager')
  })

  it('replaces requirement notifications with the active identity scope', async () => {
    const store = useAppStore()
    const notifications = useNotificationStore()

    await store.switchDemoIdentity('sales-user')
    expect(notifications.items.map((item) => item.id)).toEqual([
      'requirement-req-001',
      'requirement-req-002',
      'requirement-req-003',
    ])

    await store.switchDemoIdentity('fae')
    expect(notifications.items.map((item) => item.id)).toEqual([
      'requirement-req-001',
      'requirement-req-002',
      'requirement-req-004',
    ])
  })
})
