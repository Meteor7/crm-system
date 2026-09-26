import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { CrmApi } from '@/api'
import { CrmApiError } from '@/api'
import { evaluations } from '@/api/mock-data'
import type { CustomerReportUploadResult, DemoArtifactMetaDto } from '@/types/crm'
import CustomerReportUploadModal from './CustomerReportUploadModal.vue'

const artifact: DemoArtifactMetaDto = {
  id: 'CRM-ART-00010', demoRequestId: 'DR-107', evaluationId: 'EVAL-103', type: 'Customer Report',
  fileName: '[Customer] feedback.pdf', mimeType: 'application/pdf', version: 1, createdBy: 'Boss',
  createdAt: '2026-08-20T10:00:00+08:00', visibility: 'Customer Review',
}
const uploadResult: CustomerReportUploadResult = { artifact, round: 2, version: 1 }

function setup(testRound: number, uploadCustomerReport = vi.fn().mockResolvedValue({ data: uploadResult, warnings: [] })) {
  const apiClient = { uploadCustomerReport } as unknown as CrmApi
  const wrapper = mount(CustomerReportUploadModal, { props: { evaluation: { ...evaluations[2], testRound }, apiClient } })
  return { wrapper, uploadCustomerReport }
}

async function choose(wrapper: ReturnType<typeof mount>, file: File) {
  const input = wrapper.get('[data-customer-report]')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
}

describe('CustomerReportUploadModal', () => {
  it('names the round on screen so a window left open across a retest cannot file into the new one', async () => {
    const { wrapper, uploadCustomerReport } = setup(2)
    const file = new File(['customer feedback'], 'feedback.pdf', { type: 'application/pdf' })
    await choose(wrapper, file)
    await wrapper.get('[data-upload-customer-report]').trigger('click')
    await flushPromises()

    expect(uploadCustomerReport).toHaveBeenCalledWith(evaluations[2].id, {
      file: { fileName: 'feedback.pdf', mimeType: 'application/pdf', size: file.size, blob: file },
      expectedRound: 2,
    })
    expect(wrapper.emitted('uploaded')?.[0]).toEqual([uploadResult])
  })

  it('keeps the chosen file and shows the retest conflict when the round has moved on', async () => {
    const conflict = vi.fn().mockRejectedValue(
      new CrmApiError('CONFLICT', '该 Demo Test 已进入第 2 轮，请刷新后重新上传报告', 'req-round-42', false),
    )
    const { wrapper } = setup(1, conflict)
    await choose(wrapper, new File(['customer feedback'], 'feedback.pdf', { type: 'application/pdf' }))
    await wrapper.get('[data-upload-customer-report]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('第 2 轮')
    expect(wrapper.get('[role="alert"]').text()).toContain('req-round-42')
    expect(wrapper.get('[data-upload-customer-report]').attributes('disabled')).toBeUndefined()
  })
})
