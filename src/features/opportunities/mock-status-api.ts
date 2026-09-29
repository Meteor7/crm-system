import { CrmApiError, type CrmApi } from '@/api/contracts'
import type { BinaryDownload } from '@/api/binary-transport'
import type { OpportunityStatusRecord } from './status-types'

const repositories = new WeakMap<object, { records: Map<string, OpportunityStatusRecord[]>; files: Map<string, BinaryDownload> }>()
export function createMockStatusApi(repository: object, actor: string, authorize: (opportunityId: string, write: boolean) => void): Pick<CrmApi, 'listOpportunityStatuses' | 'saveOpportunityStatus' | 'getOpportunityStatusFile'> {
  let data = repositories.get(repository)
  if (!data) { data = { records: new Map(), files: new Map() }; repositories.set(repository, data) }
  const state = data
  const invalid = (message: string) => new CrmApiError('VALIDATION_ERROR', message, 'mock-status', false)
  return {
    async listOpportunityStatuses(opportunityId) {
      authorize(opportunityId, false)
      return { data: structuredClone(state.records.get(opportunityId) ?? []), warnings: [] }
    },
    async saveOpportunityStatus(opportunityId, input, files) {
      authorize(opportunityId, true)
      if (!input.text.trim() || input.text.length > 10000) throw invalid('Status information is required (maximum 10000 characters).')
      const records = state.records.get(opportunityId) ?? []
      const existing = input.recordId ? records.find(record => record.id === input.recordId) : undefined
      if (input.recordId && !existing) throw new CrmApiError('NOT_FOUND', 'Status record was not found.', 'mock-status', false)
      if (existing && existing.modified !== input.expectedModified) throw new CrmApiError('VERSION_CONFLICT', 'Status was changed. Reload before editing.', 'mock-status', false)
      const retained = input.retainedFileIds.map(id => existing?.files.find(file => file.id === id))
      if (retained.some(file => !file) || new Set(input.retainedFileIds).size !== retained.length) throw invalid('Attachments must belong to this Status record.')
      if (retained.length + files.length > 10 || files.reduce((sum, file) => sum + file.size, 0) > 100 * 1024 * 1024) throw invalid('Up to 10 attachments and 100 MiB per upload.')
      if (files.some(file => !/\.(pdf|docx|xlsx|pptx|txt|csv|png|jpe?g)$/i.test(file.fileName) || !file.size || file.size !== file.blob.size)) throw invalid('Unsupported or empty attachment.')
      const modified = new Date(Math.max(Date.now(), existing ? Date.parse(existing.modified) + 1 : 0)).toISOString()
      const record: OpportunityStatusRecord = { id: existing?.id ?? crypto.randomUUID(), text: input.text.trim(), files: retained.filter(file => !!file), updatedBy: actor, updatedAt: modified, modified }
      for (const file of files) {
        const id = crypto.randomUUID()
        state.files.set(id, { blob: file.blob, fileName: file.fileName, mimeType: file.mimeType })
        record.files.push({ id, fileName: file.fileName, mimeType: file.mimeType, size: file.size })
      }
      state.records.set(opportunityId, [record, ...records.filter(item => item.id !== record.id)])
      return { data: structuredClone(record), warnings: [] }
    },
    async getOpportunityStatusFile(opportunityId, recordId, fileId) {
      authorize(opportunityId, false)
      const record = state.records.get(opportunityId)?.find(item => item.id === recordId)
      const file = record?.files.some(item => item.id === fileId) ? state.files.get(fileId) : undefined
      if (!file) throw new CrmApiError('NOT_FOUND', 'Status attachment was not found.', 'mock-status', false)
      return file
    },
  }
}
