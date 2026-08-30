import { describe, expect, it } from 'vitest'
import type { StoredContactFile } from './binary-storage'
import { createMemoryContactFileRepository } from './contact-file-repository'

function contactFile(id: string, contactId: string, content = id): StoredContactFile {
  const blob = new Blob([content], { type: 'application/pdf' })
  return {
    id,
    contactId,
    fileName: `${id}.pdf`,
    mimeType: blob.type,
    size: blob.size,
    uploadedAt: '2026-07-29T10:00:00+08:00',
    uploadedBy: 'Test User',
    blob,
  }
}

describe('Contact file repository', () => {
  it('stores and reads Contact-scoped Blobs', async () => {
    const repository = createMemoryContactFileRepository()
    await repository.save(contactFile('CF-001', 'CON-001', 'contact file'))

    const listed = await repository.list('CON-001')
    const stored = await repository.get('CF-001')

    expect(listed.map((file) => file.id)).toEqual(['CF-001'])
    expect(await stored?.blob.text()).toBe('contact file')
    expect(await repository.list('CON-002')).toEqual([])
  })

  it('reassigns files during merge and removes them during hard delete', async () => {
    const repository = createMemoryContactFileRepository([
      contactFile('CF-001', 'CON-DUPLICATE'),
      contactFile('CF-002', 'CON-DUPLICATE'),
      contactFile('CF-003', 'CON-OTHER'),
    ])

    await repository.reassignContact('CON-DUPLICATE', 'CON-SURVIVOR')
    expect((await repository.list('CON-SURVIVOR')).map((file) => file.id)).toEqual(['CF-001', 'CF-002'])
    expect(await repository.list('CON-DUPLICATE')).toEqual([])

    await repository.removeForContact('CON-SURVIVOR')
    expect(await repository.list('CON-SURVIVOR')).toEqual([])
    expect((await repository.list('CON-OTHER')).map((file) => file.id)).toEqual(['CF-003'])
  })

  it('removes one file without affecting other Contact files', async () => {
    const repository = createMemoryContactFileRepository([
      contactFile('CF-001', 'CON-001'),
      contactFile('CF-002', 'CON-001'),
    ])

    await repository.remove('CF-001')

    expect(await repository.get('CF-001')).toBeUndefined()
    expect((await repository.list('CON-001')).map((file) => file.id)).toEqual(['CF-002'])
  })
})
