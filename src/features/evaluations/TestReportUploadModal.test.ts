import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { CrmApi } from '@/api'
import { CrmApiError } from '@/api'
import { evaluations } from '@/api/mock-data'
import type { DemoArtifactMetaDto, DemoTestReportUploadResult } from '@/types/crm'
import TestReportUploadModal from './TestReportUploadModal.vue'

const artifact: DemoArtifactMetaDto = {
  id: 'CRM-ART-00001', demoRequestId: 'DR-107', evaluationId: 'EVAL-103', type: 'Test Report',
  fileName: 'results.txt', mimeType: 'text/plain', version: 1, createdBy: 'Engineer',
  createdAt: '2026-08-11T10:00:00+08:00', visibility: 'Internal',
}
const externalArtifact: DemoArtifactMetaDto = {
  ...artifact, id: 'CRM-ART-00002', fileName: 'customer-results.pdf', visibility: 'Customer Review',
}
const uploadResult: DemoTestReportUploadResult = {
  internalReportArtifact: artifact, externalReportArtifact: externalArtifact, version: 1,
}

function setup() {
  const releaseDemoTestReport = vi.fn().mockResolvedValue({ data: uploadResult, warnings: [] })
  const apiClient = { releaseDemoTestReport } as unknown as CrmApi
  return { wrapper: mount(TestReportUploadModal, { props: { evaluation: evaluations[2], apiClient } }), releaseDemoTestReport }
}

async function choose(wrapper: ReturnType<typeof mount>, selector: string, file: File) {
  const input = wrapper.get(selector)
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
}

describe('TestReportUploadModal', () => {
  it('uploads both reports with exact metadata', async () => {
    const { wrapper, releaseDemoTestReport } = setup()
    const internal = new File(['capture=98.5'], 'results.txt', { type: 'text/plain' })
    const external = new File(['customer report'], 'customer-results.pdf', { type: 'application/pdf' })
    await choose(wrapper, '[data-internal-report]', internal)
    await choose(wrapper, '[data-external-report]', external)
    await wrapper.get('[data-upload-test-report]').trigger('click')
    await flushPromises()

    expect(releaseDemoTestReport).toHaveBeenCalledWith(evaluations[2].id, {
      internalFile: { fileName: 'results.txt', mimeType: 'text/plain', size: internal.size, blob: internal },
      externalFile: { fileName: 'customer-results.pdf', mimeType: 'application/pdf', size: external.size, blob: external },
    })
    expect(wrapper.emitted('uploaded')?.[0]).toEqual([uploadResult])
  })

  it('rejects empty, oversized, and unsupported files before the API call', async () => {
    const { wrapper, releaseDemoTestReport } = setup()
    expect(wrapper.get('[data-upload-test-report]').attributes('disabled')).toBeDefined()

    await choose(wrapper, '[data-internal-report]', new File(['x'], 'malware.exe', { type: 'application/octet-stream' }))
    expect(wrapper.get('[role="alert"]').text()).toContain('仅支持')

    const oversized = new File(['x'], 'large.pdf', { type: 'application/pdf' })
    Object.defineProperty(oversized, 'size', { value: 100 * 1024 * 1024 + 1 })
    await choose(wrapper, '[data-internal-report]', oversized)
    expect(wrapper.get('[role="alert"]').text()).toContain('100 MiB')
    expect(releaseDemoTestReport).not.toHaveBeenCalled()
  })

  it('keeps close disabled while an upload is pending', async () => {
    let resolve!: (value: unknown) => void
    const apiClient = { releaseDemoTestReport: vi.fn(() => new Promise((done) => { resolve = done })) } as unknown as CrmApi
    const wrapper = mount(TestReportUploadModal, { props: { evaluation: evaluations[2], apiClient } })
    await choose(wrapper, '[data-internal-report]', new File(['x'], 'result.txt', { type: 'text/plain' }))
    await choose(wrapper, '[data-external-report]', new File(['x'], 'customer.txt', { type: 'text/plain' }))
    void wrapper.get('[data-upload-test-report]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-upload-test-report]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[role="dialog"] header button').attributes('disabled')).toBeDefined()
    resolve({ data: uploadResult, warnings: [] })
    await flushPromises()
  })

  it('keeps the report selected and shows Request ID when upload fails', async () => {
    const apiClient = {
      releaseDemoTestReport: vi.fn().mockRejectedValue(
        new CrmApiError('UPSTREAM_TIMEOUT', 'Report storage timed out', 'req-report-upload-42', true),
      ),
    } as unknown as CrmApi
    const wrapper = mount(TestReportUploadModal, { props: { evaluation: evaluations[2], apiClient } })
    await choose(wrapper, '[data-internal-report]', new File(['report'], 'results.txt', { type: 'text/plain' }))
    await choose(wrapper, '[data-external-report]', new File(['customer'], 'customer.txt', { type: 'text/plain' }))

    await wrapper.get('[data-upload-test-report]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Report storage timed out')
    expect(wrapper.get('[role="alert"]').text()).toContain('req-report-upload-42')
    expect(wrapper.get('[data-upload-test-report]').attributes('disabled')).toBeUndefined()
    expect(wrapper.emitted('uploaded')).toBeUndefined()
  })
})
