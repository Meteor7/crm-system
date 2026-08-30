import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { DemoArtifactMetaDto } from '@/types/crm'
import DemoArticleCard from './DemoArticleCard.vue'

const artifacts: DemoArtifactMetaDto[] = [
  { id: 'ART-REPORT', demoRequestId: 'DR-1', evaluationId: 'EVAL-1', type: 'Test Report', fileName: 'capture.txt', mimeType: 'text/plain', version: 2, createdBy: 'Engineer Li', createdAt: '2026-08-11T10:00:00+08:00', visibility: 'Internal' },
  { id: 'ART-LEGACY', demoRequestId: 'DR-1', evaluationId: 'EVAL-1', type: 'External Demo Test Report PDF', fileName: 'legacy.pdf', mimeType: 'application/pdf', version: 1, createdBy: 'Manager Chen', createdAt: '2026-08-10T10:00:00+08:00', visibility: 'Customer Review' } as unknown as DemoArtifactMetaDto,
  { id: 'ART-REQUEST', demoRequestId: 'DR-1', type: 'Demo Request DOCX', fileName: 'request.docx', mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', version: 1, createdBy: 'Sales Zhou', createdAt: '2026-08-09T10:00:00+08:00', visibility: 'Internal' },
]

describe('DemoArticleCard', () => {
  it('shows only engineer-uploaded Test Reports and Demo Request forms', () => {
    const wrapper = mount(DemoArticleCard, { props: { artifacts } })
    expect(wrapper.text()).toContain('Test Reports1')
    expect(wrapper.text()).toContain('Demo Request Forms1')
    expect(wrapper.text()).toContain('capture.txt')
    expect(wrapper.text()).toContain('v2 · Engineer Li')
    expect(wrapper.text()).not.toContain('legacy.pdf')
    expect(wrapper.text()).toContain('request.docx')
    expect(wrapper.find('[data-preview-artifact="ART-REQUEST"]').exists()).toBe(false)
  })

  it('emits preview only for previewable files and download for every file', async () => {
    const wrapper = mount(DemoArticleCard, { props: { artifacts } })
    await wrapper.get('[data-preview-artifact="ART-REPORT"]').trigger('click')
    await wrapper.get('[data-download-artifact="ART-REQUEST"]').trigger('click')
    expect(wrapper.emitted('preview')?.[0]).toEqual(['ART-REPORT'])
    expect(wrapper.emitted('download')?.[0]).toEqual(['ART-REQUEST'])
  })
})
