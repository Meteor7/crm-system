import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { ApiResponse, Account360Dto } from '@/types/crm'
import { createMockApi } from '@/api/mock-adapter'
import { CrmApiError } from '@/api'
import AccountProfile from './AccountProfile.vue'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

describe('AccountProfile request identity', () => {
  it('does not let an older account response overwrite the selected account', async () => {
    const base = createMockApi({ latency: 0 })
    const accountA = await base.getAccount360('ACC-001')
    accountA.data.quotations = [{
      id: 'CRM-QTN-00001', refNo: 'Q-2026-0001', quotationType: 'Device',
      opportunityId: 'OPP-001', opportunityTitle: '南京缺陷检测设备 2 台',
      accountId: 'ACC-001', accountName: '示例企业014有限公司', owner: 'person002@crm.example.invalid',
      status: 'Published', approvalStatus: 'Approved', latestVersion: 1,
      currentVersionId: 'CRM-QTNV-00001', currentPublishedVersionId: 'CRM-QTNV-00001', modified: '2026-08-25T10:00:00+08:00',
    }]
    const accountB = await base.getAccount360('ACC-002')
    const a = deferred<ApiResponse<Account360Dto>>()
    const b = deferred<ApiResponse<Account360Dto>>()
    const apiClient = { ...base, getAccount360: vi.fn((id: string) => id === 'ACC-001' ? a.promise : b.promise) }
    const wrapper = mount(AccountProfile, { props: { accountId: 'ACC-001', apiClient }, global: { plugins: [createPinia()] } })
    await wrapper.setProps({ accountId: 'ACC-002' })
    b.resolve(accountB)
    await flushPromises()
    expect(wrapper.text()).toContain('示例企业044')

    a.resolve(accountA)
    await flushPromises()
    expect(wrapper.text()).toContain('示例企业044')
    expect(wrapper.text()).not.toContain('示例企业014')
  })

  it('clears the previous account and exposes the new request failure', async () => {
    const base = createMockApi({ latency: 0 })
    const accountA = await base.getAccount360('ACC-001')
    accountA.data.quotations = [{
      id: 'CRM-QTN-00001', refNo: 'Q-2026-0001', quotationType: 'Device',
      opportunityId: 'OPP-001', opportunityTitle: '南京缺陷检测设备 2 台',
      accountId: 'ACC-001', accountName: '示例企业014有限公司', owner: 'person002@crm.example.invalid',
      status: 'Published', approvalStatus: 'Approved', latestVersion: 1,
      currentVersionId: 'CRM-QTNV-00001', currentPublishedVersionId: 'CRM-QTNV-00001', modified: '2026-08-25T10:00:00+08:00',
    }]
    const apiClient = { ...base, getAccount360: vi.fn()
      .mockResolvedValueOnce(accountA)
      .mockRejectedValueOnce(new Error('客户 B 加载失败')) }
    const wrapper = mount(AccountProfile, { props: { accountId: 'ACC-001', apiClient }, global: { plugins: [createPinia()] } })
    await flushPromises()
    expect(wrapper.text()).toContain('示例企业014')
    expect(wrapper.text()).toContain('Demo / Wafer Test')
    expect(wrapper.text()).toContain('合同')
    expect(wrapper.text()).not.toContain('采购需求与行动')
    expect(wrapper.findAll('.profile-grid > .profile-section > header strong').map((item) => item.text())).toEqual([
      'Site / 厂区',
      '关键人与组织关系',
    ])
    expect(wrapper.findAll('.project-section > header strong').map((item) => item.text())).toEqual([
      '商机与 Booking', '合同', '拜访与下一步', 'Demo / Wafer Test',
    ])
    const projectFilter = wrapper.get('[data-testid="account-project-filter"]')
    expect(projectFilter.findAll('option').map((option) => option.attributes('value'))).toEqual([
      'all',
      'opportunity:OPP-001',
    ])
    await projectFilter.setValue('opportunity:OPP-001')
    const projectSections = wrapper.findAll('.project-section')
    expect(projectSections[0].text()).toContain('南京缺陷检测设备 2 台')
    expect(projectSections[1].text()).toContain('Q-2026-0001')
    expect(projectSections[2].text()).toContain('南京 Fab Demo 前现场确认')
    expect(projectSections[3].text()).toContain('南京 CD 量测重复性验证')
    expect(wrapper.find('[data-testid="export-customer-report"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('情报')

    await wrapper.setProps({ accountId: 'ACC-002' })
    await flushPromises()
    expect(wrapper.text()).toContain('客户 B 加载失败')
    expect(wrapper.text()).not.toContain('示例企业014')
  })

  it('renders a permission denial without leaking account detail', async () => {
    const base = createMockApi({ latency: 0 })
    const apiClient = { ...base, getAccount360: vi.fn().mockRejectedValue(new CrmApiError('PERMISSION_DENIED', '无权查看该客户', 'req_denied_360')) }
    const wrapper = mount(AccountProfile, { props: { accountId: 'ACC-001', apiClient }, global: { plugins: [createPinia()] } })
    await flushPromises()

    expect(wrapper.find('.state-denied').exists()).toBe(true)
    expect(wrapper.text()).toContain('req_denied_360')
    expect(wrapper.text()).not.toContain('示例企业014')
  })

  it('surfaces stale detail metadata while retaining the readable snapshot', async () => {
    const base = createMockApi({ latency: 0 })
    const snapshot = await base.getAccount360('ACC-001')
    snapshot.warnings = ['客户详情为缓存快照']
    const apiClient = { ...base, getAccount360: vi.fn().mockResolvedValue(snapshot) }
    const wrapper = mount(AccountProfile, { props: { accountId: 'ACC-001', apiClient }, global: { plugins: [createPinia()] } })
    await flushPromises()

    expect(wrapper.text()).toContain('PARTIAL / STALE')
    expect(wrapper.text()).toContain('客户详情为缓存快照')
    expect(wrapper.text()).toContain('示例企业014')
  })

  it('paginates dense project sections independently with five rows per page', async () => {
    const base = createMockApi({ latency: 0 })
    const snapshot = await base.getAccount360('ACC-001')
    const booking = (await base.listPipeline({})).data.bookings[0]
    snapshot.data.bookings = Array.from({ length: 5 }, (_, index) => ({
      ...booking,
      id: `BKG-DENSE-${index + 1}`,
      accountId: 'ACC-001',
      accountName: '示例企业014有限公司',
      sourceOpportunityId: 'OPP-001',
    }))
    snapshot.data.quotations = Array.from({ length: 6 }, (_, index) => ({
      id: `CRM-QTN-DENSE-${index + 1}`, refNo: `Q-2026-${String(index + 1).padStart(4, '0')}`,
      quotationType: 'Device' as const, opportunityId: 'OPP-001', opportunityTitle: '南京缺陷检测设备 2 台',
      accountId: 'ACC-001', accountName: '示例企业014有限公司', owner: 'person002@crm.example.invalid',
      status: 'Published' as const, approvalStatus: 'Approved' as const, latestVersion: 1,
      currentVersionId: `CRM-QTNV-DENSE-${index + 1}`, currentPublishedVersionId: `CRM-QTNV-DENSE-${index + 1}`,
      modified: `2026-08-25T10:0${index}:00+08:00`,
    }))
    const apiClient = { ...base, getAccount360: vi.fn().mockResolvedValue(snapshot) }
    const wrapper = mount(AccountProfile, { props: { accountId: 'ACC-001', apiClient }, global: { plugins: [createPinia()] } })
    await flushPromises()
    await wrapper.get('[data-testid="account-project-filter"]').setValue('opportunity:OPP-001')

    const dealSection = wrapper.findAll('.project-section')[0]
    const contractSection = wrapper.findAll('.project-section')[1]
    expect(dealSection.findAll('article')).toHaveLength(5)
    expect(contractSection.findAll('article')).toHaveLength(5)
    expect(dealSection.get('.pagination-controls').text()).toContain('第 1 / 2 页')
    expect(contractSection.get('.pagination-controls').text()).toContain('第 1 / 2 页')

    await dealSection.get('[data-page-next]').trigger('click')
    expect(dealSection.findAll('article')).toHaveLength(1)
    expect(dealSection.get('.pagination-controls').text()).toContain('第 2 / 2 页')
    expect(contractSection.findAll('article')).toHaveLength(5)
    expect(contractSection.get('.pagination-controls').text()).toContain('第 1 / 2 页')

    await contractSection.get('[data-page-next]').trigger('click')
    expect(contractSection.findAll('article')).toHaveLength(1)
    expect(contractSection.text()).toContain('Q-2026-0006')
  })
})
