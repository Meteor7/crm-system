import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setLocale } from '@/i18n'
import { createMockApi } from '@/api/mock-adapter'
import { useAppStore } from '@/stores/app'
import type { OpportunityDocuments } from '@/features/opportunities/document-types'
import OpportunityDocumentsPage from './OpportunityDocumentsPage.vue'

async function setup(role: 'Manager' | 'Engineer' = 'Manager') {
  const api = createMockApi({ latency: 0, role })
  const bootstrap = await api.getBootstrap()
  const pinia = createPinia()
  useAppStore(pinia).bootstrap = bootstrap.data
  const data: OpportunityDocuments = { opportunityId: 'opp', title: 'Customer opportunity', modified: 'version1',
    links: { productScorecard: { url: '', state: 'missing' }, dealScorecard: { url: 'https://example.com/deal', state: 'ready' } },
    groups: [{ kind: 'status', items: [{ id: 'file1', title: 'Requirements.txt', at: '2026-10-01', fileId: 'file1', sourceId: 'opp', recordId: 'status1' }] }, { kind: 'rfq', items: [] }] }
  vi.spyOn(api, 'getOpportunityDocuments').mockResolvedValue({ ...bootstrap, data })
  const save = vi.spyOn(api, 'saveOpportunityDocumentLinks').mockResolvedValue({ ...bootstrap, data: { links: data.links, modified: 'version2' } })
  const download = vi.spyOn(api, 'getOpportunityStatusFile').mockRejectedValue(new Error('The file was removed.'))
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/opportunities/:opportunityId/documents', name: 'opportunity-documents', component: OpportunityDocumentsPage },
    { path: '/opportunities/:opportunityId', name: 'opportunity-detail', component: { template: '<div />' } },
  ] })
  await router.push('/opportunities/opp/documents'); await router.isReady()
  const wrapper = mount(OpportunityDocumentsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
  await flushPromises()
  return { api, wrapper, save, download }
}

describe('Opportunity document library', () => {
  beforeEach(() => setLocale('en-US'))
  afterEach(() => setLocale('zh-CN'))
  it('shows source records and missing links, retaining the draft on version conflict', async () => {
    const { wrapper, save } = await setup()
    expect(wrapper.text()).toContain('Requirements.txt')
    expect(wrapper.text()).toContain('Link not set')
    expect(wrapper.get('a[href="https://example.com/deal"]').attributes('rel')).toContain('noopener')
    await wrapper.findAll('button').find(button => button.text() === 'Edit links')!.trigger('click')
    await wrapper.get('[data-testid="productScorecard"]').setValue('https://example.com/product')
    save.mockRejectedValueOnce(new Error('Changed by another request'))
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(save).toHaveBeenCalledWith('opp', { productScorecard: 'https://example.com/product', dealScorecard: 'https://example.com/deal' }, 'version1')
    expect(wrapper.get<HTMLInputElement>('[data-testid="productScorecard"]').element.value).toBe('https://example.com/product')
    expect(wrapper.text()).toContain('Changed by another request')
    wrapper.unmount()
  })
  it('uses the scoped download endpoint and surfaces deleted files without losing the library', async () => {
    const { wrapper, download } = await setup()
    await wrapper.findAll('button').find(button => button.text() === 'Download')!.trigger('click'); await flushPromises()
    expect(download).toHaveBeenCalledWith('opp', 'status1', 'file1')
    expect(wrapper.text()).toContain('The file was removed.')
    expect(wrapper.find('[data-testid="documents-status"]').exists()).toBe(true)
    wrapper.unmount()
  })
  it('does not offer scorecard editing to Engineers', async () => {
    const { wrapper } = await setup('Engineer')
    expect(wrapper.findAll('button').some(button => button.text() === 'Edit links')).toBe(false)
    wrapper.unmount()
  })
})
